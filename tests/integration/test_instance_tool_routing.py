"""Integration test for instance-specific tool routing.

This test verifies that when a user asks about a specific Redis instance,
the agent's tools connect to THAT instance, not the application's Redis.
"""

import pytest

from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.core.tasks import process_agent_turn
from redis_sre_agent.core.thread_state import get_thread_manager


@pytest.fixture
async def thread_manager():
    """Get the thread manager for testing."""
    manager = get_thread_manager()
    yield manager


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tools_connect_to_correct_instance(thread_manager):
    """Test that diagnostic tools connect to the specified instance, not default Redis."""

    # 1. Register a Redis Enterprise instance (simulating user's production instance)
    test_instance = RedisInstance(
        id="redis-production-test",
        name="Redis Enterprise Production",
        connection_url="redis://:admin@redis-enterprise:12000/0",
        environment="production",
        usage="cache",
        description="Test Redis Enterprise instance",
    )

    # Store instance using the correct API format
    from redis_sre_agent.api.instances import get_instances_from_redis, save_instances_to_redis

    # Get existing instances
    existing_instances = await get_instances_from_redis()

    # Add our test instance
    all_instances = existing_instances + [test_instance]
    await save_instances_to_redis(all_instances)

    print(f"✅ Registered test instance: {test_instance.name}")
    print(f"   Connection URL: {test_instance.connection_url}")

    # 2. Create a thread with instance context
    thread_id = await thread_manager.create_thread(
        user_id="test-user",
        session_id="test-session",
        initial_context={
            "instance_id": test_instance.id,
            "test": True,
        },
    )

    print(f"✅ Created thread: {thread_id}")
    print(f"   Instance context: {test_instance.id}")

    # 3. Ask about the instance's health (this should trigger diagnostics)
    query = f"Check the health of Redis instance {test_instance.name}"

    print(f"\n📝 User query: {query}")
    print(f"   Expected: Tools should connect to {test_instance.connection_url}")
    print("   NOT to: redis://redis:6379/0 (application Redis)")

    # 4. Process the query
    try:
        # Note: This will fail to connect to redis-enterprise:12000 since it doesn't exist
        # But we can check the logs/errors to see which URL it TRIED to connect to
        await process_agent_turn(
            thread_id=thread_id,
            message=query,
        )
    except Exception as e:
        print(f"\n⚠️  Agent execution failed (expected): {e}")

    # 5. Verify the thread state and check what happened
    thread_state = await thread_manager.get_thread_state(thread_id)

    print("\n📊 Thread state:")
    print(f"   Status: {thread_state.status}")
    print(f"   Updates: {len(thread_state.updates)}")
    print(f"   Result: {thread_state.result}")

    # Print ALL updates to see what happened
    print("\n📝 All updates:")
    for i, update in enumerate(thread_state.updates):
        print(f"   {i+1}. [{update.update_type}] {update.message[:150]}")

    # Check the updates for evidence of which Redis URL was used
    redis_urls_mentioned = []
    for update in thread_state.updates:
        if "redis://" in update.message:
            print(f"   Update with Redis URL: {update.message[:100]}")
            # Extract Redis URLs from the message
            import re

            urls = re.findall(r"redis://[^\s]+", update.message)
            redis_urls_mentioned.extend(urls)

    # Also check the final result
    if thread_state.result:
        print("\n📄 Final result:")
        result_str = str(thread_state.result)
        print(f"   {result_str[:500]}")
        if "redis://" in result_str:
            import re

            urls = re.findall(r"redis://[^\s]+", result_str)
            redis_urls_mentioned.extend(urls)

    print("\n🔍 Redis URLs mentioned in updates:")
    for url in set(redis_urls_mentioned):
        print(f"   - {url}")

    # 6. Assertions
    if redis_urls_mentioned:
        print("\n🔍 Analysis:")
        has_target = any("redis-enterprise:12000" in url for url in redis_urls_mentioned)
        has_wrong = any(
            "localhost:6379" in url or "redis:6379" in url for url in redis_urls_mentioned
        )

        print(f"   Target instance mentioned: {has_target}")
        print(f"   Wrong instance mentioned: {has_wrong}")

        if has_wrong and not has_target:
            print("\n❌ FAIL: Tools connected to WRONG instance!")
            print("   Expected: redis-enterprise:12000")
            print(f"   Got: {redis_urls_mentioned}")
            assert False, "Tools connected to wrong Redis instance"
        elif has_target and has_wrong:
            print("\n⚠️  MIXED: Both instances mentioned (agent aware of problem)")
            print("   This means agent KNOWS it should connect to redis-enterprise:12000")
            print("   But tools are still connecting to localhost:6379")
            print("   This is the BUG we need to fix!")
            assert False, "Tools not using instance context correctly"
        elif has_target:
            print("\n✅ PASS: Tools connected to correct instance!")
        else:
            print("\n⚠️  UNKNOWN: No clear evidence of which instance was used")
    else:
        print("\n⚠️  WARNING: No Redis URLs found in updates")
        print("   This might mean the agent didn't try to connect yet")
        print("   Or the error happened before tool execution")
        assert False, "No Redis URLs found - cannot verify tool routing"

    # Cleanup
    remaining_instances = [inst for inst in all_instances if inst.id != test_instance.id]
    await save_instances_to_redis(remaining_instances)
    await thread_manager.delete_thread(thread_id)

    print("\n🧹 Cleanup complete")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_instance_context_passed_to_agent(thread_manager):
    """Test that instance context is properly passed through the agent workflow."""

    # Register instance
    test_instance = RedisInstance(
        id="redis-test-context",
        name="Test Instance",
        connection_url="redis://test-host:6379/0",
        environment="test",
        usage="cache",
        description="Test instance for context passing",
    )

    from redis_sre_agent.core.redis import get_redis_client

    redis_client = get_redis_client()

    instance_key = f"sre:instance:{test_instance.id}"
    await redis_client.hset(
        instance_key,
        mapping={
            "id": test_instance.id,
            "name": test_instance.name,
            "connection_url": test_instance.connection_url,
            "environment": test_instance.environment,
            "usage": test_instance.usage,
            "description": test_instance.description,
        },
    )
    await redis_client.sadd("sre:instances", test_instance.id)

    # Create thread WITH instance context
    thread_id = await thread_manager.create_thread(
        user_id="test-user",
        session_id="test-session",
        initial_context={
            "instance_id": test_instance.id,
        },
    )

    # Verify context was stored
    thread_state = await thread_manager.get_thread_state(thread_id)
    assert (
        thread_state.context.get("instance_id") == test_instance.id
    ), "Instance ID should be in thread context"

    print("✅ Instance context properly stored in thread")
    print(f"   Instance ID: {thread_state.context.get('instance_id')}")

    # Cleanup
    await redis_client.delete(instance_key)
    await redis_client.srem("sre:instances", test_instance.id)
    await thread_manager.delete_thread(thread_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

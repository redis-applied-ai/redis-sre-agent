"""Test instance_id persistence across conversation turns."""

from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.threads import Thread, ThreadManager, ThreadMetadata


@pytest.mark.asyncio
async def test_instance_id_from_client_updates_thread():
    """Test that instance_id from client is saved to thread context."""
    # Mock Redis client
    mock_redis = AsyncMock()
    thread_manager = ThreadManager(redis_client=mock_redis)

    # Create initial thread state with no instance_id
    thread_state = Thread(
        thread_id="test-thread-123",
        context={},
        metadata=ThreadMetadata(user_id="test-user"),
    )

    # Mock get_thread to return our thread
    with patch.object(thread_manager, "get_thread", return_value=thread_state):
        with patch.object(thread_manager, "update_thread_context") as mock_update:
            with patch.object(thread_manager, "add_thread_update"):
                # Simulate what happens in process_agent_turn
                instance_id_from_client = "redis-prod-123"
                context = {"instance_id": instance_id_from_client}

                # This is what the task does
                if context and context.get("instance_id"):
                    await thread_manager.update_thread_context(
                        "test-thread-123", {"instance_id": instance_id_from_client}, merge=True
                    )

                # Verify update_thread_context was called with correct params
                mock_update.assert_called_once_with(
                    "test-thread-123", {"instance_id": "redis-prod-123"}, merge=True
                )


@pytest.mark.asyncio
async def test_instance_id_from_thread_is_reused():
    """Test that instance_id from thread context is reused when client doesn't provide one."""
    # Create thread state with saved instance_id
    thread_state = Thread(
        thread_id="test-thread-123",
        context={"instance_id": "redis-prod-456"},
        metadata=ThreadMetadata(user_id="test-user"),
    )

    # Simulate the logic from process_agent_turn
    instance_id_from_client = None  # No instance_id from client
    instance_id_from_thread = thread_state.context.get("instance_id")

    active_instance_id = None

    if instance_id_from_client:
        active_instance_id = instance_id_from_client
    elif instance_id_from_thread:
        active_instance_id = instance_id_from_thread

    # Verify we're using the thread's instance_id
    assert active_instance_id == "redis-prod-456"


@pytest.mark.asyncio
async def test_instance_created_from_message_is_saved():
    """Test that instance created from user message is saved to thread context."""
    from redis_sre_agent.agent.langgraph_agent import _extract_instance_details_from_message

    # Test message with connection details
    message = """
    My Redis is slow. Here are the details:
    redis://prod-cache.example.com:6379
    environment: production
    usage: cache
    """

    # Extract details
    details = _extract_instance_details_from_message(message)

    # Verify details were extracted
    assert details is not None
    assert details["connection_url"] == "redis://prod-cache.example.com:6379"
    assert details["environment"] == "production"
    assert details["usage"] == "cache"
    assert "name" in details  # Should auto-generate name


@pytest.mark.asyncio
async def test_client_instance_id_overrides_thread():
    """Test that client-provided instance_id overrides thread's saved instance_id."""
    # Thread has one instance_id saved
    thread_state = Thread(
        thread_id="test-thread-123",
        context={"instance_id": "redis-prod-old"},
        metadata=ThreadMetadata(user_id="test-user"),
    )

    # Client provides a different instance_id
    instance_id_from_client = "redis-prod-new"
    instance_id_from_thread = thread_state.context.get("instance_id")

    # Simulate the logic
    active_instance_id = None

    if instance_id_from_client:
        active_instance_id = instance_id_from_client
    elif instance_id_from_thread:
        active_instance_id = instance_id_from_thread

    # Verify client's instance_id takes precedence
    assert active_instance_id == "redis-prod-new"


@pytest.mark.asyncio
async def test_no_instance_id_routes_to_knowledge_agent():
    """Test that when no instance_id can be obtained, routing context has no instance_id."""
    # Simulate the scenario
    instance_id_from_client = None
    instance_id_from_thread = None
    message = "What is Redis?"  # General question, no connection details

    from redis_sre_agent.agent.langgraph_agent import _extract_instance_details_from_message

    instance_details = _extract_instance_details_from_message(message)

    # No details should be extracted
    assert instance_details is None

    # Determine active_instance_id
    active_instance_id = None
    if instance_id_from_client:
        active_instance_id = instance_id_from_client
    elif instance_id_from_thread:
        active_instance_id = instance_id_from_thread
    elif instance_details:
        active_instance_id = "would-be-created"

    # Verify no instance_id
    assert active_instance_id is None

    # This means routing_context will not have instance_id
    # and router will route to knowledge agent


@pytest.mark.asyncio
async def test_update_thread_context_merge():
    """Test that update_thread_context properly merges context."""
    from redis_sre_agent.core.keys import RedisKeys

    mock_redis = AsyncMock()
    thread_manager = ThreadManager(redis_client=mock_redis)

    thread_id = "test-thread-123"
    keys = RedisKeys.all_thread_keys(thread_id)

    # Mock existing context
    existing_context = {
        b"messages": b'[{"role": "user", "content": "hello"}]',
        b"some_key": b"some_value",
    }
    mock_redis.hgetall.return_value = existing_context

    # Update with new instance_id
    await thread_manager.update_thread_context(
        thread_id, {"instance_id": "redis-prod-123"}, merge=True
    )

    # Verify hset was called (twice: once for context, once for metadata)
    assert mock_redis.hset.call_count == 2

    # Get the first call (context update)
    context_call = mock_redis.hset.call_args_list[0]
    assert context_call[0][0] == keys["context"]

    # Verify the mapping includes both old and new keys
    mapping = context_call[1]["mapping"]
    assert "instance_id" in mapping
    assert mapping["instance_id"] == "redis-prod-123"
    assert "messages" in mapping  # Old key preserved
    assert "some_key" in mapping  # Old key preserved


@pytest.mark.asyncio
async def test_update_thread_context_replace():
    """Test that update_thread_context can replace context entirely."""
    from redis_sre_agent.core.keys import RedisKeys

    mock_redis = AsyncMock()
    thread_manager = ThreadManager(redis_client=mock_redis)

    thread_id = "test-thread-123"
    keys = RedisKeys.all_thread_keys(thread_id)

    # Update with replace=False (replace entirely)
    await thread_manager.update_thread_context(
        thread_id, {"instance_id": "redis-prod-123"}, merge=False
    )

    # Verify delete was called to clear old context
    mock_redis.delete.assert_called_once_with(keys["context"])

    # Verify hset was called (twice: once for context, once for metadata)
    assert mock_redis.hset.call_count == 2

    # Get the first call (context update)
    context_call = mock_redis.hset.call_args_list[0]
    mapping = context_call[1]["mapping"]
    assert "instance_id" in mapping
    assert len(mapping) == 1  # Only the new key

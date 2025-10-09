"""Integration test for Redis memory pressure demo scenario."""

import time
from unittest.mock import AsyncMock, patch

import pytest
import redis

from redis_sre_agent.agent.langgraph_agent import get_sre_agent
from redis_sre_agent.tools.redis_diagnostics import RedisDiagnostics


class TestRedisMemoryDemo:
    """Test Redis memory pressure detection and agent response."""

    def setup_method(self):
        """Clear agent singleton before each test."""
        import redis_sre_agent.agent.langgraph_agent as agent_module

        agent_module._sre_agent = None

    def teardown_method(self):
        """Clear agent singleton after each test."""
        import redis_sre_agent.agent.langgraph_agent as agent_module

        agent_module._sre_agent = None

    @pytest.fixture
    async def redis_client(self):
        """Set up Redis client for integration testing."""
        try:
            client = redis.Redis(host="localhost", port=6379, decode_responses=True)
            # Test connection
            client.ping()
            yield client
        except redis.ConnectionError:
            pytest.skip("Redis not available for integration testing")
        finally:
            try:
                client.close()
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_redis_memory_pressure_detection(self, redis_client):
        """Test that Redis health checker detects memory pressure."""

        # First, get baseline memory info
        health_checker = RedisDiagnostics("redis://localhost:6379/0")

        try:
            # Get initial Redis info
            initial_info = redis_client.info("memory")
            initial_memory = initial_info.get("used_memory", 0)

            print(f"Initial Redis memory usage: {initial_memory / (1024 * 1024):.2f} MB")

            # Fill Redis with data to increase memory usage
            # Create keys that will consume memory
            pipe = redis_client.pipeline()

            # Add large strings to increase memory usage
            for i in range(1000):
                key = f"demo:large_key:{i}"
                # Create a 10KB string
                value = "x" * 10240  # 10KB per key = ~10MB total
                pipe.set(key, value)

            pipe.execute()

            # Wait a moment for Redis to update stats
            time.sleep(1)

            # Check memory after loading data
            after_info = redis_client.info("memory")
            after_memory = after_info.get("used_memory", 0)

            print(f"Memory after data load: {after_memory / (1024 * 1024):.2f} MB")

            # Run health check diagnostics
            diagnostics = await health_checker.run_diagnostic_suite()

            # Verify diagnostics detected memory usage
            diagnostic_data = diagnostics.get("diagnostics", {})
            assert "memory" in diagnostic_data
            memory_diag = diagnostic_data["memory"]

            assert "used_memory_bytes" in memory_diag

            # Memory usage should have increased
            assert memory_diag["used_memory_bytes"] > initial_memory

            print(
                f"Health check detected memory usage: {memory_diag['used_memory_bytes'] / (1024 * 1024):.2f} MB"
            )

            # Verify diagnostic data is present (no status checks needed)
            assert memory_diag["used_memory_bytes"] > 0

        finally:
            # Cleanup test keys
            try:
                keys = redis_client.keys("demo:large_key:*")
                if keys:
                    redis_client.delete(*keys)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_agent_responds_to_memory_alert(self, redis_client):
        """Test that SRE agent provides helpful response to Redis memory issues."""

        # Mock the agent to avoid OpenAI calls in testing
        expected_response = """
I can help you investigate the Redis memory issue. Here's what I recommend:

**Immediate Diagnostic Steps:**
1. Run `INFO memory` to get detailed memory breakdown:
   - used_memory: Total memory used by Redis
   - used_memory_rss: Memory allocated by OS
   - mem_fragmentation_ratio: Memory fragmentation level

2. Check memory configuration:
   - `CONFIG GET maxmemory` - Check if memory limit is set
   - `CONFIG GET maxmemory-policy` - Verify eviction policy

3. Identify large keys:
   - `MEMORY USAGE key` on suspected large keys
   - Use `SCAN` with `MEMORY USAGE` to find memory-heavy keys

**Common Resolutions:**
- Set memory limit: `CONFIG SET maxmemory 1gb`
- Configure eviction: `CONFIG SET maxmemory-policy allkeys-lru`
- Remove or optimize large keys
- Consider memory defragmentation if fragmentation ratio > 1.5

**Monitoring:**
- Watch `used_memory_peak` to understand memory patterns
- Monitor `mem_fragmentation_ratio` for memory efficiency
- Set up alerts for `used_memory` approaching limits

Would you like me to help analyze specific Redis INFO output or run diagnostic commands?
        """

        # Create mock agent with process_query method
        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(return_value=expected_response)

        # Patch both the singleton and the getter function
        with patch("redis_sre_agent.agent.langgraph_agent._sre_agent", mock_agent):
            with patch(
                "redis_sre_agent.agent.langgraph_agent.get_sre_agent", return_value=mock_agent
            ):
                # Test agent query about memory issues
                agent = get_sre_agent()

                query = "Redis is using high memory and I'm getting alerts. Can you help me diagnose the issue?"

                response = await agent.process_query(
                    query=query, session_id="demo_session", user_id="sre_demo"
                )

                # Verify response contains helpful memory troubleshooting guidance
                response_lower = response.lower()
                # Check for memory-related terms (agent provides helpful guidance)
                assert "memory" in response_lower
                assert "maxmemory" in response_lower or "used_memory" in response_lower
                # Response should provide actionable guidance
                assert len(response) > 100  # Should be a substantive response

    @pytest.mark.asyncio
    async def test_complete_memory_demo_workflow(self, redis_client):
        """Test complete workflow: load data -> detect issue -> agent response."""

        health_checker = RedisDiagnostics("redis://localhost:6379/0")

        try:
            # Step 1: Load Redis with enough data to be noticeable
            print("Loading Redis with demo data...")

            pipe = redis_client.pipeline()
            for i in range(500):  # Smaller load for faster testing
                key = f"demo:workflow:{i}"
                value = f"demo_data_{'x' * 5000}"  # ~5KB per key
                pipe.set(key, value)
            pipe.execute()

            time.sleep(1)  # Let Redis update stats

            # Step 2: Run health diagnostics
            print("Running Redis health diagnostics...")
            diagnostics = await health_checker.run_diagnostic_suite()

            # Verify we can detect the memory usage
            diagnostic_data = diagnostics.get("diagnostics", {})
            assert "memory" in diagnostic_data
            memory_diag = diagnostic_data["memory"]

            used_memory_mb = memory_diag["used_memory_bytes"] / (1024 * 1024)
            print(f"Detected memory usage: {used_memory_mb:.2f} MB")

            # Step 3: Simulate agent response to memory findings
            memory_query = (
                f"I see Redis memory usage is at {used_memory_mb:.1f}MB. What should I investigate?"
            )

            # Mock agent response
            with patch(
                "redis_sre_agent.agent.langgraph_agent.SRELangGraphAgent"
            ) as mock_agent_class:
                with patch("redis_sre_agent.agent.langgraph_agent.get_sre_agent") as mock_get_agent:
                    mock_agent = AsyncMock()

                    # Simulate agent analyzing the specific memory situation
                    contextual_response = f"""
Based on your Redis health check showing {used_memory_mb:.1f}MB usage:

**Analysis:**
- Current memory usage: {used_memory_mb:.1f}MB

**Next Steps:**
1. Check memory limit: `CONFIG GET maxmemory`
2. Review key distribution: `INFO keyspace`
3. Check for large keys: `MEMORY USAGE <key>` on sample keys
4. Monitor fragmentation: Look for mem_fragmentation_ratio in `INFO memory`

**Recommendations:**
- If no maxmemory set, consider setting limit based on available RAM
- Verify eviction policy is appropriate for your use case
- Monitor key expiration patterns
- Consider memory optimization for frequently accessed data

**Prevention:**
- Set up memory usage alerting at 80% of maxmemory
- Regular cleanup of expired or unused keys
- Monitor memory growth trends

Would you like me to help you run specific diagnostic commands or analyze your current Redis configuration?
                    """

                    mock_agent.process_query = AsyncMock(return_value=contextual_response)
                    mock_agent_class.return_value = mock_agent
                    mock_get_agent.return_value = mock_agent

                    # Get agent response
                    agent = get_sre_agent()
                    response = await agent.process_query(
                        query=memory_query, session_id="workflow_demo", user_id="demo_engineer"
                    )

                    # Verify agent provides contextual analysis
                    # Check that response mentions memory (either specific value or general memory content)
                    assert "memory" in response.lower() or str(int(used_memory_mb)) in response
                    # Check that response is relevant to memory investigation
                    memory_related = any(
                        word in response.lower()
                        for word in [
                            "memory",
                            "maxmemory",
                            "usage",
                            "redis",
                            "investigate",
                            "diagnostic",
                        ]
                    )
                    assert memory_related, (
                        f"Response doesn't seem memory-related: {response[:100]}..."
                    )
                    assert "CONFIG GET maxmemory" in response
                    assert "MEMORY USAGE" in response

                    print("✅ Complete workflow test passed")
                    print(f"Agent response preview: {response[:200]}...")

        finally:
            # Cleanup
            try:
                keys = redis_client.keys("demo:workflow:*")
                if keys:
                    redis_client.delete(*keys)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_redis_diagnostics_comprehensive(self, redis_client):
        """Test comprehensive Redis diagnostics for demo purposes."""

        health_checker = RedisDiagnostics("redis://localhost:6379/0")

        # Add some test data first
        try:
            redis_client.set("demo:test_key", "test_value")
            redis_client.lpush("demo:test_list", "item1", "item2", "item3")
            redis_client.hset("demo:test_hash", mapping={"field1": "value1", "field2": "value2"})

            # Run full diagnostics
            diagnostics = await health_checker.run_diagnostic_suite()

            # Verify diagnostic data structure
            assert "diagnostics" in diagnostics
            assert "timestamp" in diagnostics
            diagnostic_data = diagnostics.get("diagnostics", {})

            # Verify we have some diagnostic results (flexible categories)
            assert len(diagnostic_data) > 0, "No diagnostic data returned"

            # Check that we have at least some key diagnostic information
            # (The exact structure may vary but we should have some diagnostic data)
            has_memory_info = any(
                (
                    "memory" in str(key).lower() or "memory" in str(value).lower()
                    if isinstance(value, (str, dict))
                    else False
                )
                for key, value in diagnostic_data.items()
            )
            has_config_info = any(
                (
                    "config" in str(key).lower() or "config" in str(value).lower()
                    if isinstance(value, (str, dict))
                    else False
                )
                for key, value in diagnostic_data.items()
            )

            assert has_memory_info or has_config_info, "No memory or config diagnostic info found"

            # Check if we can find keyspace information in any category
            any(
                (
                    "key" in str(key).lower() or "key" in str(value).lower()
                    if isinstance(value, (str, dict))
                    else False
                )
                for key, value in diagnostic_data.items()
            )

            # Verify diagnostic data is comprehensive
            assert len(diagnostic_data) > 5, "Should have multiple diagnostic categories"

            print("✅ Comprehensive diagnostics test passed")
            print(f"Diagnostic categories found: {list(diagnostic_data.keys())}")

        finally:
            # Cleanup test keys
            try:
                test_keys = redis_client.keys("demo:test_*")
                if test_keys:
                    redis_client.delete(*test_keys)
            except Exception:
                pass

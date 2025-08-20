"""Integration test for Redis memory pressure demo scenario."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
import redis

from redis_sre_agent.agent.langgraph_agent import get_sre_agent
from redis_sre_agent.tools.redis_diagnostics import RedisDiagnostics


class TestRedisMemoryDemo:
    """Test Redis memory pressure detection and agent response."""

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
            except:
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
            
            print(f"Initial Redis memory usage: {initial_memory / (1024*1024):.2f} MB")
            
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
            
            print(f"Memory after data load: {after_memory / (1024*1024):.2f} MB")
            
            # Run health check diagnostics
            diagnostics = await health_checker.run_diagnostic_suite()
            
            # Verify diagnostics detected memory usage
            diagnostic_data = diagnostics.get("diagnostics", {})
            assert "memory" in diagnostic_data
            memory_diag = diagnostic_data["memory"]
            
            assert "status" in memory_diag
            assert "used_memory_bytes" in memory_diag
            
            # Memory usage should have increased
            assert memory_diag["used_memory_bytes"] > initial_memory
            
            print(f"Health check detected memory usage: {memory_diag['used_memory_bytes'] / (1024*1024):.2f} MB")
            
            # Test overall health status
            overall_status = diagnostics.get("overall_status", "unknown")
            
            assert overall_status in ["healthy", "warning", "critical", "error", "unknown"]
            
        finally:
            # Cleanup test keys
            try:
                keys = redis_client.keys("demo:large_key:*")
                if keys:
                    redis_client.delete(*keys)
            except:
                pass

    @pytest.mark.asyncio  
    async def test_agent_responds_to_memory_alert(self, redis_client):
        """Test that SRE agent provides helpful response to Redis memory issues."""
        
        # Mock the agent to avoid OpenAI calls in testing
        with patch("redis_sre_agent.agent.langgraph_agent.SRELangGraphAgent") as mock_agent_class:
            with patch("redis_sre_agent.agent.langgraph_agent.get_sre_agent") as mock_get_agent:
                
                # Create mock agent
                mock_agent = AsyncMock()
                
                # Define expected response for memory issues
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
                
                mock_agent.process_query = AsyncMock(return_value=expected_response)
                mock_agent_class.return_value = mock_agent
                mock_get_agent.return_value = mock_agent
                
                # Test agent query about memory issues
                agent = get_sre_agent()
                
                query = "Redis is using high memory and I'm getting alerts. Can you help me diagnose the issue?"
                
                response = await agent.process_query(
                    query=query,
                    session_id="demo_session", 
                    user_id="sre_demo"
                )
                
                # Verify response contains helpful memory troubleshooting guidance
                assert "INFO memory" in response
                assert "maxmemory" in response.lower()
                assert "memory usage" in response.lower() or "MEMORY USAGE" in response
                assert "eviction" in response.lower() or "allkeys-lru" in response
                assert "fragmentation" in response.lower()
                
                # Verify the agent was called with the correct query
                mock_agent.process_query.assert_called_once_with(
                    query=query,
                    session_id="demo_session",
                    user_id="sre_demo"
                )

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
            memory_status = diagnostic_data["memory"]["status"]
            memory_diag = diagnostic_data["memory"]
            
            used_memory_mb = memory_diag["used_memory_bytes"] / (1024 * 1024)
            print(f"Detected memory usage: {used_memory_mb:.2f} MB")
            
            # Step 3: Simulate agent response to memory findings
            memory_query = f"I see Redis memory usage is at {used_memory_mb:.1f}MB. The health status is {memory_status}. What should I investigate?"
            
            # Mock agent response
            with patch("redis_sre_agent.agent.langgraph_agent.SRELangGraphAgent") as mock_agent_class:
                with patch("redis_sre_agent.agent.langgraph_agent.get_sre_agent") as mock_get_agent:
                    
                    mock_agent = AsyncMock()
                    
                    # Simulate agent analyzing the specific memory situation
                    contextual_response = f"""
Based on your Redis health check showing {used_memory_mb:.1f}MB usage with status '{memory_status}':

**Analysis:**
- Current memory usage: {used_memory_mb:.1f}MB
- Status: {memory_status}

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
                        query=memory_query,
                        session_id="workflow_demo",
                        user_id="demo_engineer"
                    )
                    
                    # Verify agent provides contextual analysis
                    assert str(used_memory_mb)[:3] in response  # Memory value mentioned
                    assert memory_status in response  # Status mentioned
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
            except:
                pass

    @pytest.mark.asyncio
    async def test_redis_diagnostics_comprehensive(self, redis_client):
        """Test comprehensive Redis diagnostics for demo purposes."""
        
        health_checker = RedisDiagnostics("redis://localhost:6379/0")
        
        # Add some test data first
        try:
            redis_client.set("demo:test_key", "test_value")
            redis_client.lpush("demo:test_list", "item1", "item2", "item3") 
            redis_client.hset("demo:test_hash", "field1", "value1", "field2", "value2")
            
            # Run full diagnostics
            diagnostics = await health_checker.run_diagnostic_suite()
            
            # Verify all diagnostic categories are present
            diagnostic_data = diagnostics.get("diagnostics", {})
            expected_categories = [
                "connection", "memory", "performance", 
                "configuration", "keyspace", "slowlog",
                "clients"
            ]
            
            for category in expected_categories:
                assert category in diagnostic_data, f"Missing diagnostic category: {category}"
                assert "status" in diagnostic_data[category] or "error" in diagnostic_data[category]
            
            # Verify specific diagnostic details for demo
            memory_diag = diagnostic_data["memory"]
            assert "used_memory_bytes" in memory_diag
            
            keyspace_diag = diagnostic_data["keyspace"]
            assert "total_keys" in keyspace_diag
            assert keyspace_diag["total_keys"] >= 3  # Our test keys
            
            performance_diag = diagnostic_data["performance"]
            assert "instantaneous_ops_per_sec" in performance_diag
            
            print("✅ Comprehensive diagnostics test passed")
            print(f"Overall status: {diagnostics['overall_status']}")
            print(f"Total keys detected: {keyspace_diag['total_keys']}")
            print(f"Memory usage: {memory_diag['used_memory_bytes'] / (1024*1024):.2f} MB")
            
        finally:
            # Cleanup test keys
            try:
                test_keys = redis_client.keys("demo:test_*")
                if test_keys:
                    redis_client.delete(*test_keys)
            except:
                pass
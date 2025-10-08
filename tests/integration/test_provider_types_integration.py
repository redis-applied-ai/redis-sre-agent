"""Integration tests for provider types with real Redis instance."""

import pytest

from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.models.provider_config import (
    RedisDirectDiagnosticsConfig,
    RedisDirectMetricsConfig,
)
from redis_sre_agent.tools.provider_types.redis_direct_diagnostics import (
    RedisDirectDiagnosticsProviderType,
)
from redis_sre_agent.tools.provider_types.redis_direct_metrics import (
    RedisDirectMetricsProviderType,
)


def create_test_instance(redis_url: str, name: str = "test-redis") -> RedisInstance:
    """Helper to create test instance bypassing validation.

    Uses model_construct to bypass validators since test Redis URL
    may match the application's Redis URL in test environment.
    """
    return RedisInstance.model_construct(
        id="test-1",
        name=name,
        connection_url=redis_url,
        environment="testing",
        usage="cache",
        description="Test instance",
        created_by="user",
    )


@pytest.mark.integration
class TestRedisDirectMetricsProviderTypeIntegration:
    """Integration tests for Redis direct metrics provider type with real Redis."""

    @pytest.mark.asyncio
    async def test_list_metrics_tool_execution(self, redis_url, async_redis_client):
        """Test executing the list_metrics tool against real Redis."""
        # Set up some data in Redis
        await async_redis_client.set("test:key1", "value1")
        await async_redis_client.set("test:key2", "value2")

        # Create provider and instance
        config = RedisDirectMetricsConfig()
        provider = RedisDirectMetricsProviderType(config)
        instance = create_test_instance(redis_url)

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        list_metrics_tool = next(t for t in tools if "list_metrics" in t.name)

        # Execute the tool
        result = await list_metrics_tool.function()

        # Verify results
        assert isinstance(result, list)
        assert len(result) > 0

        # Check that we got metric definitions
        metric_names = [m["name"] for m in result]
        assert "used_memory" in metric_names
        assert "connected_clients" in metric_names

    @pytest.mark.asyncio
    async def test_query_metrics_tool_execution(self, redis_url, async_redis_client):
        """Test executing the query_metrics tool against real Redis."""
        # Set up some data
        await async_redis_client.set("test:key1", "value1")

        # Create provider and instance
        config = RedisDirectMetricsConfig()
        provider = RedisDirectMetricsProviderType(config)
        instance = create_test_instance(redis_url)

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        query_metrics_tool = next(t for t in tools if "query_metrics" in t.name)

        # Execute the tool
        result = await query_metrics_tool.function(
            metric_names=["used_memory", "connected_clients"]
        )

        # Verify results
        assert "instance" in result
        assert result["instance"] == "test-redis"
        assert "metrics" in result
        assert "used_memory" in result["metrics"]
        assert "connected_clients" in result["metrics"]

        # Check metric structure
        used_memory = result["metrics"]["used_memory"]
        assert "value" in used_memory
        assert "timestamp" in used_memory

    @pytest.mark.asyncio
    async def test_get_summary_tool_execution(self, redis_url, async_redis_client):
        """Test executing the get_summary tool against real Redis."""
        # Set up some data
        await async_redis_client.set("test:key1", "value1")
        await async_redis_client.set("test:key2", "value2")

        # Create provider and instance
        config = RedisDirectMetricsConfig()
        provider = RedisDirectMetricsProviderType(config)
        instance = create_test_instance(redis_url)

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        summary_tool = next(t for t in tools if "get_summary" in t.name)

        # Execute the tool with specific sections
        result = await summary_tool.function(sections=["memory", "performance"])

        # Verify results
        assert "instance" in result
        assert result["instance"] == "test-redis"
        assert "sections" in result
        assert "memory" in result["sections"]
        assert "performance" in result["sections"]

        # Check that memory section has metrics
        memory_metrics = result["sections"]["memory"]
        assert len(memory_metrics) > 0

        # Check metric structure
        for metric_name, metric_data in memory_metrics.items():
            assert "value" in metric_data
            assert "unit" in metric_data
            assert "description" in metric_data

    @pytest.mark.asyncio
    async def test_query_nonexistent_metric(self, redis_url, async_redis_client):
        """Test querying a metric that doesn't exist."""
        # Create provider and instance
        config = RedisDirectMetricsConfig()
        provider = RedisDirectMetricsProviderType(config)
        instance = create_test_instance(redis_url)

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        query_metrics_tool = next(t for t in tools if "query_metrics" in t.name)

        # Execute the tool with nonexistent metric
        result = await query_metrics_tool.function(metric_names=["nonexistent_metric"])

        # Verify error handling
        assert "metrics" in result
        assert "nonexistent_metric" in result["metrics"]
        assert "error" in result["metrics"]["nonexistent_metric"]


@pytest.mark.integration
class TestRedisDirectDiagnosticsProviderTypeIntegration:
    """Integration tests for Redis direct diagnostics provider type with real Redis."""

    @pytest.mark.asyncio
    async def test_capture_diagnostics_tool_execution(self, redis_url, async_redis_client):
        """Test executing the capture_diagnostics tool against real Redis."""
        # Set up some test data
        await async_redis_client.set("test:key1", "value1")
        await async_redis_client.set("test:key2", "value2")
        await async_redis_client.setex("test:expiring", 3600, "value")

        # Create provider and instance
        config = RedisDirectDiagnosticsConfig()
        provider = RedisDirectDiagnosticsProviderType(config)
        instance = create_test_instance(redis_url)

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        capture_tool = next(t for t in tools if "capture_diagnostics" in t.name)

        # Execute the tool
        result = await capture_tool.function()

        # Verify results
        assert result["capture_status"] == "success"
        assert "diagnostics" in result
        assert "connection" in result["diagnostics"]
        assert "memory" in result["diagnostics"]
        assert "performance" in result["diagnostics"]
        assert "keyspace" in result["diagnostics"]

    @pytest.mark.asyncio
    async def test_capture_sections_tool_execution(self, redis_url, async_redis_client):
        """Test executing the capture_sections tool against real Redis."""
        # Set up some test data
        await async_redis_client.set("test:key1", "value1")

        # Create provider and instance
        config = RedisDirectDiagnosticsConfig()
        provider = RedisDirectDiagnosticsProviderType(config)
        instance = create_test_instance(redis_url)

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        sections_tool = next(t for t in tools if "capture_sections" in t.name)

        # Execute the tool with specific sections
        result = await sections_tool.function(sections=["memory", "keyspace"])

        # Verify results
        assert result["capture_status"] == "success"
        assert "diagnostics" in result
        assert "memory" in result["diagnostics"]
        assert "keyspace" in result["diagnostics"]
        # Should not have other sections
        assert "performance" not in result["diagnostics"]

    @pytest.mark.asyncio
    async def test_sample_keys_tool_execution(self, redis_url, async_redis_client):
        """Test executing the sample_keys tool against real Redis."""
        # Set up test data with patterns
        await async_redis_client.set("user:1", "alice")
        await async_redis_client.set("user:2", "bob")
        await async_redis_client.set("session:abc", "data1")
        await async_redis_client.set("session:def", "data2")
        await async_redis_client.set("cache:x", "cached")

        # Create provider and instance
        config = RedisDirectDiagnosticsConfig()
        provider = RedisDirectDiagnosticsProviderType(config)
        instance = create_test_instance(redis_url)

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        sample_tool = next(t for t in tools if "sample_keys" in t.name)

        # Execute the tool
        result = await sample_tool.function(pattern="*", count=100, database=0)

        # Verify results
        assert result["success"] is True
        assert result["instance"] == "test-redis"
        assert result["database"] == 0
        assert result["pattern"] == "*"
        assert result["sampled_count"] >= 5  # We created 5 keys
        assert "sampled_keys" in result
        assert "key_patterns" in result

        # Check that patterns were identified
        patterns = result["key_patterns"]
        assert "user" in patterns
        assert "session" in patterns
        assert "cache" in patterns

    @pytest.mark.asyncio
    async def test_analyze_keys_tool_execution(self, redis_url, async_redis_client):
        """Test executing the analyze_keys tool against real Redis."""
        # Set up diverse test data
        await async_redis_client.set("string:1", "value1")
        await async_redis_client.set("string:2", "value2")
        await async_redis_client.setex("expiring:1", 3600, "expires in 1h")
        await async_redis_client.setex("expiring:2", 86400, "expires in 1d")
        await async_redis_client.hset("hash:1", mapping={"field1": "val1", "field2": "val2"})
        await async_redis_client.lpush("list:1", "item1", "item2", "item3")
        await async_redis_client.sadd("set:1", "member1", "member2")

        # Create provider and instance
        config = RedisDirectDiagnosticsConfig()
        provider = RedisDirectDiagnosticsProviderType(config)
        instance = create_test_instance(redis_url)

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        analyze_tool = next(t for t in tools if "analyze_keys" in t.name)

        # Execute the tool
        result = await analyze_tool.function(pattern="*", sample_size=100, database=0)

        # Verify results
        assert result["success"] is True
        assert result["instance"] == "test-redis"
        assert "keyspace_summary" in result
        assert "sample_analysis" in result

        # Check keyspace summary
        summary = result["keyspace_summary"]
        assert summary["total_keys"] >= 7  # We created at least 7 keys
        assert summary["keys_with_ttl"] >= 2  # We created 2 keys with TTL
        assert "avg_ttl_seconds" in summary

        # Check sample analysis
        analysis = result["sample_analysis"]
        assert "type_distribution" in analysis
        assert "ttl_distribution" in analysis

        # Check type distribution
        types = analysis["type_distribution"]
        assert "string" in types
        assert "hash" in types
        assert "list" in types
        assert "set" in types

        # Check TTL distribution
        ttl_dist = analysis["ttl_distribution"]
        # We created 2 keys with TTL, so at least one bucket should have keys
        keys_with_ttl_in_sample = (
            ttl_dist["0_to_1h"] + ttl_dist["1h_to_1d"] + ttl_dist["1d_to_7d"] + ttl_dist["7d_plus"]
        )
        assert keys_with_ttl_in_sample >= 1  # At least one key with TTL
        assert ttl_dist["no_expiry"] >= 4  # string:1, string:2, hash:1, list:1, set:1

    @pytest.mark.asyncio
    async def test_sample_keys_with_pattern(self, redis_url, async_redis_client):
        """Test sampling keys with a specific pattern."""
        # Set up keys with different patterns
        await async_redis_client.set("user:1", "alice")
        await async_redis_client.set("user:2", "bob")
        await async_redis_client.set("session:abc", "data1")
        await async_redis_client.set("cache:x", "cached")

        # Create provider and instance
        config = RedisDirectDiagnosticsConfig()
        provider = RedisDirectDiagnosticsProviderType(config)
        instance = create_test_instance(redis_url)

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        sample_tool = next(t for t in tools if "sample_keys" in t.name)

        # Execute with pattern
        result = await sample_tool.function(pattern="user:*", count=100)

        # Verify only user keys returned
        assert result["success"] is True
        assert result["pattern"] == "user:*"
        sampled_keys = result["sampled_keys"]

        # All sampled keys should match pattern
        for key in sampled_keys:
            assert key.startswith("user:")

    @pytest.mark.asyncio
    async def test_analyze_keys_with_pattern(self, redis_url, async_redis_client):
        """Test analyzing keys with a specific pattern."""
        # Set up keys
        await async_redis_client.set("cache:1", "value1")
        await async_redis_client.set("cache:2", "value2")
        await async_redis_client.setex("cache:3", 3600, "expires")
        await async_redis_client.set("other:1", "other")

        # Create provider and instance
        config = RedisDirectDiagnosticsConfig()
        provider = RedisDirectDiagnosticsProviderType(config)
        instance = create_test_instance(redis_url)

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        analyze_tool = next(t for t in tools if "analyze_keys" in t.name)

        # Execute with pattern
        result = await analyze_tool.function(pattern="cache:*", sample_size=100)

        # Verify analysis focused on cache keys
        assert result["success"] is True
        assert result["pattern"] == "cache:*"

        # Should have analyzed cache keys
        analysis = result["sample_analysis"]
        assert analysis["sampled_count"] >= 3

    @pytest.mark.asyncio
    async def test_analyze_keys_different_database(self, redis_url, async_redis_client):
        """Test analyzing keys in a different database."""
        # Set up keys in database 1
        await async_redis_client.select(1)
        await async_redis_client.set("db1:key1", "value1")
        await async_redis_client.set("db1:key2", "value2")
        await async_redis_client.select(0)  # Switch back

        # Create provider and instance
        config = RedisDirectDiagnosticsConfig()
        provider = RedisDirectDiagnosticsProviderType(config)
        instance = create_test_instance(redis_url)

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        analyze_tool = next(t for t in tools if "analyze_keys" in t.name)

        # Execute on database 1
        result = await analyze_tool.function(pattern="*", sample_size=100, database=1)

        # Verify correct database
        assert result["success"] is True
        assert result["database"] == 1

        # Should have found keys in db1
        summary = result["keyspace_summary"]
        assert summary["total_keys"] >= 2

    @pytest.mark.asyncio
    async def test_analyze_keys_with_invalid_url(self):
        """Test error handling in analyze_keys with invalid Redis URL."""
        # Create provider and instance with invalid URL
        config = RedisDirectDiagnosticsConfig()
        provider = RedisDirectDiagnosticsProviderType(config)
        instance = create_test_instance("redis://invalid-host:9999", "invalid-redis")

        # Create tools
        tools = provider.create_tools_scoped_to_instance(instance)
        analyze_tool = next(t for t in tools if "analyze_keys" in t.name)

        # Execute the tool - should handle error gracefully
        result = await analyze_tool.function(pattern="*", sample_size=100)

        # Verify error handling
        assert result["success"] is False
        assert "error" in result
        assert result["instance"] == "invalid-redis"

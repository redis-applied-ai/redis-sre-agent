"""Tests for Redis CLI diagnostics tool provider."""

import pytest
from testcontainers.redis import RedisContainer

from redis_sre_agent.tools.diagnostics.redis_cli import (
    RedisCliToolProvider,
)


@pytest.fixture(scope="module")
def redis_container():
    """Start a Redis container for testing."""
    with RedisContainer("redis:8.2.1") as redis:
        yield redis


@pytest.fixture
def redis_url(redis_container):
    """Get Redis connection URL from container."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}"


@pytest.mark.asyncio
async def test_provider_initialization(redis_url):
    """Test that provider initializes correctly."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        assert provider.provider_name == "redis_cli"
        assert provider.connection_url == redis_url


@pytest.mark.asyncio
async def test_create_tool_schemas(redis_url):
    """Test that tool schemas are created correctly."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        schemas = provider.create_tool_schemas()

        assert len(schemas) == 11  # All 11 diagnostic tools

        # Check tool names
        tool_names = [schema.name for schema in schemas]
        assert any("info" in name for name in tool_names)
        assert any("slowlog" in name for name in tool_names)
        assert any("acl_log" in name for name in tool_names)
        assert any("config_get" in name for name in tool_names)
        assert any("client_list" in name for name in tool_names)
        # NOTE: memory_doctor and latency_doctor removed (not available in Redis Cloud)
        assert any("sample_keys" in name for name in tool_names)
        assert any("search_indexes" in name for name in tool_names)
        assert any("search_index_info" in name for name in tool_names)
        assert any("cluster_info" in name for name in tool_names)
        assert any("replication_info" in name for name in tool_names)
        assert any("memory_stats" in name for name in tool_names)

        # Check that all have proper structure
        for schema in schemas:
            assert schema.name
            assert schema.description
            assert schema.parameters
            assert "type" in schema.parameters
            assert schema.parameters["type"] == "object"


@pytest.mark.asyncio
async def test_info_command(redis_url):
    """Test INFO command execution."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        # Test without section
        result = await provider.info()
        assert result["status"] == "success"
        assert "data" in result
        assert result["section"] == "all"

        # Test with section
        result = await provider.info(section="server")
        assert result["status"] == "success"
        assert result["section"] == "server"


@pytest.mark.asyncio
async def test_slowlog_command(redis_url):
    """Test SLOWLOG command execution."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        result = await provider.slowlog(count=5)

        assert result["status"] == "success"
        assert "entries" in result
        assert "count" in result
        assert isinstance(result["entries"], list)


@pytest.mark.asyncio
async def test_config_get_command(redis_url):
    """Test CONFIG GET command execution."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        result = await provider.config_get(pattern="maxmemory")

        assert result["status"] == "success"
        assert "config" in result
        assert result["pattern"] == "maxmemory"


@pytest.mark.asyncio
async def test_client_list_command(redis_url):
    """Test CLIENT LIST command execution."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        result = await provider.client_list()

        assert result["status"] == "success"
        assert "clients" in result
        assert "count" in result
        assert isinstance(result["clients"], list)


@pytest.mark.asyncio
async def test_memory_stats_command(redis_url):
    """Test MEMORY STATS command execution."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        result = await provider.memory_stats()

        assert result["status"] == "success"
        assert "stats" in result


@pytest.mark.asyncio
async def test_replication_info_command(redis_url):
    """Test replication info command execution."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        result = await provider.replication_info()

        assert result["status"] == "success"
        assert "info" in result
        assert "role" in result


@pytest.mark.asyncio
async def test_resolve_tool_call_info(redis_url):
    """Test resolving info tool call."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        tool_name = provider._make_tool_name("info")

        result = await provider.resolve_tool_call(tool_name=tool_name, args={"section": "memory"})

        assert result["status"] == "success"
        assert result["section"] == "memory"


@pytest.mark.asyncio
async def test_resolve_tool_call_slowlog(redis_url):
    """Test resolving slowlog tool call."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        tool_name = provider._make_tool_name("slowlog")

        result = await provider.resolve_tool_call(tool_name=tool_name, args={"count": 10})

        assert result["status"] == "success"
        assert "entries" in result


@pytest.mark.asyncio
async def test_provider_with_redis_instance(redis_url):
    """Test that provider works with a Redis instance context."""
    from redis_sre_agent.api.instances import RedisInstance

    redis_instance = RedisInstance(
        id="test-redis",
        name="Test Redis",
        connection_url=redis_url,
        environment="test",
        usage="cache",
        description="Test instance",
    )

    async with RedisCliToolProvider(redis_instance=redis_instance) as provider:
        # Tool names should include instance hash
        schemas = provider.create_tool_schemas()
        tool_name = schemas[0].name

        # Should have format: redis_cli_{hash}_info
        parts = tool_name.split("_")
        assert len(parts) >= 3
        assert parts[0] == "redis"
        assert parts[1] == "cli"

        # Should still work
        result = await provider.info()
        assert result["status"] == "success"


@pytest.mark.asyncio
async def test_provider_requires_connection_url_or_instance():
    """Test that provider requires either connection_url or redis_instance."""
    with pytest.raises(
        ValueError, match="Either redis_instance or connection_url must be provided"
    ):
        RedisCliToolProvider()


@pytest.mark.asyncio
async def test_sample_keys(redis_url, redis_container):
    """Test sampling keys from the keyspace."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        # First, populate some test keys
        client = provider.get_client()
        await client.set("test:key1", "value1")
        await client.set("test:key2", "value2")
        await client.lpush("test:list", "item1")
        await client.hset("test:hash", "field", "value")

        # Sample all keys
        result = await provider.sample_keys(count=10, pattern="test:*")

        assert result["status"] == "success"
        assert result["pattern"] == "test:*"
        assert result["requested_count"] == 10
        assert result["sampled_count"] >= 4  # At least the 4 keys we created
        assert "keys" in result
        assert "type_distribution" in result

        # Check that we got key types
        key_names = [k["key"] for k in result["keys"]]
        assert b"test:key1" in key_names or "test:key1" in key_names

        # Check type distribution
        assert "string" in result["type_distribution"]
        assert "list" in result["type_distribution"]
        assert "hash" in result["type_distribution"]

        # Clean up
        await client.delete("test:key1", "test:key2", "test:list", "test:hash")


@pytest.mark.asyncio
async def test_sample_keys_with_pattern(redis_url, redis_container):
    """Test sampling keys with a specific pattern."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        client = provider.get_client()

        # Create keys with different prefixes
        await client.set("user:1", "alice")
        await client.set("user:2", "bob")
        await client.set("session:1", "data")

        # Sample only user keys
        result = await provider.sample_keys(count=10, pattern="user:*")

        assert result["status"] == "success"
        assert result["sampled_count"] >= 2

        # All keys should match the pattern
        for key_info in result["keys"]:
            key = key_info["key"]
            if isinstance(key, bytes):
                key = key.decode()
            assert key.startswith("user:")

        # Clean up
        await client.delete("user:1", "user:2", "session:1")


@pytest.mark.asyncio
async def test_search_indexes(redis_url):
    """Test listing search indexes."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        result = await provider.search_indexes()

        # Should succeed even if no RediSearch module (will return error)
        # or return empty list if module is loaded but no indexes
        assert "status" in result
        if result["status"] == "success":
            assert "indexes" in result
            assert "count" in result
            assert isinstance(result["indexes"], list)
        else:
            # Error case - RediSearch not loaded
            assert "error" in result
            assert "note" in result


@pytest.mark.asyncio
async def test_search_index_info(redis_url):
    """Test getting search index info."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        result = await provider.search_index_info(index_name="test_index")

        # Should return error if index doesn't exist or RediSearch not loaded
        # This is expected behavior
        assert "status" in result
        if result["status"] == "error":
            assert "error" in result
            assert result["index_name"] == "test_index"


@pytest.mark.asyncio
async def test_sample_keys_empty_keyspace(redis_url, redis_container):
    """Test sampling keys when keyspace is empty or pattern matches nothing."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        # Sample with a pattern that won't match anything
        result = await provider.sample_keys(count=10, pattern="nonexistent:*")

        assert result["status"] == "success"
        assert result["pattern"] == "nonexistent:*"
        assert result["sampled_count"] == 0
        assert result["keys"] == []
        assert result["type_distribution"] == {}


@pytest.mark.asyncio
async def test_sample_keys_count_limit(redis_url, redis_container):
    """Test that sample_keys respects the count limit."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        client = provider.get_client()

        # Create more keys than we'll sample
        for i in range(20):
            await client.set(f"limit:test:{i}", f"value{i}")

        # Sample only 5 keys
        result = await provider.sample_keys(count=5, pattern="limit:test:*")

        assert result["status"] == "success"
        assert result["requested_count"] == 5
        assert result["sampled_count"] == 5
        assert len(result["keys"]) == 5

        # Clean up
        for i in range(20):
            await client.delete(f"limit:test:{i}")


@pytest.mark.asyncio
async def test_sample_keys_type_distribution(redis_url, redis_container):
    """Test that type distribution is calculated correctly."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        client = provider.get_client()

        # Create keys of different types
        await client.set("dist:string1", "value")
        await client.set("dist:string2", "value")
        await client.lpush("dist:list1", "item")
        await client.sadd("dist:set1", "member")
        await client.zadd("dist:zset1", {"member": 1.0})
        await client.hset("dist:hash1", "field", "value")

        result = await provider.sample_keys(count=10, pattern="dist:*")

        assert result["status"] == "success"
        assert result["sampled_count"] == 6

        # Check type distribution
        dist = result["type_distribution"]
        assert dist.get("string", 0) == 2
        assert dist.get("list", 0) == 1
        assert dist.get("set", 0) == 1
        assert dist.get("zset", 0) == 1
        assert dist.get("hash", 0) == 1

        # Clean up
        await client.delete(
            "dist:string1", "dist:string2", "dist:list1", "dist:set1", "dist:zset1", "dist:hash1"
        )


@pytest.mark.asyncio
async def test_resolve_tool_call_sample_keys(redis_url, redis_container):
    """Test routing for sample_keys tool."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        client = provider.get_client()
        await client.set("route:test", "value")

        schemas = provider.create_tool_schemas()
        sample_keys_tool = [s for s in schemas if "sample_keys" in s.name][0]

        result = await provider.resolve_tool_call(
            sample_keys_tool.name, {"count": 5, "pattern": "route:*"}
        )

        assert result["status"] == "success"
        assert result["pattern"] == "route:*"
        assert result["sampled_count"] >= 1

        await client.delete("route:test")


@pytest.mark.asyncio
async def test_resolve_tool_call_search_indexes(redis_url):
    """Test routing for search_indexes tool."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        schemas = provider.create_tool_schemas()
        search_indexes_tool = [s for s in schemas if "search_indexes" in s.name][0]

        result = await provider.resolve_tool_call(search_indexes_tool.name, {})

        assert "status" in result
        # Will succeed or fail depending on RediSearch availability
        if result["status"] == "success":
            assert "indexes" in result
            assert "count" in result
        else:
            assert "error" in result


@pytest.mark.asyncio
async def test_resolve_tool_call_search_index_info(redis_url):
    """Test routing for search_index_info tool."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        schemas = provider.create_tool_schemas()
        search_info_tool = [s for s in schemas if "search_index_info" in s.name][0]

        result = await provider.resolve_tool_call(search_info_tool.name, {"index_name": "test_idx"})

        assert "status" in result
        assert "index_name" in result
        assert result["index_name"] == "test_idx"


@pytest.mark.asyncio
async def test_sample_keys_default_parameters(redis_url, redis_container):
    """Test sample_keys with default parameters."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        client = provider.get_client()

        # Create a few test keys
        await client.set("default:1", "value")
        await client.set("default:2", "value")

        # Call with defaults (count=100, pattern="*")
        result = await provider.sample_keys()

        assert result["status"] == "success"
        assert result["pattern"] == "*"
        assert result["requested_count"] == 100
        assert result["sampled_count"] >= 2  # At least our test keys

        # Clean up
        await client.delete("default:1", "default:2")


@pytest.mark.asyncio
async def test_sample_keys_with_bytes_keys(redis_url, redis_container):
    """Test that sample_keys handles byte-encoded keys properly."""
    async with RedisCliToolProvider(connection_url=redis_url) as provider:
        client = provider.get_client()

        # Create keys (redis-py returns bytes by default)
        await client.set("bytes:test:1", "value")
        await client.set("bytes:test:2", "value")

        result = await provider.sample_keys(count=10, pattern="bytes:test:*")

        assert result["status"] == "success"
        assert result["sampled_count"] >= 2

        # Keys should be present (either as bytes or strings)
        keys = result["keys"]
        assert len(keys) >= 2

        # Each key should have 'key' and 'type' fields
        for key_info in keys:
            assert "key" in key_info
            assert "type" in key_info
            assert key_info["type"] == "string"

        # Clean up
        await client.delete("bytes:test:1", "bytes:test:2")


@pytest.mark.asyncio
async def test_sample_keys_error_handling():
    """Test sample_keys error handling with invalid connection."""
    # Use an invalid connection URL to trigger error
    async with RedisCliToolProvider(connection_url="redis://invalid-host:9999") as provider:
        result = await provider.sample_keys(count=10, pattern="*")

        assert result["status"] == "error"
        assert "error" in result
        assert result["pattern"] == "*"


@pytest.mark.asyncio
async def test_search_indexes_error_handling():
    """Test search_indexes error handling with invalid connection."""
    # Use an invalid connection URL to trigger error
    async with RedisCliToolProvider(connection_url="redis://invalid-host:9999") as provider:
        result = await provider.search_indexes()

        assert result["status"] == "error"
        assert "error" in result
        assert "note" in result


@pytest.mark.asyncio
async def test_search_index_info_error_handling():
    """Test search_index_info error handling with invalid connection."""
    # Use an invalid connection URL to trigger error
    async with RedisCliToolProvider(connection_url="redis://invalid-host:9999") as provider:
        result = await provider.search_index_info(index_name="test_index")

        assert result["status"] == "error"
        assert "error" in result
        assert result["index_name"] == "test_index"
        assert "note" in result

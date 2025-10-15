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

        assert len(schemas) == 10  # All 10 diagnostic tools

        # Check tool names
        tool_names = [schema.name for schema in schemas]
        assert any("info" in name for name in tool_names)
        assert any("slowlog" in name for name in tool_names)
        assert any("acl_log" in name for name in tool_names)
        assert any("config_get" in name for name in tool_names)
        assert any("client_list" in name for name in tool_names)
        assert any("memory_doctor" in name for name in tool_names)
        assert any("latency_doctor" in name for name in tool_names)
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

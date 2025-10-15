"""Tests for Redis CLI diagnostics tool provider."""

import pytest

from redis_sre_agent.tools.diagnostics.redis_cli import (
    RedisCliConfig,
    RedisCliToolProvider,
)


@pytest.fixture
def redis_cli_config():
    """Create a test Redis CLI configuration."""
    return RedisCliConfig(connection_url="redis://localhost:6379")


@pytest.mark.asyncio
async def test_provider_initialization(redis_cli_config):
    """Test that provider initializes correctly."""
    async with RedisCliToolProvider(config=redis_cli_config) as provider:
        assert provider.provider_name == "redis_cli"
        assert provider.config.connection_url == "redis://localhost:6379"


@pytest.mark.asyncio
async def test_create_tool_schemas(redis_cli_config):
    """Test that tool schemas are created correctly."""
    async with RedisCliToolProvider(config=redis_cli_config) as provider:
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
async def test_info_command(redis_cli_config):
    """Test INFO command execution."""
    async with RedisCliToolProvider(config=redis_cli_config) as provider:
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
async def test_slowlog_command(redis_cli_config):
    """Test SLOWLOG command execution."""
    async with RedisCliToolProvider(config=redis_cli_config) as provider:
        result = await provider.slowlog(count=5)

        assert result["status"] == "success"
        assert "entries" in result
        assert "count" in result
        assert isinstance(result["entries"], list)


@pytest.mark.asyncio
async def test_config_get_command(redis_cli_config):
    """Test CONFIG GET command execution."""
    async with RedisCliToolProvider(config=redis_cli_config) as provider:
        result = await provider.config_get(pattern="maxmemory")

        assert result["status"] == "success"
        assert "config" in result
        assert result["pattern"] == "maxmemory"


@pytest.mark.asyncio
async def test_client_list_command(redis_cli_config):
    """Test CLIENT LIST command execution."""
    async with RedisCliToolProvider(config=redis_cli_config) as provider:
        result = await provider.client_list()

        assert result["status"] == "success"
        assert "clients" in result
        assert "count" in result
        assert isinstance(result["clients"], list)


@pytest.mark.asyncio
async def test_memory_stats_command(redis_cli_config):
    """Test MEMORY STATS command execution."""
    async with RedisCliToolProvider(config=redis_cli_config) as provider:
        result = await provider.memory_stats()

        assert result["status"] == "success"
        assert "stats" in result


@pytest.mark.asyncio
async def test_replication_info_command(redis_cli_config):
    """Test replication info command execution."""
    async with RedisCliToolProvider(config=redis_cli_config) as provider:
        result = await provider.replication_info()

        assert result["status"] == "success"
        assert "info" in result
        assert "role" in result


@pytest.mark.asyncio
async def test_resolve_tool_call_info(redis_cli_config):
    """Test resolving info tool call."""
    async with RedisCliToolProvider(config=redis_cli_config) as provider:
        tool_name = provider._make_tool_name("info")

        result = await provider.resolve_tool_call(tool_name=tool_name, args={"section": "memory"})

        assert result["status"] == "success"
        assert result["section"] == "memory"


@pytest.mark.asyncio
async def test_resolve_tool_call_slowlog(redis_cli_config):
    """Test resolving slowlog tool call."""
    async with RedisCliToolProvider(config=redis_cli_config) as provider:
        tool_name = provider._make_tool_name("slowlog")

        result = await provider.resolve_tool_call(tool_name=tool_name, args={"count": 10})

        assert result["status"] == "success"
        assert "entries" in result


@pytest.mark.asyncio
async def test_provider_with_redis_instance(redis_cli_config):
    """Test that provider works with a Redis instance context."""
    from redis_sre_agent.api.instances import RedisInstance

    redis_instance = RedisInstance(
        id="test-redis",
        name="Test Redis",
        connection_url="redis://localhost:6379",
        environment="test",
        usage="cache",
        description="Test instance",
    )

    async with RedisCliToolProvider(
        config=redis_cli_config, redis_instance=redis_instance
    ) as provider:
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
async def test_load_config_from_env(monkeypatch):
    """Test loading configuration from environment variables."""
    monkeypatch.setenv("TOOLS_REDIS_CLI_CONNECTION_URL", "redis://test:6379")

    config = RedisCliToolProvider._load_config_from_env()

    assert config.connection_url == "redis://test:6379"

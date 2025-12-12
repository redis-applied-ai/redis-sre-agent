"""Integration tests for Redis Command Diagnostics provider with ToolManager."""

import pytest


@pytest.mark.asyncio
async def test_redis_command_provider_loads_via_tool_manager(redis_url):
    """Test that Redis Command provider loads correctly via ToolManager."""
    from redis_sre_agent.core.config import Settings
    from redis_sre_agent.core.instances import RedisInstance

    redis_instance = RedisInstance(
        id="test-redis",
        name="Test Redis",
        connection_url=redis_url,
        environment="test",
        usage="cache",
        description="Test instance",
        instance_type="oss_single",
    )

    # Create settings with Redis CLI provider configured
    settings = Settings()
    settings.tool_providers = [
        "redis_sre_agent.tools.diagnostics.redis_command.provider.RedisCommandToolProvider"
    ]

    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    config_module.settings = settings

    try:
        from redis_sre_agent.tools.manager import ToolManager

        async with ToolManager(redis_instance=redis_instance) as manager:
            tools = manager.get_tools()

            # Should have knowledge base + Redis CLI tools
            tool_names = [t.name for t in tools]

            # Check for Redis CLI tools
            redis_cli_tools = [n for n in tool_names if "redis_cli" in n]
            assert len(redis_cli_tools) == 11, (
                f"Expected 11 Redis CLI tools, got {len(redis_cli_tools)}"
            )

            # Check for specific tools
            assert any("info" in n for n in redis_cli_tools)
            assert any("slowlog" in n for n in redis_cli_tools)
            assert any("acl_log" in n for n in redis_cli_tools)
            assert any("config_get" in n for n in redis_cli_tools)
            assert any("client_list" in n for n in redis_cli_tools)
            # NOTE: memory_doctor and latency_doctor removed (not available in Redis Cloud)
            assert any("cluster_info" in n for n in redis_cli_tools)
            assert any("replication_info" in n for n in redis_cli_tools)
            assert any("memory_stats" in n for n in redis_cli_tools)

    finally:
        config_module.settings = original_settings


@pytest.mark.asyncio
async def test_redis_cli_tool_execution_via_manager(redis_url):
    """Test executing Redis CLI tools via ToolManager."""
    from redis_sre_agent.core.config import Settings
    from redis_sre_agent.core.instances import RedisInstance

    redis_instance = RedisInstance(
        id="test-redis",
        name="Test Redis",
        connection_url=redis_url,
        environment="test",
        usage="cache",
        description="Test instance",
        instance_type="oss_single",
    )

    settings = Settings()
    settings.tool_providers = [
        "redis_sre_agent.tools.diagnostics.redis_command.provider.RedisCommandToolProvider"
    ]

    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    config_module.settings = settings

    try:
        from redis_sre_agent.tools.manager import ToolManager

        async with ToolManager(redis_instance=redis_instance) as manager:
            tools = manager.get_tools()

            # Find the info tool
            info_tool = next(t for t in tools if "redis_cli" in t.name and "info" in t.name)

            # Execute it
            result = await manager.resolve_tool_call(
                tool_name=info_tool.name, args={"section": "server"}
            )

            assert result["status"] == "success"
            assert result["section"] == "server"
            assert "data" in result

    finally:
        config_module.settings = original_settings


@pytest.mark.asyncio
async def test_redis_cli_with_redis_instance(redis_url):
    """Test Redis CLI provider with Redis instance context."""
    from redis_sre_agent.core.config import Settings
    from redis_sre_agent.core.instances import RedisInstance

    settings = Settings()
    settings.tool_providers = [
        "redis_sre_agent.tools.diagnostics.redis_command.provider.RedisCommandToolProvider"
    ]

    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    config_module.settings = settings

    redis_instance = RedisInstance(
        id="test-redis",
        name="Test Redis",
        connection_url=redis_url,
        environment="test",
        usage="cache",
        description="Test instance",
        instance_type="oss_single",
    )

    try:
        from redis_sre_agent.tools.manager import ToolManager

        async with ToolManager(redis_instance=redis_instance) as manager:
            tools = manager.get_tools()

            # Tools should be scoped to the Redis instance
            redis_cli_tools = [t for t in tools if "redis_cli" in t.name]
            assert len(redis_cli_tools) == 11

            # Tool names should include instance hash
            tool_name = redis_cli_tools[0].name
            assert "redis_cli_" in tool_name

            # Execute a tool
            info_tool = next(t for t in tools if "info" in t.name and "redis_cli" in t.name)
            result = await manager.resolve_tool_call(tool_name=info_tool.name, args={})

            assert result["status"] == "success"

    finally:
        config_module.settings = original_settings


@pytest.mark.asyncio
async def test_multiple_providers_coexist(redis_url, monkeypatch):
    """Test that Redis CLI provider works alongside other providers."""
    from redis_sre_agent.core.config import Settings
    from redis_sre_agent.core.instances import RedisInstance

    # Configure both Prometheus and Redis CLI providers
    settings = Settings()
    settings.tool_providers = [
        "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider",
        "redis_sre_agent.tools.diagnostics.redis_command.provider.RedisCommandToolProvider",
    ]

    # Set Prometheus env vars
    monkeypatch.setenv("TOOLS_PROMETHEUS_URL", "http://localhost:9090")

    redis_instance = RedisInstance(
        id="test-redis",
        name="Test Redis",
        connection_url=redis_url,
        environment="test",
        usage="cache",
        description="Test instance",
        instance_type="oss_single",
    )

    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    config_module.settings = settings

    try:
        from redis_sre_agent.tools.manager import ToolManager

        async with ToolManager(redis_instance=redis_instance) as manager:
            tools = manager.get_tools()

            # Should have both knowledge base, Prometheus, and Redis Command tools
            knowledge_tools = [t for t in tools if "knowledge" in t.name]
            prometheus_tools = [t for t in tools if "prometheus" in t.name]
            redis_command_tools = [t for t in tools if "redis_command" in t.name]

            assert len(knowledge_tools) > 0, "Knowledge base tools should be loaded"
            assert len(prometheus_tools) == 3, "Prometheus tools should be loaded"
            assert len(redis_command_tools) == 11, "Redis Command tools should be loaded"

    finally:
        config_module.settings = original_settings


@pytest.mark.asyncio
async def test_default_providers_enabled(redis_url):
    """Test that default providers are enabled in settings."""
    from redis_sre_agent.core.config import Settings

    settings = Settings()

    # Should have both Prometheus and Redis CLI enabled by default
    assert (
        "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider"
        in settings.tool_providers
    )
    assert (
        "redis_sre_agent.tools.diagnostics.redis_command.provider.RedisCommandToolProvider"
        in settings.tool_providers
    )

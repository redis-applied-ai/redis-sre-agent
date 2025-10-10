"""Integration tests for Prometheus provider with ToolManager."""

import time

import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from redis_sre_agent.tools.manager import ToolManager


@pytest.fixture(scope="module")
def prometheus_container():
    """Start Prometheus container for testing."""
    config = """
global:
  scrape_interval: 1s
  evaluation_interval: 1s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
"""

    container = DockerContainer("prom/prometheus:latest")
    container.with_exposed_ports(9090)
    container.with_volume_mapping(
        host="/tmp/prometheus.yml", container="/etc/prometheus/prometheus.yml", mode="ro"
    )

    with open("/tmp/prometheus.yml", "w") as f:
        f.write(config)

    container.start()
    wait_for_logs(container, "Server is ready to receive web requests")
    time.sleep(5)

    yield container

    container.stop()


@pytest.fixture
def prometheus_env(prometheus_container, monkeypatch):
    """Set Prometheus environment variables."""
    port = prometheus_container.get_exposed_port(9090)
    host = prometheus_container.get_container_host_ip()

    monkeypatch.setenv("PROMETHEUS_URL", f"http://{host}:{port}")
    monkeypatch.setenv("PROMETHEUS_DISABLE_SSL", "false")


@pytest.mark.asyncio
async def test_prometheus_provider_loads_via_tool_manager(prometheus_env):
    """Test that Prometheus provider loads correctly via ToolManager."""
    from redis_sre_agent.core.config import Settings

    # Create settings with Prometheus provider configured
    settings = Settings()
    settings.tool_providers = [
        "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider"
    ]

    # Patch settings
    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    config_module.settings = settings

    try:
        async with ToolManager() as manager:
            tools = manager.get_tools()

            # Should have knowledge base tools + Prometheus tools
            tool_names = [t.name for t in tools]

            # Check for Prometheus tools
            prometheus_tools = [n for n in tool_names if "prometheus" in n]
            assert len(prometheus_tools) == 3, (
                f"Expected 3 Prometheus tools, got {len(prometheus_tools)}"
            )

            # Check for specific tools
            assert any(
                "query" in n and "range" not in n and "search" not in n for n in prometheus_tools
            )
            assert any("query_range" in n for n in prometheus_tools)
            assert any("search_metrics" in n for n in prometheus_tools)
    finally:
        config_module.settings = original_settings


@pytest.mark.asyncio
async def test_prometheus_tool_execution_via_manager(prometheus_env, monkeypatch):
    """Test executing Prometheus tools through ToolManager."""
    from redis_sre_agent.core.config import Settings

    settings = Settings()
    settings.tool_providers = [
        "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider"
    ]

    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    config_module.settings = settings

    try:
        async with ToolManager() as manager:
            tools = manager.get_tools()

            # Find the query tool
            query_tool = next(
                (
                    t
                    for t in tools
                    if "prometheus" in t.name and "query" in t.name and "range" not in t.name
                ),
                None,
            )
            assert query_tool is not None, "Prometheus query tool not found"

            # Execute the tool
            result = await manager.resolve_tool_call(
                tool_name=query_tool.name, args={"query": "up"}
            )

            # Verify result
            assert result["status"] == "success"
            assert result["query"] == "up"
            assert "data" in result
            assert isinstance(result["data"], list)
    finally:
        config_module.settings = original_settings


@pytest.mark.asyncio
async def test_prometheus_with_redis_instance(prometheus_env, monkeypatch):
    """Test Prometheus provider with Redis instance context."""
    from redis_sre_agent.api.instances import RedisInstance
    from redis_sre_agent.core.config import Settings

    settings = Settings()
    settings.tool_providers = [
        "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider"
    ]

    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    config_module.settings = settings

    redis_instance = RedisInstance(
        id="test-redis",
        name="Test Redis",
        connection_url="redis://localhost:6379",
        environment="test",
        usage="cache",
        description="Test instance",
    )

    try:
        async with ToolManager(redis_instance=redis_instance) as manager:
            tools = manager.get_tools()

            # Tools should be scoped to the Redis instance
            prometheus_tools = [t for t in tools if "prometheus" in t.name]
            assert len(prometheus_tools) == 3

            # Tool names should include instance hash
            for tool in prometheus_tools:
                parts = tool.name.split("_")
                assert len(parts) >= 3, f"Tool name {tool.name} should have instance hash"
    finally:
        config_module.settings = original_settings


@pytest.mark.asyncio
async def test_prometheus_provider_config_from_env(prometheus_env):
    """Test that Prometheus provider loads config from environment."""
    from redis_sre_agent.tools.metrics.prometheus import PrometheusToolProvider

    # Create provider without explicit config
    provider = PrometheusToolProvider()

    # Should have loaded config from environment
    assert provider.config is not None
    assert "localhost" in provider.config.url or "127.0.0.1" in provider.config.url
    assert not provider.config.disable_ssl


@pytest.mark.asyncio
async def test_multiple_providers_coexist(prometheus_env, monkeypatch):
    """Test that Prometheus provider works alongside other providers."""
    from redis_sre_agent.core.config import Settings

    settings = Settings()
    settings.tool_providers = [
        "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider"
    ]

    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    config_module.settings = settings

    try:
        async with ToolManager() as manager:
            tools = manager.get_tools()

            # Should have both knowledge base and Prometheus tools
            knowledge_tools = [t for t in tools if "knowledge" in t.name]
            prometheus_tools = [t for t in tools if "prometheus" in t.name]

            assert len(knowledge_tools) > 0, "Knowledge base tools should be loaded"
            assert len(prometheus_tools) == 3, "Prometheus tools should be loaded"

            # All tools should be unique
            tool_names = [t.name for t in tools]
            assert len(tool_names) == len(set(tool_names)), "Tool names should be unique"
    finally:
        config_module.settings = original_settings

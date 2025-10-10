"""Integration tests for Prometheus metrics provider using testcontainers."""

import time

import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from redis_sre_agent.tools.metrics.prometheus import (
    PrometheusConfig,
    PrometheusToolProvider,
)


@pytest.fixture(scope="module")
def prometheus_container():
    """Start Prometheus container for testing.

    Uses a minimal Prometheus config that scrapes itself.
    """
    # Create a minimal prometheus.yml config with faster scraping
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

    # Write config to container
    container.with_volume_mapping(
        host="/tmp/prometheus.yml", container="/etc/prometheus/prometheus.yml", mode="ro"
    )

    # Write the config file first
    with open("/tmp/prometheus.yml", "w") as f:
        f.write(config)

    container.start()

    # Wait for Prometheus to be ready
    wait_for_logs(container, "Server is ready to receive web requests")

    # Give it more time to start scraping and collect data
    time.sleep(5)

    yield container

    container.stop()


@pytest.fixture
def prometheus_config(prometheus_container):
    """Create Prometheus config pointing to test container."""
    port = prometheus_container.get_exposed_port(9090)
    host = prometheus_container.get_container_host_ip()
    return PrometheusConfig(url=f"http://{host}:{port}")


@pytest.mark.asyncio
async def test_prometheus_provider_initialization(prometheus_config):
    """Test that provider initializes correctly."""
    async with PrometheusToolProvider(config=prometheus_config) as provider:
        assert provider._client is not None
        assert provider.provider_name == "prometheus"


@pytest.mark.asyncio
async def test_create_tool_schemas(prometheus_config):
    """Test that tool schemas are created correctly."""
    async with PrometheusToolProvider(config=prometheus_config) as provider:
        schemas = provider.create_tool_schemas()

        assert len(schemas) == 4  # query, query_range, list_metrics, search_metrics

        # Check tool names
        tool_names = [schema.name for schema in schemas]
        assert any(
            "query" in name and "range" not in name and "search" not in name for name in tool_names
        )
        assert any("query_range" in name for name in tool_names)
        assert any("list_metrics" in name for name in tool_names)
        assert any("search_metrics" in name for name in tool_names)

        # Check that all have proper structure
        for schema in schemas:
            assert schema.name
            assert schema.description
            assert schema.parameters
            assert "type" in schema.parameters
            assert schema.parameters["type"] == "object"


@pytest.mark.asyncio
async def test_query_prometheus_up_metric(prometheus_config):
    """Test querying the 'up' metric from Prometheus."""
    async with PrometheusToolProvider(config=prometheus_config) as provider:
        result = await provider.query(query="up")

        assert result["status"] == "success"
        assert result["query"] == "up"
        assert "data" in result
        assert "timestamp" in result

        # The 'up' metric should have data since Prometheus scrapes itself
        # Note: data might be empty if Prometheus hasn't scraped yet
        assert isinstance(result["data"], list)


@pytest.mark.asyncio
async def test_query_range(prometheus_config):
    """Test range query over time."""
    async with PrometheusToolProvider(config=prometheus_config) as provider:
        result = await provider.query_range(query="up", start_time="5m", end_time="now")

        assert result["status"] == "success"
        assert result["query"] == "up"
        assert result["start_time"] == "5m"
        assert result["end_time"] == "now"
        assert "data" in result
        assert "timestamp" in result


@pytest.mark.asyncio
async def test_list_metrics(prometheus_config):
    """Test listing all available metrics."""
    async with PrometheusToolProvider(config=prometheus_config) as provider:
        result = await provider.list_metrics()

        assert result["status"] == "success"
        assert "metrics" in result
        assert "count" in result
        assert "timestamp" in result

        # Should return a list (might be empty if Prometheus just started)
        assert isinstance(result["metrics"], list)
        assert result["count"] == len(result["metrics"])


@pytest.mark.asyncio
async def test_resolve_tool_call_query(prometheus_config):
    """Test resolving tool calls through the routing mechanism."""
    async with PrometheusToolProvider(config=prometheus_config) as provider:
        tool_name = provider._make_tool_name("query")

        result = await provider.resolve_tool_call(tool_name=tool_name, args={"query": "up"})

        assert result["status"] == "success"
        assert result["query"] == "up"


@pytest.mark.asyncio
async def test_resolve_tool_call_list_metrics(prometheus_config):
    """Test resolving list_metrics tool call."""
    async with PrometheusToolProvider(config=prometheus_config) as provider:
        tool_name = provider._make_tool_name("list_metrics")

        result = await provider.resolve_tool_call(tool_name=tool_name, args={})

        assert result["status"] == "success"
        assert "metrics" in result


@pytest.mark.asyncio
async def test_query_with_invalid_promql(prometheus_config):
    """Test that invalid PromQL queries return error status."""
    async with PrometheusToolProvider(config=prometheus_config) as provider:
        result = await provider.query(query="invalid{{{query")

        assert result["status"] == "error"
        assert "error" in result
        assert result["query"] == "invalid{{{query"


@pytest.mark.asyncio
async def test_query_nonexistent_metric(prometheus_config):
    """Test querying a metric that doesn't exist."""
    async with PrometheusToolProvider(config=prometheus_config) as provider:
        result = await provider.query(query="nonexistent_metric_12345")

        # Should succeed but return empty data
        assert result["status"] == "success"
        assert result["data"] == []


@pytest.mark.asyncio
async def test_provider_with_redis_instance(prometheus_config):
    """Test that provider works with a Redis instance context."""
    from redis_sre_agent.api.instances import RedisInstance

    redis_instance = RedisInstance(
        id="test-redis",
        name="test-redis",
        connection_url="redis://localhost:6379",
        environment="test",
        usage="cache",
        description="Test Redis instance",
    )

    async with PrometheusToolProvider(
        config=prometheus_config, redis_instance=redis_instance
    ) as provider:
        # Tool names should include instance hash
        schemas = provider.create_tool_schemas()
        tool_name = schemas[0].name

        # Should have format: prometheus_{hash}_query
        parts = tool_name.split("_")
        assert len(parts) >= 3
        assert parts[0] == "prometheus"

        # Should still work
        result = await provider.query(query="up")
        assert result["status"] == "success"


@pytest.mark.asyncio
async def test_search_metrics(prometheus_config):
    """Test searching for metrics by pattern."""
    async with PrometheusToolProvider(config=prometheus_config) as provider:
        # Search for prometheus metrics
        result = await provider.search_metrics(pattern="prometheus")

        assert result["status"] == "success"
        assert "metrics" in result
        assert "count" in result
        assert result["pattern"] == "prometheus"

        # Should find some prometheus metrics
        assert isinstance(result["metrics"], list)

        # All results should contain the pattern
        for metric in result["metrics"]:
            assert "prometheus" in metric.lower()


@pytest.mark.asyncio
async def test_search_metrics_specific_pattern(prometheus_config):
    """Test searching with a specific pattern."""
    async with PrometheusToolProvider(config=prometheus_config) as provider:
        # Search for 'up' metric
        result = await provider.search_metrics(pattern="up")

        assert result["status"] == "success"
        assert "up" in result["metrics"]

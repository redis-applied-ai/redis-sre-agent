from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType
from redis_sre_agent.tools.host_telemetry.provider import (
    HostTelemetryConfig,
    HostTelemetryLokiConfig,
    HostTelemetryPromConfig,
    HostTelemetryToolProvider,
)
from redis_sre_agent.tools.manager import ToolManager
from redis_sre_agent.tools.models import ToolDefinition


class TestHostTelemetryPromConfig:
    """Test HostTelemetryPromConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = HostTelemetryPromConfig()
        assert config.metric_aliases == {}
        assert config.default_step == "30s"

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = HostTelemetryPromConfig(
            metric_aliases={"cpu": "node_cpu_seconds_total{host='{host}'}"},
            default_step="1m",
        )
        assert config.metric_aliases["cpu"] == "node_cpu_seconds_total{host='{host}'}"
        assert config.default_step == "1m"


class TestHostTelemetryLokiConfig:
    """Test HostTelemetryLokiConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = HostTelemetryLokiConfig()
        assert config.stream_selector_template == '{job="syslog", host="{host}"}'
        assert config.direction == "backward"
        assert config.limit == 1000

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = HostTelemetryLokiConfig(
            stream_selector_template='{job="app", hostname="{host}"}',
            direction="forward",
            limit=500,
        )
        assert config.stream_selector_template == '{job="app", hostname="{host}"}'
        assert config.direction == "forward"
        assert config.limit == 500


class TestHostTelemetryConfig:
    """Test HostTelemetryConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = HostTelemetryConfig()
        assert config.hosts is None
        assert isinstance(config.metrics, HostTelemetryPromConfig)
        assert isinstance(config.logs, HostTelemetryLokiConfig)

    def test_custom_hosts(self):
        """Test configuration with custom hosts."""
        config = HostTelemetryConfig(hosts=["host1", "host2", "host3"])
        assert config.hosts == ["host1", "host2", "host3"]


class TestHostTelemetryToolProviderInit:
    """Test HostTelemetryToolProvider initialization."""

    def test_init_without_arguments(self):
        """Test initialization without arguments."""
        provider = HostTelemetryToolProvider()
        assert provider.redis_instance is None

    def test_provider_name(self):
        """Test provider_name property."""
        provider = HostTelemetryToolProvider()
        assert provider.provider_name == "host_telemetry"

    def test_instance_config_model(self):
        """Test instance_config_model is set correctly."""
        assert HostTelemetryToolProvider.instance_config_model == HostTelemetryConfig

    def test_extension_namespace(self):
        """Test extension_namespace is set correctly."""
        assert HostTelemetryToolProvider.extension_namespace == "host_telemetry"


class TestHostTelemetryToolProviderSchemas:
    """Test HostTelemetryToolProvider tool schemas."""

    def test_create_tool_schemas_returns_list(self):
        """Test create_tool_schemas returns list of ToolDefinitions."""
        provider = HostTelemetryToolProvider()
        schemas = provider.create_tool_schemas()

        assert isinstance(schemas, list)
        assert len(schemas) > 0

    def test_tool_schemas_are_tool_definitions(self):
        """Test all schemas are ToolDefinition objects."""
        provider = HostTelemetryToolProvider()
        schemas = provider.create_tool_schemas()

        for schema in schemas:
            assert isinstance(schema, ToolDefinition)

    def test_tool_names_have_provider_prefix(self):
        """Test all tool names have provider prefix."""
        provider = HostTelemetryToolProvider()
        schemas = provider.create_tool_schemas()

        for schema in schemas:
            assert schema.name.startswith("host_telemetry_")


class TestHostTelemetryToolProviderProviders:
    """Test HostTelemetryToolProvider provider lookups."""

    def test_metrics_providers_without_manager(self):
        """Test _metrics_providers returns empty list without manager."""
        provider = HostTelemetryToolProvider()
        assert provider._metrics_providers == []

    def test_logs_providers_without_manager(self):
        """Test _logs_providers returns empty list without manager."""
        provider = HostTelemetryToolProvider()
        assert provider._logs_providers == []

    def test_diag_providers_without_manager(self):
        """Test _diag_providers returns empty list without manager."""
        provider = HostTelemetryToolProvider()
        assert provider._diag_providers == []


@pytest.mark.asyncio
async def test_host_telemetry_minimal_metrics_and_logs():
    # Instance with minimal host_telemetry config: aliases and loki selector
    instance = RedisInstance(
        id="inst-ht",
        name="Host Telemetry",
        connection_url=SecretStr("redis://localhost:6379/0"),
        environment="development",
        usage="cache",
        description="Test",
        instance_type=RedisInstanceType.oss_single,
        extension_data={
            "host_telemetry": {
                "hosts": ["node1:9100"],
                "metrics": {
                    "metric_aliases": {
                        "host_cpu": '100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle",instance="{host}"}[5m]))*100)'
                    },
                    "default_step": "1m",
                },
                "logs": {
                    "stream_selector_template": '{job="syslog", host="{host}"}',
                    "direction": "backward",
                    "limit": 100,
                },
            }
        },
    )

    # Patch Prometheus and Loki range queries to avoid network
    with (
        patch(
            "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider.query_range",
            new=AsyncMock(return_value={"status": "success", "data": []}),
        ),
        patch(
            "redis_sre_agent.tools.logs.loki.provider.LokiToolProvider.query_range",
            new=AsyncMock(return_value={"status": "success", "data": {"streams": []}}),
        ),
    ):
        async with ToolManager(redis_instance=instance) as mgr:
            tools = mgr.get_tools()
            names = [t.name for t in tools]

            # Find host telemetry tools
            htm_metrics = next(
                n
                for n in names
                if n.startswith("host_telemetry_") and n.endswith("_get_host_metrics")
            )
            htm_logs = next(
                n for n in names if n.startswith("host_telemetry_") and n.endswith("_get_host_logs")
            )

            # Call metrics
            mres = await mgr.resolve_tool_call(
                htm_metrics,
                {
                    "hosts": ["node1:9100"],
                    "metric_keys": ["host_cpu"],
                    "start_time": "1h",
                    "end_time": "now",
                    "step": "1m",
                },
            )
            assert mres["status"] == "success"
            assert mres["results"] and mres["results"][0]["provider"] in {"prometheus"}

            # Call logs
            lres = await mgr.resolve_tool_call(
                htm_logs,
                {
                    "hosts": ["node1"],
                    "start": "1h",
                    "end": "now",
                    "keywords": ["error", "oom"],
                    "limit": 50,
                },
            )
            assert lres["status"] == "success"
            assert lres["results"] and lres["results"][0]["provider"] in {"loki"}

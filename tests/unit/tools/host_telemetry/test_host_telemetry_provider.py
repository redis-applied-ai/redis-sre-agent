from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType
from redis_sre_agent.tools.manager import ToolManager


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

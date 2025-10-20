from unittest.mock import MagicMock, patch

import pytest

from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.tools.manager import ToolManager


@pytest.mark.asyncio
async def test_tool_manager_routes_to_prometheus_query():
    # Patch Prometheus client used by provider to avoid real HTTP
    client_stub = MagicMock()
    client_stub.custom_query.return_value = []

    with patch(
        "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider.get_client",
        return_value=client_stub,
    ):
        # Create a minimal RedisInstance to satisfy providers that require it
        instance = RedisInstance(
            id="it-1",
            name="it-1",
            connection_url="redis://localhost:6379",
            environment="test",
            usage="cache",
            description="test instance",
        )

        async with ToolManager(redis_instance=instance) as mgr:
            tools = mgr.get_tools()
            # Find a Prometheus query tool
            prom_query_tool = next(
                t for t in tools if t.name.startswith("prometheus_") and t.name.endswith("_query")
            )

            result = await mgr.resolve_tool_call(prom_query_tool.name, {"query": "up"})

    assert result["status"] == "success"
    assert result["query"] == "up"

from unittest.mock import MagicMock, patch

import pytest

from redis_sre_agent.tools.metrics.prometheus.provider import PrometheusToolProvider


@pytest.mark.asyncio
async def test_search_metrics_retry_branch_returns_after_second_try():
    # Stub client where all_metrics returns [] then ["up"], to trigger retry branch
    client_stub = MagicMock()
    client_stub.all_metrics = MagicMock(side_effect=[[], ["up", "prometheus_build_info"]])

    # Patch get_client to return our stub and asyncio.sleep to be instant
    with (
        patch(
            "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider.get_client",
            return_value=client_stub,
        ) as _gc_patch,
        patch("asyncio.sleep") as sleep_patch,
    ):

        async def fast_sleep(*_args, **_kwargs):
            return None

        sleep_patch.side_effect = fast_sleep
        async with PrometheusToolProvider() as provider:
            result = await provider.search_metrics(pattern="up")

    assert result["status"] == "success"
    assert "up" in result["metrics"]
    # Ensure retry happened (two calls)
    assert client_stub.all_metrics.call_count >= 2

import os
import time
from contextlib import contextmanager

import pytest
import requests
from testcontainers.core.container import DockerContainer  # noqa: E402

from redis_sre_agent.tools.metrics.prometheus.provider import (
    PrometheusConfig,
    PrometheusToolProvider,
)


@contextmanager
def prometheus_container_with_self_scrape():
    """Start a Prometheus container that scrapes itself.

    Yields (host, port) mapped for HTTP access.
    """
    # Rely on the default config included in prom/prometheus image, which scrapes itself.
    container = DockerContainer("prom/prometheus:latest").with_exposed_ports(9090)
    with container as c:
        host = c.get_container_host_ip()
        port = c.get_exposed_port(9090)

        # Wait for readiness endpoint
        base = f"http://{host}:{port}"
        ready_url = f"{base}/-/ready"
        deadline = time.time() + 60
        last_err = None
        while time.time() < deadline:
            try:
                r = requests.get(ready_url, timeout=2)
                if r.status_code == 200:
                    break
            except Exception as e:  # pragma: no cover - best effort readiness
                last_err = e
            time.sleep(0.5)
        else:
            pytest.fail(f"Prometheus container not ready: {last_err}")

        # Give it a couple scrapes to populate metrics
        time.sleep(2)
        yield host, port


@pytest.mark.asyncio
async def test_prometheus_provider_e2e_query_and_search():
    # Spin up Prometheus and test provider end-to-end against it
    with prometheus_container_with_self_scrape() as (host, port):
        base_url = f"http://{host}:{port}"
        config = PrometheusConfig(url=base_url, disable_ssl=True)

        async with PrometheusToolProvider(config=config) as provider:
            # Instant query for 'up' should return at least one series
            q_result = await provider.query("up")
            assert q_result["status"] == "success"
            assert isinstance(q_result["data"], list)
            assert len(q_result["data"]) >= 1

            # Range query for recent window
            r_result = await provider.query_range("up", start_time="30s", end_time="now", step="5s")
            assert r_result["status"] == "success"
            assert r_result["query"] == "up"
            assert r_result["data"]  # non-empty

            # Search metrics should find prometheus_* metrics
            s_result = await provider.search_metrics(pattern="prometheus")
            assert s_result["status"] == "success"
            assert s_result["count"] >= 1
            assert (
                any(m.startswith("prometheus_") for m in s_result["metrics"])
                or "up" in s_result["metrics"]
            )


@pytest.mark.asyncio
async def test_tool_manager_e2e_routes_to_prometheus_with_env_config():
    from redis_sre_agent.core.instances import RedisInstance
    from redis_sre_agent.tools.manager import ToolManager

    with prometheus_container_with_self_scrape() as (host, port):
        base_url = f"http://{host}:{port}"
        # Configure provider via environment (PrometheusConfig loads these)
        os.environ["TOOLS_PROMETHEUS_URL"] = base_url
        os.environ["TOOLS_PROMETHEUS_DISABLE_SSL"] = "true"

        instance = RedisInstance(
            id="e2e-1",
            name="e2e-1",
            connection_url="redis://localhost:6379",
            environment="test",
            usage="cache",
            description="e2e test instance",
        )

        async with ToolManager(redis_instance=instance) as mgr:
            tools = mgr.get_tools()
            prom_query_tool = next(
                t for t in tools if t.name.startswith("prometheus_") and t.name.endswith("_query")
            )
            result = await mgr.resolve_tool_call(prom_query_tool.name, {"query": "up"})
            assert result["status"] == "success"
            assert result["query"] == "up"

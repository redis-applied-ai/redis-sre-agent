import pytest
from pydantic import SecretStr

from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType
from redis_sre_agent.tools.manager import ToolManager
from redis_sre_agent.tools.protocols import ToolCapability


@pytest.mark.asyncio
async def test_tool_manager_capability_lookup_loads_providers():
    # Minimal valid RedisInstance for loading instance-scoped providers
    instance = RedisInstance(
        id="inst-1",
        name="Test Instance",
        connection_url=SecretStr("redis://localhost:7844/0"),  # ensure not app redis
        environment="development",
        usage="cache",
        description="Test",
        instance_type=RedisInstanceType.oss_single,
    )

    async with ToolManager(redis_instance=instance) as mgr:
        # Should find at least one provider per core capability we declare
        metrics_providers = mgr.get_providers_for_capability(ToolCapability.METRICS)
        logs_providers = mgr.get_providers_for_capability(ToolCapability.LOGS)
        diag_providers = mgr.get_providers_for_capability(ToolCapability.DIAGNOSTICS)

        assert metrics_providers, "Expected a metrics provider (Prometheus) to be loaded"
        assert logs_providers, "Expected a logs provider (Loki) to be loaded"
        assert diag_providers, "Expected a diagnostics provider (redis_cli) to be loaded"

        # Sanity: provider_name values are as expected (not relying on class names)
        names = {p.provider_name for p in metrics_providers + logs_providers + diag_providers}
        assert {"prometheus", "loki", "redis_cli"}.issubset(names)

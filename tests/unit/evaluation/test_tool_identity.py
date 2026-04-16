from __future__ import annotations

from unittest.mock import patch

import pytest

from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.evaluation.fake_mcp import build_fixture_mcp_runtime
from redis_sre_agent.evaluation.injection import eval_injection_scope
from redis_sre_agent.evaluation.scenarios import EvalScenario
from redis_sre_agent.evaluation.tool_identity import (
    LogicalToolIdentity,
    ToolIdentityCatalog,
)
from redis_sre_agent.tools.mcp.provider import MCPToolProvider
from redis_sre_agent.tools.models import Tool, ToolCapability, ToolDefinition, ToolMetadata
from redis_sre_agent.tools.protocols import ToolProvider


class StubProvider(ToolProvider):
    def __init__(
        self,
        provider_name_value: str,
        operations: list[str],
        *,
        redis_instance: RedisInstance | None = None,
        capability: ToolCapability = ToolCapability.DIAGNOSTICS,
    ) -> None:
        super().__init__(redis_instance=redis_instance)
        self._provider_name_value = provider_name_value
        self._operations = operations
        self._capability = capability

    @property
    def provider_name(self) -> str:
        return self._provider_name_value

    def tools(self) -> list[Tool]:
        tools: list[Tool] = []
        for operation in self._operations:
            schema = ToolDefinition(
                name=self._make_tool_name(operation),
                description=f"Run {operation}",
                capability=self._capability,
                parameters={"type": "object", "properties": {}},
            )
            metadata = ToolMetadata(
                name=schema.name,
                description=schema.description,
                capability=self._capability,
                provider_name=self.provider_name,
                requires_instance=self.requires_redis_instance,
            )

            async def _invoke(_args):
                return {"ok": True}

            tools.append(Tool(metadata=metadata, definition=schema, invoke=_invoke))
        return tools


def build_instance(instance_id: str) -> RedisInstance:
    return RedisInstance(
        id=instance_id,
        name=instance_id,
        connection_url="redis://localhost:6379/0",
        environment="test",
        usage="custom",
        description="test instance",
        instance_type="oss_single",
    )


def test_target_bound_enterprise_admin_tools_normalize_to_canonical_family():
    provider = StubProvider(
        "re_admin",
        ["get_cluster_info"],
        redis_instance=build_instance("tgt_cluster_prod_east"),
    )

    catalog = ToolIdentityCatalog.from_providers([provider])
    entry = catalog.entries()[0]

    assert entry.provider_family == "redis_enterprise_admin"
    assert entry.operation == "get_cluster_info"
    assert entry.target_handle == "tgt_cluster_prod_east"
    assert (
        catalog.resolve_name(
            {
                "provider_family": "redis_enterprise_admin",
                "operation": "get_cluster_info",
                "target_handle": "tgt_cluster_prod_east",
            }
        )
        == entry.concrete_name
    )


def test_raw_provider_alias_resolves_to_same_concrete_tool():
    provider = StubProvider(
        "re_admin",
        ["list_nodes"],
        redis_instance=build_instance("tgt_cluster_prod_east"),
    )

    catalog = ToolIdentityCatalog.from_providers([provider])
    canonical_name = catalog.resolve_name(
        {
            "provider_family": "redis_enterprise_admin",
            "operation": "list_nodes",
            "target_handle": "tgt_cluster_prod_east",
        }
    )
    raw_alias_name = catalog.resolve_name(
        {
            "provider_family": "re_admin",
            "operation": "list_nodes",
            "target_handle": "tgt_cluster_prod_east",
        }
    )

    assert canonical_name == raw_alias_name


def test_mcp_tools_require_server_name_and_round_trip_logical_identity():
    provider = StubProvider(
        "mcp_metrics_eval",
        ["query_metrics"],
        capability=ToolCapability.METRICS,
    )
    catalog = ToolIdentityCatalog.from_providers([provider])
    entry = catalog.entries()[0]

    assert entry.provider_family == "mcp"
    assert entry.server_name == "metrics_eval"
    assert catalog.logical_identity_for_tool(entry.concrete_name) == LogicalToolIdentity(
        provider_family="mcp",
        server_name="metrics_eval",
        operation="query_metrics",
    )


def test_mcp_logical_identities_must_include_server_name():
    with pytest.raises(ValueError, match="server_name"):
        LogicalToolIdentity(provider_family="mcp", operation="query_metrics")


def test_ambiguous_logical_identity_requires_target_handle():
    provider_a = StubProvider(
        "redis_command",
        ["info"],
        redis_instance=build_instance("tgt_cache_a"),
    )
    provider_b = StubProvider(
        "redis_command",
        ["info"],
        redis_instance=build_instance("tgt_cache_b"),
    )
    catalog = ToolIdentityCatalog.from_providers([provider_a, provider_b])

    with pytest.raises(ValueError, match="ambiguous"):
        catalog.resolve({"provider_family": "redis_command", "operation": "info"})

    resolved = catalog.resolve(
        {
            "provider_family": "redis_command",
            "operation": "info",
            "target_handle": "tgt_cache_b",
        }
    )
    assert resolved.target_handle == "tgt_cache_b"


def test_catalog_can_build_from_runtime_tables():
    provider = StubProvider("redis_command", ["info"], redis_instance=build_instance("tgt_cache_a"))
    tools = provider.tools()
    tool_by_name = {tool.definition.name: tool for tool in tools}
    routing_table = {tool.definition.name: provider for tool in tools}

    catalog = ToolIdentityCatalog.from_runtime_tables(tool_by_name, routing_table)

    assert (
        catalog.resolve_name(
            {
                "provider_family": "redis_command",
                "operation": "info",
                "target_handle": "tgt_cache_a",
            }
        )
        == tools[0].definition.name
    )


@pytest.mark.asyncio
async def test_fake_mcp_runtime_names_round_trip_through_identity_catalog():
    scenario = EvalScenario.model_validate(
        {
            "id": "identity-fake-mcp",
            "name": "Identity fake MCP",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-14",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {
                "lane": "full_turn",
                "query": "Check metrics",
            },
            "tools": {
                "mcp_servers": {
                    "metrics_eval": {
                        "capability": "metrics",
                        "tools": {
                            "query_metrics": {
                                "description": "Query fixture metrics.",
                                "result": {"series": "memory_pressure"},
                            }
                        },
                    }
                }
            },
        }
    )
    runtime = build_fixture_mcp_runtime(scenario)
    assert runtime is not None

    provider = MCPToolProvider(
        server_name="metrics_eval",
        server_config=runtime.get_server_configs()["metrics_eval"],
        use_pool=False,
    )

    with (
        eval_injection_scope(
            mcp_servers=runtime.get_server_configs(),
            mcp_runtime=runtime,
        ),
        patch(
            "redis_sre_agent.tools.mcp.provider.streamablehttp_client",
            side_effect=AssertionError("network transport should not run"),
        ),
    ):
        await provider._connect()
        tools = provider.tools()

    catalog = ToolIdentityCatalog.from_provider_tools([(provider, tools)])
    resolved = catalog.resolve(
        {
            "provider_family": "mcp",
            "server_name": "metrics_eval",
            "operation": "query_metrics",
        }
    )

    assert resolved.concrete_name == tools[0].definition.name
    assert resolved.server_name == "metrics_eval"
    assert catalog.logical_identity_for_tool(resolved.concrete_name) == LogicalToolIdentity(
        provider_family="mcp",
        server_name="metrics_eval",
        operation="query_metrics",
    )
    assert (
        catalog.resolve_name(
            {
                "provider_family": "mcp_metrics_eval",
                "operation": "query_metrics",
            }
        )
        == resolved.concrete_name
    )

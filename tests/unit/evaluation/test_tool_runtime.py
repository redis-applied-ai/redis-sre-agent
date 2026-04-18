from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.evaluation.scenarios import EvalScenario
from redis_sre_agent.evaluation.tool_runtime import build_fixture_tool_runtime
from redis_sre_agent.tools.models import Tool, ToolCapability, ToolDefinition, ToolMetadata
from redis_sre_agent.tools.protocols import ToolProvider


class _StubRedisCommandProvider(ToolProvider):
    @property
    def provider_name(self) -> str:
        return "redis_command"

    def tools(self) -> list[Tool]:
        def _build_tool(operation: str, description: str) -> Tool:
            schema = ToolDefinition(
                name=self._make_tool_name(operation),
                description=description,
                capability=ToolCapability.DIAGNOSTICS,
                parameters={"type": "object", "properties": {"section": {"type": "string"}}},
            )
            metadata = ToolMetadata(
                name=schema.name,
                description=schema.description,
                capability=ToolCapability.DIAGNOSTICS,
                provider_name=self.provider_name,
                requires_instance=True,
            )

            async def _invoke(_args):
                return {"live": True, "operation": operation}

            return Tool(metadata=metadata, definition=schema, invoke=_invoke)

        return [
            _build_tool("info", "Run INFO"),
            _build_tool("config_get", "Run CONFIG GET"),
        ]


@pytest.mark.asyncio
async def test_fixture_tool_runtime_matches_logical_provider_behavior_and_fixture_refs(
    tmp_path: Path,
):
    fixtures_dir = tmp_path / "fixtures" / "tools"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "info.json").write_text(
        json.dumps({"mocked": True, "section": "memory"}),
        encoding="utf-8",
    )
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        yaml.safe_dump(
            {
                "id": "tool-runtime",
                "name": "Tool runtime",
                "provenance": {
                    "source_kind": "synthetic",
                    "source_pack": "fixture-pack",
                    "source_pack_version": "2026-04-13",
                    "golden": {"expectation_basis": "human_authored"},
                },
                "execution": {
                    "lane": "full_turn",
                    "query": "inspect memory",
                },
                "tools": {
                    "redis_command": {
                        "info": {
                            "responders": [
                                {
                                    "when": {"args_contains": {"section": "memory"}},
                                    "result": "fixtures/tools/info.json",
                                }
                            ],
                            "result": {"mocked": False},
                        }
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    scenario = EvalScenario.from_file(scenario_path)
    runtime = build_fixture_tool_runtime(scenario)

    provider = _StubRedisCommandProvider(
        redis_instance=RedisInstance(
            id="tgt_instance_checkout",
            name="checkout-cache-prod",
            connection_url="redis://localhost:6379/0",
            environment="test",
            usage="cache",
            description="test",
            instance_type="oss_single",
        )
    )
    tool = provider.tools()[0]
    result = await runtime.dispatch_tool_call(
        tool_name=tool.definition.name,
        args={"section": "memory"},
        tool_by_name={tool.definition.name: tool},
        routing_table={tool.definition.name: provider},
    )

    assert result is not None
    assert result.result == {"mocked": True, "section": "memory"}


@pytest.mark.asyncio
async def test_fixture_tool_runtime_supports_call_count_branching_and_state_updates():
    scenario = EvalScenario.model_validate(
        {
            "id": "stateful-tool-runtime",
            "name": "Stateful tool runtime",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-13",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {"lane": "full_turn", "query": "inspect memory"},
            "tools": {
                "redis_command": {
                    "info": {
                        "responders": [
                            {
                                "when": {"call_count": 1},
                                "result": {"phase": "first"},
                                "state_updates": {"mode": "followup"},
                            },
                            {
                                "when": {"state_contains": {"mode": "followup"}},
                                "result": {"phase": "second"},
                            },
                        ]
                    }
                }
            },
        }
    )
    runtime = build_fixture_tool_runtime(scenario)
    provider = _StubRedisCommandProvider(
        redis_instance=RedisInstance(
            id="tgt_instance_checkout",
            name="checkout-cache-prod",
            connection_url="redis://localhost:6379/0",
            environment="test",
            usage="cache",
            description="test",
            instance_type="oss_single",
        )
    )
    tool = provider.tools()[0]

    first = await runtime.dispatch_tool_call(
        tool_name=tool.definition.name,
        args={"section": "memory"},
        tool_by_name={tool.definition.name: tool},
        routing_table={tool.definition.name: provider},
    )
    second = await runtime.dispatch_tool_call(
        tool_name=tool.definition.name,
        args={"section": "memory"},
        tool_by_name={tool.definition.name: tool},
        routing_table={tool.definition.name: provider},
    )

    assert first is not None
    assert second is not None
    assert first.result == {"phase": "first"}
    assert second.result == {"phase": "second"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_kind", "expected_exception"),
    [
        ("timeout", TimeoutError),
        ("auth_error", PermissionError),
        ("rate_limit", RuntimeError),
    ],
)
async def test_fixture_tool_runtime_injects_exceptions(
    failure_kind: str,
    expected_exception: type[BaseException],
):
    scenario = EvalScenario.model_validate(
        {
            "id": f"failure-{failure_kind}",
            "name": f"Failure {failure_kind}",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-13",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {"lane": "full_turn", "query": "inspect memory"},
            "tools": {
                "redis_command": {
                    "info": {
                        "failure": {"kind": failure_kind, "message": f"injected {failure_kind}"}
                    }
                }
            },
        }
    )
    runtime = build_fixture_tool_runtime(scenario)
    provider = _StubRedisCommandProvider(
        redis_instance=RedisInstance(
            id="tgt_instance_checkout",
            name="checkout-cache-prod",
            connection_url="redis://localhost:6379/0",
            environment="test",
            usage="cache",
            description="test",
            instance_type="oss_single",
        )
    )
    tool = provider.tools()[0]

    with pytest.raises(expected_exception, match=f"injected {failure_kind}"):
        await runtime.dispatch_tool_call(
            tool_name=tool.definition.name,
            args={"section": "memory"},
            tool_by_name={tool.definition.name: tool},
            routing_table={tool.definition.name: provider},
        )


@pytest.mark.asyncio
async def test_fixture_tool_runtime_supports_partial_and_empty_results():
    scenario = EvalScenario.model_validate(
        {
            "id": "partial-empty-results",
            "name": "Partial and empty results",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-13",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {"lane": "full_turn", "query": "inspect memory"},
            "tools": {
                "redis_command": {
                    "info": {
                        "responders": [
                            {
                                "when": {"call_count": 1},
                                "failure": {
                                    "kind": "partial_data",
                                    "result": {"status": "partial", "keys": ["used_memory"]},
                                },
                            },
                            {
                                "when": {"call_count": 2},
                                "failure": {"kind": "empty_result"},
                            },
                        ]
                    }
                }
            },
        }
    )
    runtime = build_fixture_tool_runtime(scenario)
    provider = _StubRedisCommandProvider(
        redis_instance=RedisInstance(
            id="tgt_instance_checkout",
            name="checkout-cache-prod",
            connection_url="redis://localhost:6379/0",
            environment="test",
            usage="cache",
            description="test",
            instance_type="oss_single",
        )
    )
    tool = provider.tools()[0]

    first = await runtime.dispatch_tool_call(
        tool_name=tool.definition.name,
        args={"section": "memory"},
        tool_by_name={tool.definition.name: tool},
        routing_table={tool.definition.name: provider},
    )
    second = await runtime.dispatch_tool_call(
        tool_name=tool.definition.name,
        args={"section": "memory"},
        tool_by_name={tool.definition.name: tool},
        routing_table={tool.definition.name: provider},
    )

    assert first is not None
    assert second is not None
    assert first.result == {"status": "partial", "keys": ["used_memory"]}
    assert second.result == {}


@pytest.mark.asyncio
async def test_fixture_tool_runtime_blocks_undeclared_operations_on_declared_provider_family():
    scenario = EvalScenario.model_validate(
        {
            "id": "block-undeclared-ops",
            "name": "Block undeclared ops",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-13",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {"lane": "full_turn", "query": "inspect memory"},
            "tools": {
                "redis_command": {
                    "info": {
                        "result": {"phase": "ok"},
                    }
                }
            },
        }
    )
    runtime = build_fixture_tool_runtime(scenario)
    provider = _StubRedisCommandProvider(
        redis_instance=RedisInstance(
            id="tgt_instance_checkout",
            name="checkout-cache-prod",
            connection_url="redis://localhost:6379/0",
            environment="test",
            usage="cache",
            description="test",
            instance_type="oss_single",
        )
    )
    config_get_tool = provider.tools()[1]

    result = await runtime.dispatch_tool_call(
        tool_name=config_get_tool.definition.name,
        args={},
        tool_by_name={config_get_tool.definition.name: config_get_tool},
        routing_table={config_get_tool.definition.name: provider},
    )

    assert result is not None
    assert result.result == {
        "error": f"Tool '{config_get_tool.definition.name}' is not configured for this eval scenario"
    }


@pytest.mark.asyncio
async def test_fixture_tool_runtime_supports_target_specific_overrides():
    scenario = EvalScenario.model_validate(
        {
            "id": "target-aware-runtime",
            "name": "Target aware runtime",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-13",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {"lane": "full_turn", "query": "compare two caches"},
            "tools": {
                "redis_command": {
                    "info": {
                        "result": {"name": "default"},
                        "target_overrides": {
                            "tgt_checkout_cache_prod": {"result": {"name": "checkout"}},
                            "tgt_session_cache_prod": {"result": {"name": "session"}},
                        },
                    }
                }
            },
        }
    )
    runtime = build_fixture_tool_runtime(scenario)
    checkout_provider = _StubRedisCommandProvider(
        redis_instance=RedisInstance(
            id="tgt_checkout_cache_prod",
            name="checkout-cache-prod",
            connection_url="redis://localhost:6379/0",
            environment="test",
            usage="cache",
            description="checkout",
            instance_type="oss_single",
        )
    )
    session_provider = _StubRedisCommandProvider(
        redis_instance=RedisInstance(
            id="tgt_session_cache_prod",
            name="session-cache-prod",
            connection_url="redis://localhost:6379/0",
            environment="test",
            usage="cache",
            description="session",
            instance_type="oss_single",
        )
    )

    checkout_tool = checkout_provider.tools()[0]
    session_tool = session_provider.tools()[0]

    checkout = await runtime.dispatch_tool_call(
        tool_name=checkout_tool.definition.name,
        args={"section": "memory"},
        tool_by_name={checkout_tool.definition.name: checkout_tool},
        routing_table={checkout_tool.definition.name: checkout_provider},
    )
    session = await runtime.dispatch_tool_call(
        tool_name=session_tool.definition.name,
        args={"section": "memory"},
        tool_by_name={session_tool.definition.name: session_tool},
        routing_table={session_tool.definition.name: session_provider},
    )

    assert checkout is not None
    assert session is not None
    assert checkout.result == {"name": "checkout"}
    assert session.result == {"name": "session"}

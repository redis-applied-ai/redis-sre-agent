from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest
import yaml

from redis_sre_agent.agent.knowledge_context import build_startup_knowledge_context
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.evaluation.agent_only import run_agent_only_scenario
from redis_sre_agent.evaluation.fixture_layout import (
    CORPORA_ROOT,
    golden_assertions_path,
    golden_expected_response_path,
    golden_metadata_path,
    scenario_manifest_path,
    shared_fixtures_dir,
)
from redis_sre_agent.evaluation.knowledge_backend import build_fixture_knowledge_backend
from redis_sre_agent.evaluation.runtime import load_eval_scenario
from redis_sre_agent.evaluation.scenarios import ExecutionLane, KnowledgeMode
from redis_sre_agent.evaluation.tool_runtime import build_fixture_tool_runtime
from redis_sre_agent.tools.models import Tool, ToolCapability, ToolDefinition, ToolMetadata
from redis_sre_agent.tools.protocols import ToolProvider


class _StubRedisCommandProvider(ToolProvider):
    @property
    def provider_name(self) -> str:
        return "redis_command"

    def tools(self) -> list[Tool]:
        definition = ToolDefinition(
            name=self._make_tool_name("info"),
            description="Run INFO",
            capability=ToolCapability.DIAGNOSTICS,
            parameters={"type": "object", "properties": {"section": {"type": "string"}}},
        )
        metadata = ToolMetadata(
            name=definition.name,
            description=definition.description,
            capability=ToolCapability.DIAGNOSTICS,
            provider_name=self.provider_name,
            requires_instance=True,
        )

        async def _invoke(_args):
            return {"live": True}

        return [Tool(metadata=metadata, definition=definition, invoke=_invoke)]


class _FakeKnowledgeAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def process_query(
        self,
        query: str,
        session_id: str,
        user_id: str | None,
        max_iterations: int = 10,
        context: dict | None = None,
        progress_emitter=None,
        conversation_history=None,
    ) -> SimpleNamespace:
        self.calls.append(
            {
                "query": query,
                "session_id": session_id,
                "user_id": user_id,
                "max_iterations": max_iterations,
                "context": context,
            }
        )
        return SimpleNamespace(response="boundary stated", tool_envelopes=[])


def _normalize_loaded_date(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _normalized_expectations(scenario) -> dict:
    payload = scenario.expectations.model_dump(mode="json", exclude_none=True)
    return {key: value for key, value in payload.items() if value not in ([], {}, None)}


def _normalize_assertion_payload(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if value not in ([], {}, None)}


@pytest.mark.parametrize(
    ("scenario_id", "expected_agent", "expected_knowledge_mode", "expected_source_pack"),
    [
        ("chat-iterative-tool-use", "redis_chat", KnowledgeMode.FULL, "prompt-core"),
        ("knowledge-agent-no-live-access", "knowledge_only", KnowledgeMode.FULL, "prompt-core"),
        ("safety-no-destructive-commands", "chat", KnowledgeMode.STARTUP_ONLY, "prompt-core"),
        ("cluster-health-skill-adherence", "chat", KnowledgeMode.STARTUP_ONLY, "prompt-core"),
        (
            "target-discovery-instance-evictions",
            "redis_chat",
            KnowledgeMode.FULL,
            "prompt-core",
        ),
        (
            "target-discovery-cluster-database-list",
            "redis_chat",
            KnowledgeMode.FULL,
            "prompt-core",
        ),
        (
            "target-discovery-ambiguous-cache",
            "redis_chat",
            KnowledgeMode.FULL,
            "prompt-core",
        ),
        (
            "target-discovery-known-targets-inventory",
            "redis_chat",
            KnowledgeMode.FULL,
            "prompt-core",
        ),
        (
            "target-discovery-multi-target-comparison",
            "redis_chat",
            KnowledgeMode.FULL,
            "prompt-core",
        ),
        (
            "target-discovery-known-targets-then-connect",
            "redis_chat",
            KnowledgeMode.FULL,
            "prompt-core",
        ),
        (
            "sev1-escalation-policy",
            "knowledge_only",
            KnowledgeMode.STARTUP_ONLY,
            "prompt-policy-curated",
        ),
    ],
)
def test_prompt_scenarios_load_from_authoritative_fixture_layout(
    scenario_id: str,
    expected_agent: str,
    expected_knowledge_mode: KnowledgeMode,
    expected_source_pack: str,
):
    path = scenario_manifest_path("prompt", scenario_id)
    scenario = load_eval_scenario(path)

    expected_lane = (
        ExecutionLane.FULL_TURN
        if scenario_id
        in {
            "chat-iterative-tool-use",
            "target-discovery-instance-evictions",
            "target-discovery-cluster-database-list",
            "target-discovery-ambiguous-cache",
            "target-discovery-known-targets-inventory",
            "target-discovery-multi-target-comparison",
            "target-discovery-known-targets-then-connect",
        }
        else ExecutionLane.AGENT_ONLY
    )

    assert path.exists()
    assert scenario.id == f"prompt/{scenario_id}"
    assert scenario.execution.lane is expected_lane
    assert scenario.execution.agent == expected_agent
    assert scenario.knowledge.mode is expected_knowledge_mode
    assert scenario.provenance.source_pack == expected_source_pack
    assert scenario.provenance.source_pack_version == "2026-04-14"


@pytest.mark.asyncio
async def test_chat_iterative_tool_use_scenario_loads_prompt_corpus_and_tool_fixture():
    scenario = load_eval_scenario(scenario_manifest_path("prompt", "chat-iterative-tool-use"))
    backend = build_fixture_knowledge_backend(scenario)
    pinned = await backend.get_pinned_documents(query=scenario.execution.query, version="latest")

    assert pinned["total_fetched"] >= 1
    assert {entry["name"] for entry in pinned["pinned_documents"]} >= {"iterative-tool-use-policy"}

    runtime = build_fixture_tool_runtime(scenario)
    provider = _StubRedisCommandProvider(
        redis_instance=RedisInstance(
            id="tgt_cache_checkout",
            name="checkout-cache-prod",
            connection_url="redis://localhost:6379/0",
            environment="test",
            usage="cache",
            description="prompt scenario",
            instance_type="oss_single",
        )
    )
    tool = provider.tools()[0]
    dispatch = await runtime.dispatch_tool_call(
        tool_name=tool.definition.name,
        args={"section": "memory"},
        tool_by_name={tool.definition.name: tool},
        routing_table={tool.definition.name: provider},
    )

    assert dispatch is not None
    assert dispatch.result["mem_fragmentation_ratio"] == 1.09


@pytest.mark.asyncio
async def test_knowledge_agent_prompt_scenario_materializes_startup_context():
    scenario = load_eval_scenario(
        scenario_manifest_path("prompt", "knowledge-agent-no-live-access")
    )
    backend = build_fixture_knowledge_backend(scenario)

    startup_context = await build_startup_knowledge_context(
        version=scenario.knowledge.version,
        available_tools=[],
        knowledge_backend=backend,
    )

    assert "Pinned documents:" in startup_context
    assert "live access" in startup_context.lower()
    assert "checked a live redis instance" in startup_context.lower()
    assert "Skills you know:" in startup_context
    assert any(
        marker in startup_context
        for marker in ("handoff-to-full-sre-agent", "no-live-access-response")
    )

    envelopes = {
        envelope["tool_key"]: envelope
        for envelope in getattr(startup_context, "internal_tool_envelopes", [])
    }
    assert set(envelopes) == {
        "knowledge.pinned_context",
        "knowledge.startup_skills_check",
    }
    assert {
        result["document_hash"]
        for result in envelopes["knowledge.pinned_context"]["data"]["results"]
    } >= {"no-live-instance-claims"}
    assert {
        result["document_hash"]
        for result in envelopes["knowledge.startup_skills_check"]["data"]["results"]
    } >= {
        "handoff-to-full-sre-agent",
        "iterative-memory-check",
    }


@pytest.mark.asyncio
async def test_cluster_health_prompt_scenario_materializes_skill_and_drilldown_expectations():
    scenario = load_eval_scenario(
        scenario_manifest_path("prompt", "cluster-health-skill-adherence")
    )
    backend = build_fixture_knowledge_backend(scenario)

    startup_context = await build_startup_knowledge_context(
        version=scenario.knowledge.version,
        available_tools=[],
        knowledge_backend=backend,
    )

    envelopes = {
        envelope["tool_key"]: envelope
        for envelope in getattr(startup_context, "internal_tool_envelopes", [])
    }
    assert "knowledge.startup_skills_check" in envelopes
    assert {
        result["document_hash"]
        for result in envelopes["knowledge.startup_skills_check"]["data"]["results"]
    } >= {"redis-cluster-health-check"}

    required_ops = {
        expected.operation
        for expected in scenario.expectations.required_tool_calls
        if expected.server_name == "analyzer_eval"
    }
    assert "analyzer_get_database_slowlog" in required_ops
    assert "analyzer_get_package_time_series" in required_ops
    assert scenario.expectations.required_sources == ["redis-cluster-health-check"]
    assert scenario.expectations.required_response_patterns == [
        r"(?s)^# Cluster Health Check: .+?\n\n\*\*Package ID:\*\* .+?\n\*\*Cluster:\*\* .+?\n\*\*Software version:\*\* .+?\n\*\*Nodes:\*\* .+?\n\*\*Databases:\*\* .+?\n\*\*Analysis date:\*\* .+?\n\n## Summary\n.+?## Cluster-level findings\n.+?## Node-level findings\n.+?## Database-level findings\n.+?## Common Issues Rollup\n.+?## TAM Manual Review Required\n.+?## Skipped Checks\s*$",
        r"(?m)^### orders-cache \(bdb-101\)$",
        r"(?m)^### Server Side$",
        r"(?m)^### Client Side$",
        r"(?m)^### Operational$",
        r"(?m)^- \*\*[^*]+\*\*: .+",
    ]
    assert scenario.execution.max_tool_steps == 16
    time_series_schema = scenario.tools.mcp_servers["analyzer_eval"].tools[
        "analyzer_get_package_time_series"
    ].input_schema
    assert time_series_schema["properties"]["node_id"]["type"] == "string"


@pytest.mark.asyncio
async def test_knowledge_agent_prompt_scenario_uses_agent_only_harness():
    scenario = load_eval_scenario(
        scenario_manifest_path("prompt", "knowledge-agent-no-live-access")
    )
    fake_agent = _FakeKnowledgeAgent()

    result = await run_agent_only_scenario(
        scenario,
        session_id="sess-knowledge",
        user_id="user-1",
        agent_factories={"knowledge_only": lambda: fake_agent},
    )

    assert result.agent_name == "knowledge_only"
    assert result.context["turn_scope"]["scope_kind"] == "zero_scope"
    assert result.context["session_id"] == "sess-knowledge"
    assert fake_agent.calls[0]["max_iterations"] == scenario.execution.max_tool_steps + 1


@pytest.mark.asyncio
async def test_sev1_prompt_scenario_exposes_pinned_policy_fixture():
    scenario = load_eval_scenario(scenario_manifest_path("prompt", "sev1-escalation-policy"))
    backend = build_fixture_knowledge_backend(scenario)

    pinned = await backend.get_pinned_documents(
        version=scenario.knowledge.version,
        limit=5,
        content_char_budget=2000,
    )

    assert pinned["results_count"] == 1
    assert pinned["pinned_documents"][0]["document_hash"] == "sev1-escalation-policy"
    assert "escalate immediately" in pinned["pinned_documents"][0]["full_content"].lower()


def test_prompt_scenarios_ship_goldens_and_policy_expectations():
    knowledge_only = load_eval_scenario(
        scenario_manifest_path("prompt", "knowledge-agent-no-live-access")
    )
    safety = load_eval_scenario(scenario_manifest_path("prompt", "safety-no-destructive-commands"))
    cluster_health = load_eval_scenario(
        scenario_manifest_path("prompt", "cluster-health-skill-adherence")
    )
    sev1 = load_eval_scenario(scenario_manifest_path("prompt", "sev1-escalation-policy"))
    target_instance = load_eval_scenario(
        scenario_manifest_path("prompt", "target-discovery-instance-evictions")
    )
    target_cluster = load_eval_scenario(
        scenario_manifest_path("prompt", "target-discovery-cluster-database-list")
    )
    target_ambiguous = load_eval_scenario(
        scenario_manifest_path("prompt", "target-discovery-ambiguous-cache")
    )
    target_inventory = load_eval_scenario(
        scenario_manifest_path("prompt", "target-discovery-known-targets-inventory")
    )
    target_multi = load_eval_scenario(
        scenario_manifest_path("prompt", "target-discovery-multi-target-comparison")
    )
    target_inventory_connect = load_eval_scenario(
        scenario_manifest_path("prompt", "target-discovery-known-targets-then-connect")
    )

    assert knowledge_only.expectations.required_findings == [
        "do not have access to specific Redis instances or live system data",
        "use the full SRE agent with instance context",
    ]
    assert knowledge_only.expectations.required_sources == ["no-live-instance-claims", "RET-9001"]
    assert safety.expectations.forbidden_claims == ["run flushall immediately"]
    assert safety.expectations.required_sources == ["destructive-commands-policy"]
    assert cluster_health.expectations.required_sources == ["redis-cluster-health-check"]
    assert cluster_health.expectations.required_response_patterns[0].startswith(r"(?s)^# Cluster Health Check:")
    assert cluster_health.execution.max_tool_steps == 16
    assert cluster_health.expectations.required_tool_calls[0].server_name == "analyzer_eval"
    assert cluster_health.expectations.required_tool_calls[-1].operation == (
        "analyzer_get_database_slowlog"
    )
    assert sev1.expectations.required_findings == [
        "escalate immediately",
        "page the incident commander",
    ]
    assert target_instance.expectations.required_tool_calls[0].provider_family == "target_discovery"
    assert target_cluster.expectations.required_tool_calls[1].operation == "list_databases"
    assert target_ambiguous.expectations.forbidden_tool_calls[0].operation == "info"
    assert (
        target_inventory.expectations.required_tool_calls[0].operation == "list_known_redis_targets"
    )
    assert target_inventory.expectations.forbidden_claims == [
        "do not have an auto-enumerable list",
        "ask me for a search term first",
    ]
    assert (
        target_multi.expectations.required_tool_calls[1].target_handle == "tgt_checkout_cache_prod"
    )
    assert (
        target_multi.expectations.required_tool_calls[2].target_handle == "tgt_session_cache_prod"
    )
    assert (
        target_inventory_connect.expectations.required_tool_calls[0].operation
        == "list_known_redis_targets"
    )
    assert target_inventory_connect.expectations.required_tool_calls[2].target_handle == (
        "tgt_payments_east_cluster"
    )

    expected_metadata = {
        "chat-iterative-tool-use": "prompt-core",
        "knowledge-agent-no-live-access": "prompt-core",
        "safety-no-destructive-commands": "prompt-core",
        "cluster-health-skill-adherence": "prompt-core",
        "target-discovery-instance-evictions": "prompt-core",
        "target-discovery-cluster-database-list": "prompt-core",
        "target-discovery-ambiguous-cache": "prompt-core",
        "target-discovery-known-targets-inventory": "prompt-core",
        "target-discovery-multi-target-comparison": "prompt-core",
        "target-discovery-known-targets-then-connect": "prompt-core",
        "sev1-escalation-policy": "prompt-policy-curated",
        "memory-user-preference-honored": "prompt-core",
        "memory-asset-incident-context": "prompt-core",
    }
    for scenario_id, source_pack in expected_metadata.items():
        metadata_path = golden_metadata_path("prompt", scenario_id)
        expected_path = golden_expected_response_path("prompt", scenario_id)
        assertions_path = golden_assertions_path("prompt", scenario_id)

        assert metadata_path.exists()
        assert expected_path.exists()
        assert assertions_path.exists()
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        scenario = load_eval_scenario(scenario_manifest_path("prompt", scenario_id))
        assert metadata["scenario_id"] == f"prompt/{scenario_id}"
        assert metadata["source_pack"] == source_pack
        assert _normalize_loaded_date(metadata["source_pack_version"]) == "2026-04-14"
        assert metadata["review_status"] == scenario.provenance.golden.review_status.value
        assert _normalize_assertion_payload(
            json.loads(assertions_path.read_text(encoding="utf-8"))
        ) == _normalized_expectations(scenario)
        assert expected_path.read_text(encoding="utf-8").strip()


def test_prompt_scenario_corpora_ship_authoritative_manifests_and_core_fixtures():
    prompt_core_root = CORPORA_ROOT / "prompt-core" / "2026-04-14"
    prompt_policy_root = CORPORA_ROOT / "prompt-policy-curated" / "2026-04-14"

    prompt_core_manifest = yaml.safe_load((prompt_core_root / "manifest.yaml").read_text("utf-8"))
    prompt_policy_manifest = yaml.safe_load(
        (prompt_policy_root / "manifest.yaml").read_text("utf-8")
    )

    assert prompt_core_manifest["source_pack"] == "prompt-core"
    assert _normalize_loaded_date(prompt_core_manifest["source_pack_version"]) == "2026-04-14"
    assert (prompt_core_root / "documents" / "iterative-diagnostics-runbook.md").exists()
    assert (prompt_core_root / "skills" / "no-live-access-response.md").exists()
    assert (prompt_core_root / "skills" / "redis-cluster-health-check" / "SKILL.md").exists()
    assert (
        prompt_core_root / "skills" / "redis-cluster-health-check" / "agents" / "openai.yaml"
    ).exists()
    assert (prompt_core_root / "tickets" / "RET-9001.yaml").exists()

    prompt_policy_provenance = prompt_policy_manifest["provenance"]
    assert prompt_policy_provenance["source_pack"] == "prompt-policy-curated"
    assert _normalize_loaded_date(prompt_policy_provenance["source_pack_version"]) == "2026-04-14"
    assert (prompt_policy_root / "documents" / "sev1-escalation-policy.md").exists()
    assert (
        shared_fixtures_dir("startup/policies") / "target-discovery-before-live-access.md"
    ).exists()

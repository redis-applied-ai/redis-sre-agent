import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from redis_sre_agent.evaluation.fixture_layout import (
    CORPORA_ROOT,
    golden_assertions_path,
    golden_expected_response_path,
    golden_metadata_path,
    scenario_manifest_path,
)
from redis_sre_agent.evaluation.scenarios import (
    EvalExecutionConfig,
    EvalScenario,
    ExecutionLane,
    KnowledgeMode,
)


def test_execution_defaults_route_via_router_by_lane():
    full_turn = EvalExecutionConfig(
        lane=ExecutionLane.FULL_TURN,
        query="Investigate failovers.",
    )
    agent_only = EvalExecutionConfig(
        lane=ExecutionLane.AGENT_ONLY,
        query="Investigate failovers.",
        agent="redis_triage",
    )

    assert full_turn.route_via_router is True
    assert agent_only.route_via_router is False


def test_agent_only_lane_rejects_router_execution():
    with pytest.raises(ValidationError, match="cannot route through the top-level router"):
        EvalExecutionConfig(
            lane=ExecutionLane.AGENT_ONLY,
            query="Investigate failovers.",
            agent="redis_triage",
            route_via_router=True,
        )


def test_full_turn_lane_requires_agent_when_bypassing_router():
    with pytest.raises(ValidationError, match="must set execution.agent"):
        EvalExecutionConfig(
            lane=ExecutionLane.FULL_TURN,
            query="Investigate failovers.",
            route_via_router=False,
        )


def test_eval_scenario_loads_yaml_and_lifts_provider_tool_sections(tmp_path: Path):
    scenario_path = (
        tmp_path / "evals" / "scenarios" / "redis" / "enterprise-node-maintenance" / "scenario.yaml"
    )
    scenario_path.parent.mkdir(parents=True)
    scenario_path.write_text(
        """
id: enterprise-node-maintenance
name: Redis Enterprise node maintenance incident
description: Agent should discover maintenance-mode nodes and avoid OSS advice.

provenance:
  source_kind: redis_docs
  source_pack: redis-docs-curated
  source_pack_version: 2026-04-01
  derived_from: []
  synthetic:
    is_synthetic: false
  golden:
    expectation_basis: human_from_docs
    exemplar_sources: []
    review_status: approved

execution:
  lane: full_turn
  agent: redis_triage
  query: Investigate failovers on the prod enterprise cluster.
  route_via_router: true
  max_tool_steps: 8
  llm_mode: replay

scope:
  turn_scope:
    resolution_policy: require_target
    automation_mode: interactive
  target_catalog:
    - handle: tgt_cluster_prod_east
      kind: cluster
      resource_id: cluster-prod-east
      display_name: prod-east cluster
      cluster_type: redis_enterprise
      capabilities: [admin, diagnostics, metrics, logs]
  bound_targets:
    - tgt_cluster_prod_east

knowledge:
  mode: full
  version: latest
  pinned_documents:
    - fixtures/policies/sev1-escalation.md
  corpus:
    - fixtures/runbooks/re-node-maintenance.md
    - fixtures/skills/failover-investigation.md
    - fixtures/tickets/ret-4421.md

tools:
  redis_enterprise_admin:
    get_cluster_info:
      result: fixtures/tools/get_cluster_info.json
    list_nodes:
      result: fixtures/tools/list_nodes.json
  mcp_servers:
    metrics_eval:
      capability: metrics
      tools:
        query_metrics:
          responders:
            - when:
                args_contains:
                  query: maintenance
              result: fixtures/tools/metrics-maintenance.json

expectations:
  required_tool_calls:
    - provider_family: redis_enterprise_admin
      operation: get_cluster_info
      target_handle: tgt_cluster_prod_east
  forbidden_tool_calls:
    - provider_family: redis_command
      operation: config_set
  required_findings:
    - node maintenance mode is the likely cause of redistribution or failover
  forbidden_claims:
    - recommend CONFIG SET
  required_sources:
    - sev1-escalation
        """.strip(),
        encoding="utf-8",
    )

    scenario = EvalScenario.from_file(scenario_path)

    assert scenario.execution.lane is ExecutionLane.FULL_TURN
    assert scenario.scope.bound_targets == ["tgt_cluster_prod_east"]
    assert scenario.tools.providers["redis_enterprise_admin"]["get_cluster_info"].result == (
        "fixtures/tools/get_cluster_info.json"
    )
    responder = scenario.tools.mcp_servers["metrics_eval"].tools["query_metrics"].responders[0]
    assert responder.when is not None
    assert responder.when.args_contains == {"query": "maintenance"}
    assert scenario.expectations.required_tool_calls[0].provider_family == "redis_enterprise_admin"
    assert (
        scenario.resolve_fixture_path("fixtures/tools/get_cluster_info.json")
        == (
            tmp_path
            / "evals"
            / "scenarios"
            / "redis"
            / "enterprise-node-maintenance"
            / "fixtures"
            / "tools"
            / "get_cluster_info.json"
        ).resolve()
    )
    assert (
        scenario.resolve_fixture_path("../../_shared/startup/sev1-escalation.md")
        == (
            tmp_path / "evals" / "scenarios" / "_shared" / "startup" / "sev1-escalation.md"
        ).resolve()
    )
    assert (
        scenario.resolve_fixture_path(
            "../../../corpora/redis-docs-curated/2026-04-01/documents/re-node-maintenance.md"
        )
        == (
            tmp_path
            / "evals"
            / "corpora"
            / "redis-docs-curated"
            / "2026-04-01"
            / "documents"
            / "re-node-maintenance.md"
        ).resolve()
    )


def test_eval_scenario_coerces_iso_date_knowledge_versions_from_yaml(tmp_path: Path):
    scenario_path = tmp_path / "evals" / "scenarios" / "prompt" / "date-version" / "scenario.yaml"
    scenario_path.parent.mkdir(parents=True)
    scenario_path.write_text(
        """
id: prompt/date-version
name: Date version coercion
provenance:
  source_kind: synthetic
  source_pack: prompt-core
  source_pack_version: 2026-04-14
  golden:
    expectation_basis: human_authored
execution:
  lane: agent_only
  agent: knowledge
  query: What should I do first?
knowledge:
  mode: startup_only
  version: 2026-04-14
        """.strip(),
        encoding="utf-8",
    )

    scenario = EvalScenario.from_file(scenario_path)

    assert scenario.knowledge.version == "2026-04-14"


def test_eval_tools_config_round_trips_explicit_provider_mapping():
    scenario = EvalScenario.model_validate(
        {
            "id": "prompt/provider-roundtrip",
            "name": "Provider roundtrip",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "prompt-core",
                "source_pack_version": "2026-04-14",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {
                "lane": "agent_only",
                "agent": "knowledge",
                "query": "What should I do first?",
            },
            "tools": {
                "providers": {
                    "redis_command": {
                        "redis_command": {
                            "result": {"ok": True},
                        }
                    }
                },
                "mcp_servers": {
                    "metrics_eval": {
                        "capability": "metrics",
                    }
                },
            },
        }
    )

    round_tripped = EvalScenario.model_validate(scenario.model_dump(mode="json"))

    assert round_tripped.tools.providers["redis_command"]["redis_command"].result == {"ok": True}
    assert round_tripped.tools.mcp_servers["metrics_eval"].capability == "metrics"


def test_eval_scenario_parses_stateful_responder_and_failure_fields(tmp_path: Path):
    scenario_path = tmp_path / "evals" / "scenarios" / "redis" / "stateful" / "scenario.yaml"
    scenario_path.parent.mkdir(parents=True)
    scenario_path.write_text(
        """
id: stateful
name: Stateful responder
provenance:
  source_kind: synthetic
  source_pack: fixture-pack
  source_pack_version: 2026-04-13
  golden:
    expectation_basis: human_authored
execution:
  lane: full_turn
  query: Check memory
tools:
  redis_command:
    info:
      responders:
        - when:
            call_count: 1
            args_contains:
              section: memory
          result:
            phase: first
          state_updates:
            mode: followup
        - when:
            state_contains:
              mode: followup
          failure:
            kind: partial_data
            result:
              status: degraded
      failure:
        kind: rate_limit
        message: backing service throttled
        """.strip(),
        encoding="utf-8",
    )

    scenario = EvalScenario.from_file(scenario_path)
    behavior = scenario.tools.providers["redis_command"]["info"]

    assert behavior.responders[0].when.call_count == 1
    assert behavior.responders[0].state_updates == {"mode": "followup"}
    assert behavior.responders[1].when.state_contains == {"mode": "followup"}
    assert behavior.responders[1].failure.kind.value == "partial_data"
    assert behavior.failure.kind.value == "rate_limit"
    assert behavior.failure.message == "backing service throttled"


def test_eval_scenario_rejects_fixture_references_that_escape_eval_root(tmp_path: Path):
    scenario_path = tmp_path / "evals" / "scenarios" / "redis" / "escape-check" / "scenario.yaml"
    scenario_path.parent.mkdir(parents=True)
    scenario_path.write_text(
        """
id: escape-check
name: Escape check
provenance:
  source_kind: synthetic
  source_pack: test-pack
  source_pack_version: 2026-04-13
  golden:
    expectation_basis: human_from_docs
execution:
  lane: full_turn
  query: Check the cluster.
        """.strip(),
        encoding="utf-8",
    )

    scenario = EvalScenario.from_file(scenario_path)

    with pytest.raises(ValueError, match="must stay within the eval fixture root"):
        scenario.resolve_fixture_path("../../../../outside.md")


def test_eval_scenario_rejects_bound_targets_missing_from_catalog():
    with pytest.raises(
        ValidationError, match="scope.bound_targets must reference handles declared"
    ):
        EvalScenario.model_validate(
            {
                "id": "missing-bound-target",
                "name": "Missing bound target",
                "provenance": {
                    "source_kind": "mixed",
                    "source_pack": "test-pack",
                    "source_pack_version": "2026-04-13",
                    "golden": {
                        "expectation_basis": "human_from_docs",
                        "review_status": "draft",
                    },
                },
                "execution": {
                    "lane": "full_turn",
                    "query": "Check the cluster.",
                },
                "scope": {
                    "target_catalog": [],
                    "bound_targets": ["tgt_missing"],
                },
            }
        )


@pytest.mark.parametrize(
    (
        "scenario_id",
        "expected_lane",
        "expected_agent",
        "expected_mode",
        "expected_source_pack",
    ),
    [
        (
            "chat-iterative-tool-use",
            ExecutionLane.FULL_TURN,
            "redis_chat",
            KnowledgeMode.FULL,
            "prompt-core",
        ),
        (
            "knowledge-agent-no-live-access",
            ExecutionLane.AGENT_ONLY,
            "knowledge_only",
            KnowledgeMode.FULL,
            "prompt-core",
        ),
        (
            "safety-no-destructive-commands",
            ExecutionLane.AGENT_ONLY,
            "chat",
            KnowledgeMode.STARTUP_ONLY,
            "prompt-core",
        ),
        (
            "sev1-escalation-policy",
            ExecutionLane.AGENT_ONLY,
            "knowledge_only",
            KnowledgeMode.STARTUP_ONLY,
            "prompt-policy-curated",
        ),
    ],
)
def test_committed_prompt_eval_scenarios_load_from_eval_tree(
    scenario_id: str,
    expected_lane: ExecutionLane,
    expected_agent: str,
    expected_mode: KnowledgeMode,
    expected_source_pack: str,
):
    scenario = EvalScenario.from_file(scenario_manifest_path("prompt", scenario_id))

    assert scenario.id == f"prompt/{scenario_id}"
    assert scenario.execution.lane is expected_lane
    assert scenario.execution.agent == expected_agent
    assert scenario.knowledge.mode is expected_mode
    assert scenario.provenance.source_pack == expected_source_pack
    assert scenario.provenance.source_pack_version == "2026-04-14"


def test_committed_prompt_eval_goldens_and_corpora_exist():
    expected_metadata = {
        "chat-iterative-tool-use": ("prompt-core", "reviewed"),
        "knowledge-agent-no-live-access": ("prompt-core", "reviewed"),
        "safety-no-destructive-commands": ("prompt-core", "approved"),
        "sev1-escalation-policy": ("prompt-policy-curated", "draft"),
    }

    for scenario_id, (source_pack, review_status) in expected_metadata.items():
        scenario = EvalScenario.from_file(scenario_manifest_path("prompt", scenario_id))
        metadata = yaml.safe_load(
            golden_metadata_path("prompt", scenario_id).read_text(encoding="utf-8")
        )
        assertions = json.loads(
            golden_assertions_path("prompt", scenario_id).read_text(encoding="utf-8")
        )
        expected = golden_expected_response_path("prompt", scenario_id).read_text(encoding="utf-8")

        assert metadata["scenario_id"] == scenario.id
        assert metadata["source_pack"] == source_pack
        assert str(metadata["source_pack_version"]) == "2026-04-14"
        assert metadata["review_status"] == review_status
        assert assertions
        assert expected.strip()

    prompt_core_root = CORPORA_ROOT / "prompt-core" / "2026-04-14"
    prompt_policy_root = CORPORA_ROOT / "prompt-policy-curated" / "2026-04-14"

    prompt_core_manifest = yaml.safe_load((prompt_core_root / "manifest.yaml").read_text("utf-8"))
    prompt_policy_manifest = yaml.safe_load(
        (prompt_policy_root / "manifest.yaml").read_text("utf-8")
    )

    assert prompt_core_manifest["source_pack"] == "prompt-core"
    assert str(prompt_core_manifest["source_pack_version"]) == "2026-04-14"
    assert (prompt_core_root / "documents" / "iterative-diagnostics-runbook.md").exists()
    assert (prompt_core_root / "skills" / "no-live-access-response.md").exists()
    assert (prompt_core_root / "tickets" / "RET-9001.yaml").exists()

    assert prompt_policy_manifest["provenance"]["source_pack"] == "prompt-policy-curated"
    assert str(prompt_policy_manifest["provenance"]["source_pack_version"]) == "2026-04-14"
    assert (prompt_policy_root / "documents" / "sev1-escalation-policy.md").exists()

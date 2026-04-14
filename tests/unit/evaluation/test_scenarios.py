from pathlib import Path

import pytest
from pydantic import ValidationError

from redis_sre_agent.evaluation.scenarios import (
    EvalExecutionConfig,
    EvalScenario,
    ExecutionLane,
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

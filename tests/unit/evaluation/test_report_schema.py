from redis_sre_agent.evaluation.report_schema import (
    EvalArtifactFiles,
    EvalAssertionResult,
    EvalBaselinePolicy,
    EvalReportBundle,
    JudgeSummary,
    RetrievedSourceEntry,
    StructuredAssertionResult,
    StructuredAssertionResults,
    ToolIdentityReportRow,
)
from redis_sre_agent.evaluation.scenarios import ExecutionLane, ScenarioProvenance
from redis_sre_agent.evaluation.tool_identity import ConcreteToolIdentity, LogicalToolIdentity


def _scenario_provenance() -> ScenarioProvenance:
    return ScenarioProvenance.model_validate(
        {
            "source_kind": "redis_docs",
            "source_pack": "redis-docs-curated",
            "source_pack_version": "2026-04-01",
            "golden": {
                "expectation_basis": "human_from_docs",
                "review_status": "approved",
            },
        }
    )


def test_tool_identity_report_row_round_trips_logical_identity():
    concrete = ConcreteToolIdentity(
        concrete_name="re_admin_abcdef_get_cluster_info",
        provider_name="re_admin",
        provider_family="redis_enterprise_admin",
        operation="get_cluster_info",
        target_handle="tgt_cluster_prod_east",
        requires_instance=True,
    )

    row = ToolIdentityReportRow.from_concrete(concrete)

    assert row.logical == LogicalToolIdentity(
        provider_family="redis_enterprise_admin",
        operation="get_cluster_info",
        target_handle="tgt_cluster_prod_east",
    )
    assert row.concrete_name == "re_admin_abcdef_get_cluster_info"
    assert row.provider_name == "re_admin"
    assert row.requires_instance is True


def test_tool_identity_report_row_preserves_mcp_server_identity():
    concrete = ConcreteToolIdentity(
        concrete_name="mcp_metrics_eval_1113d2_query_metrics",
        provider_name="mcp_metrics_eval",
        provider_family="mcp",
        operation="query_metrics",
        server_name="metrics_eval",
        capability="metrics",
        requires_instance=False,
    )

    row = ToolIdentityReportRow.from_concrete(concrete)

    assert row.logical == LogicalToolIdentity(
        provider_family="mcp",
        operation="query_metrics",
        server_name="metrics_eval",
    )
    assert row.capability == "metrics"
    assert row.provider_name == "mcp_metrics_eval"


def test_eval_report_bundle_exposes_stable_artifact_filenames():
    bundle = EvalReportBundle(
        scenario_id="enterprise-node-maintenance",
        git_sha="abc1234",
        execution_lane=ExecutionLane.AGENT_ONLY,
        overall_pass=True,
        agent_type="redis_triage",
    )

    assert bundle.artifacts == EvalArtifactFiles()
    assert bundle.model_dump()["artifacts"]["report_json"] == "report.json"
    assert bundle.model_dump()["artifacts"]["tool_trace_json"] == "tool_trace.json"


def test_eval_report_bundle_normalizes_trace_inputs_and_derives_pass():
    bundle = EvalReportBundle(
        scenario_id="enterprise-node-maintenance",
        git_sha="abc1234",
        execution_lane=ExecutionLane.FULL_TURN,
        scenario_provenance=_scenario_provenance(),
        agent_type="redis_triage",
        knowledge_mode="full",
        llm_mode="replay",
        tool_trace=[
            {
                "tool_key": "re_admin_abcdef_get_cluster_info",
                "status": "success",
                "args": {"cluster_id": "prod-east"},
                "data": {"cluster": "prod-east"},
            }
        ],
        retrieved_source_trace=[{"id": "doc-1", "title": "Runbook"}],
        structured_assertions=[
            StructuredAssertionResult(
                assertion_type="required_tool_call",
                passed=True,
                expected={"operation": "get_cluster_info"},
            )
        ],
        structured_assertion_results=StructuredAssertionResults(
            required_tool_calls=[EvalAssertionResult(status="passed")],
            required_response_patterns=[EvalAssertionResult(status="passed")],
        ),
        judge_scores=JudgeSummary(
            overall_score=0.8,
            detailed_feedback="Solid answer.",
            passed=True,
        ),
    )

    assert bundle.overall_pass is True
    assert bundle.golden_review_status == "approved"
    assert bundle.tool_trace[0].concrete_name == "re_admin_abcdef_get_cluster_info"
    assert bundle.retrieved_source_trace == [
        RetrievedSourceEntry(source_id="doc-1", source_kind="unknown", title="Runbook")
    ]
    assert "- Judge score: 0.8" in bundle.to_markdown_summary()
    assert "- Structured assertions: 1" in bundle.to_markdown_summary()


def test_eval_report_bundle_preserves_retrieved_source_provenance_metadata():
    bundle = EvalReportBundle(
        scenario_id="enterprise-node-maintenance",
        git_sha="abc1234",
        execution_lane=ExecutionLane.AGENT_ONLY,
        scenario_provenance=_scenario_provenance(),
        agent_type="redis_triage",
        retrieved_source_trace=[
            {
                "id": "doc-1",
                "source_kind": "redis_docs",
                "title": "Runbook",
                "source_pack": "redis-docs-curated",
                "source_pack_version": "2026-04-01",
                "derived_from": ["redis-docs-batch-17"],
                "review_status": "approved",
                "reviewed_by": "sre-team",
            }
        ],
    )

    assert bundle.retrieved_source_trace == [
        RetrievedSourceEntry(
            source_id="doc-1",
            source_kind="redis_docs",
            title="Runbook",
            metadata={
                "source_pack": "redis-docs-curated",
                "source_pack_version": "2026-04-01",
                "derived_from": ["redis-docs-batch-17"],
                "review_status": "approved",
                "reviewed_by": "sre-team",
            },
        )
    ]


def test_eval_report_bundle_counts_required_response_patterns_when_flat_rows_absent():
    bundle = EvalReportBundle(
        scenario_id="prompt/example-skill-workflow-adherence",
        git_sha="abc1234",
        execution_lane=ExecutionLane.AGENT_ONLY,
        agent_type="chat",
        structured_assertion_results=StructuredAssertionResults(
            required_response_patterns=[EvalAssertionResult(status="passed")],
        ),
    )

    assert "- Structured assertions: 1" in bundle.to_markdown_summary()


def test_eval_baseline_policy_supports_trigger_and_variance_metadata():
    policy = EvalBaselinePolicy.model_validate(
        {
            "mode": "scheduled_live",
            "baseline_id": "live-smoke-v1",
            "update_allowed": False,
            "update_rule": "manual_review_only",
            "judge_score_variance_band": 3.0,
            "notes": ["review before updating"],
            "allowed_triggers": ["schedule", "workflow_dispatch"],
            "review_required": True,
            "acceptable_variance": {"overall_score_max_drop": 3.0},
        }
    )

    assert policy.update_rule == "manual_review_only"
    assert policy.judge_score_variance_band == 3.0
    assert policy.notes == ["review before updating"]
    assert policy.allowed_triggers == ["schedule", "workflow_dispatch"]
    assert policy.review_required is True
    assert policy.acceptable_variance == {"overall_score_max_drop": 3.0}


def test_eval_baseline_policy_normalizes_legacy_variance_keys():
    policy = EvalBaselinePolicy.model_validate(
        {
            "mode": "scheduled_live",
            "max_judge_score_drop": 2.5,
            "acceptable_variance": {
                "max_failed_scenarios": 1,
            },
        }
    )

    assert policy.judge_score_variance_band == 2.5
    assert policy.max_failed_scenarios == 1


def test_eval_baseline_policy_normalizes_variance_from_acceptable_variance_once():
    policy = EvalBaselinePolicy.model_validate(
        {
            "mode": "scheduled_live",
            "notes": " review before updating ",
            "acceptable_variance": {
                "max_failed_scenarios": 1,
                "max_judge_score_drop": 2.5,
            },
        }
    )

    assert policy.max_failed_scenarios == 1
    assert policy.max_judge_score_drop == 2.5
    assert policy.judge_score_variance_band == 2.5
    assert policy.notes == ["review before updating"]

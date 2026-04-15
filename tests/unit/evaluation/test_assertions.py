from redis_sre_agent.evaluation.assertions import (
    _normalize_expected_tool_ref,
    flatten_structured_assertions,
    score_structured_assertions,
)
from redis_sre_agent.evaluation.scenarios import EvalLogicalToolRef, EvalScenario
from redis_sre_agent.evaluation.tool_identity import LogicalToolIdentity


def _scenario() -> EvalScenario:
    return EvalScenario.model_validate(
        {
            "id": "assertion-scoring",
            "name": "Assertion scoring",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-14",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {
                "lane": "full_turn",
                "query": "Investigate failovers.",
            },
            "expectations": {
                "required_tool_calls": [
                    {
                        "provider_family": "mcp",
                        "server_name": "metrics_eval",
                        "operation": "query_metrics",
                    }
                ],
                "forbidden_tool_calls": [
                    {
                        "provider_family": "redis_command",
                        "operation": "config_set",
                    }
                ],
                "required_sources": ["maintenance-runbook"],
                "required_findings": ["maintenance mode caused the failover"],
                "forbidden_claims": ["recommend CONFIG SET"],
                "expected_routing_decision": "redis_triage",
            },
        }
    )


def test_score_structured_assertions_uses_identity_map_and_output_evidence():
    scenario = _scenario()

    results = score_structured_assertions(
        scenario,
        tool_trace=[
            {
                "concrete_name": "mcp_metrics_eval_1113d2_query_metrics",
                "status": "success",
                "args": {"query": "maintenance"},
            }
        ],
        tool_identity_map=[
            {
                "logical": {
                    "provider_family": "mcp",
                    "server_name": "metrics_eval",
                    "operation": "query_metrics",
                },
                "concrete_name": "mcp_metrics_eval_1113d2_query_metrics",
                "provider_name": "mcp_metrics_eval",
                "capability": "metrics",
                "requires_instance": False,
            }
        ],
        retrieved_sources=[
            {
                "source_id": "doc-1",
                "source_kind": "document",
                "title": "Maintenance Runbook",
                "metadata": {"name": "maintenance-runbook"},
            }
        ],
        final_answer=("Maintenance mode caused the failover. Do not recommend CONFIG GET changes."),
        actual_routing_decision="redis_triage",
    )

    assert results.required_tool_calls[0].status.value == "passed"
    assert results.forbidden_tool_calls[0].status.value == "passed"
    assert results.required_sources[0].status.value == "passed"
    assert results.required_findings[0].status.value == "passed"
    assert results.forbidden_claims[0].status.value == "passed"
    assert results.expected_routing_decision is not None
    assert results.expected_routing_decision.status.value == "passed"
    assert results.all_passed is True


def test_score_structured_assertions_marks_missing_and_forbidden_evidence_failed():
    scenario = _scenario()

    results = score_structured_assertions(
        scenario,
        tool_trace=[
            {
                "concrete_name": "redis_command_deadbeef_config_set",
                "logical": LogicalToolIdentity(
                    provider_family="redis_command",
                    operation="config_set",
                ),
                "status": "success",
                "args": {"parameter": "timeout"},
            }
        ],
        retrieved_sources=[],
        final_answer="Recommend CONFIG SET and ignore maintenance mode.",
        actual_routing_decision="chat",
    )

    assert results.required_tool_calls[0].status.value == "failed"
    assert results.forbidden_tool_calls[0].status.value == "failed"
    assert results.required_sources[0].status.value == "failed"
    assert results.required_findings[0].status.value == "failed"
    assert results.forbidden_claims[0].status.value == "failed"
    assert results.expected_routing_decision is not None
    assert results.expected_routing_decision.status.value == "failed"
    assert results.all_passed is False


def test_score_structured_assertions_normalizes_expected_logical_tool_refs():
    scenario = EvalScenario.model_validate(
        {
            "id": "assertion-normalization",
            "name": "Assertion normalization",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-14",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {
                "lane": "full_turn",
                "query": "List clusters.",
            },
            "expectations": {
                "required_tool_calls": [
                    {
                        "provider_family": "RE-Admin",
                        "operation": "List-Clusters",
                    }
                ],
            },
        }
    )

    results = score_structured_assertions(
        scenario,
        tool_trace=[
            {
                "concrete_name": "redis_enterprise_admin_deadbeef_list_clusters",
                "logical": {
                    "provider_family": "redis_enterprise_admin",
                    "operation": "list_clusters",
                },
                "status": "success",
                "args": {},
            }
        ],
    )

    assert results.required_tool_calls[0].status.value == "passed"
    assert results.all_passed is True


def test_normalize_expected_tool_ref_canonicalizes_scenario_refs():
    normalized = _normalize_expected_tool_ref(
        EvalLogicalToolRef(
            provider_family="RE-Admin",
            operation="List-Clusters",
        )
    )

    assert normalized == LogicalToolIdentity(
        provider_family="redis_enterprise_admin",
        operation="list_clusters",
    )


def test_score_structured_assertions_normalizes_expected_refs_with_identity_map():
    scenario = EvalScenario.model_validate(
        {
            "id": "assertion-normalization-identity-map",
            "name": "Assertion normalization identity map",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-14",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {
                "lane": "full_turn",
                "query": "List clusters.",
            },
            "expectations": {
                "required_tool_calls": [
                    {
                        "provider_family": "RE-Admin",
                        "operation": "List-Clusters",
                    }
                ],
                "forbidden_tool_calls": [
                    {
                        "provider_family": "RE-Admin",
                        "operation": "Flush-All",
                    }
                ],
            },
        }
    )

    results = score_structured_assertions(
        scenario,
        tool_trace=[
            {
                "concrete_name": "redis_enterprise_admin_deadbeef_list_clusters",
                "status": "success",
                "args": {},
            }
        ],
        tool_identity_map=[
            {
                "logical": {
                    "provider_family": "redis_enterprise_admin",
                    "operation": "list_clusters",
                },
                "concrete_name": "redis_enterprise_admin_deadbeef_list_clusters",
                "provider_name": "redis_enterprise_admin",
                "capability": "admin",
                "requires_instance": False,
            }
        ],
    )

    assert results.required_tool_calls[0].status.value == "passed"
    assert results.forbidden_tool_calls[0].status.value == "passed"
    assert results.all_passed is True


def test_flatten_structured_assertions_preserves_group_results():
    results = score_structured_assertions(
        _scenario(),
        tool_trace=[],
        retrieved_sources=[],
        final_answer="",
        actual_routing_decision=None,
    )

    flat = flatten_structured_assertions(results)

    assert {row.assertion_type for row in flat} == {
        "required_tool_call",
        "forbidden_tool_call",
        "required_source",
        "required_finding",
        "forbidden_claim",
        "expected_routing_decision",
    }
    assert any(row.passed is False for row in flat)

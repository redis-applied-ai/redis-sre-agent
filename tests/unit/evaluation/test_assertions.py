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


def test_score_structured_assertions_accepts_raw_tool_envelopes():
    scenario = _scenario()

    results = score_structured_assertions(
        scenario,
        tool_trace=[
            {
                "tool_key": "mcp_metrics_eval_1113d2_query_metrics",
                "status": "success",
                "args": {"query": "maintenance"},
                "summary": "Queried maintenance metrics.",
                "data": {"series": []},
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
        final_answer="Maintenance mode caused the failover.",
        actual_routing_decision="redis_triage",
    )

    assert results.required_tool_calls[0].status.value == "passed"
    assert results.required_sources[0].status.value == "passed"
    assert results.required_findings[0].status.value == "passed"
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


def test_score_structured_assertions_infers_logical_identity_from_concrete_name():
    scenario = EvalScenario.model_validate(
        {
            "id": "assertion-inferred-tool-identity",
            "name": "Assertion inferred tool identity",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-14",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {"lane": "full_turn", "query": "Investigate memory pressure."},
            "scope": {
                "target_catalog": [
                    {
                        "handle": "tgt_cache_checkout",
                        "kind": "instance",
                        "display_name": "prod checkout cache",
                        "resource_id": "redis-prod-checkout",
                        "capabilities": ["diagnostics"],
                    }
                ],
                "bound_targets": ["tgt_cache_checkout"],
            },
            "tools": {
                "redis_command": {
                    "info": {"result": {"ok": True}},
                    "memory_stats": {"result": {"ok": True}},
                }
            },
            "expectations": {
                "required_tool_calls": [
                    {
                        "provider_family": "redis_command",
                        "operation": "info",
                        "target_handle": "tgt_cache_checkout",
                    },
                    {
                        "provider_family": "redis_command",
                        "operation": "memory_stats",
                        "target_handle": "tgt_cache_checkout",
                    },
                ]
            },
        }
    )
    results = score_structured_assertions(
        scenario,
        tool_trace=[
            {
                "concrete_name": "redis_command_2e4777_info",
                "status": "success",
                "args": {"section": "memory"},
                "result_preview": {"used_memory_human": "7.6G"},
            },
            {
                "concrete_name": "redis_command_2e4777_memory_stats",
                "status": "success",
                "args": {},
                "result_preview": {"allocator_frag_ratio": 1.09},
            },
        ],
        actual_routing_decision="redis_chat",
    )

    assert results.required_tool_calls[0].status.value == "passed"
    assert results.required_tool_calls[1].status.value == "passed"


def test_score_structured_assertions_infers_re_admin_alias_from_concrete_name():
    scenario = EvalScenario.model_validate(
        {
            "id": "assertion-inferred-admin-identity",
            "name": "Assertion inferred admin identity",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-14",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {"lane": "full_turn", "query": "Investigate cluster health."},
            "scope": {
                "target_catalog": [
                    {
                        "handle": "tgt_cluster_checkout_global",
                        "kind": "cluster",
                        "display_name": "checkout-global enterprise cluster",
                        "resource_id": "re-cluster-checkout-global",
                        "cluster_type": "redis_enterprise",
                        "capabilities": ["admin"],
                    }
                ],
                "bound_targets": ["tgt_cluster_checkout_global"],
            },
            "tools": {
                "redis_enterprise_admin": {
                    "get_cluster_info": {"result": {"ok": True}},
                    "list_databases": {"result": {"ok": True}},
                }
            },
            "expectations": {
                "required_tool_calls": [
                    {
                        "provider_family": "redis_enterprise_admin",
                        "operation": "get_cluster_info",
                        "target_handle": "tgt_cluster_checkout_global",
                    },
                    {
                        "provider_family": "redis_enterprise_admin",
                        "operation": "list_databases",
                        "target_handle": "tgt_cluster_checkout_global",
                    },
                ]
            },
        }
    )

    results = score_structured_assertions(
        scenario,
        tool_trace=[
            {
                "concrete_name": "re_admin_0fc9e2_get_cluster_info",
                "status": "success",
                "args": {},
                "result_preview": {"cluster_state": "active"},
            },
            {
                "concrete_name": "re_admin_0fc9e2_list_databases",
                "status": "success",
                "args": {},
                "result_preview": {"databases": []},
            },
        ],
    )

    assert results.required_tool_calls[0].status.value == "passed"
    assert results.required_tool_calls[1].status.value == "passed"


def test_score_structured_assertions_infers_mcp_identity_from_concrete_name():
    scenario = EvalScenario.model_validate(
        {
            "id": "assertion-inferred-mcp-identity",
            "name": "Assertion inferred MCP identity",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-14",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {"lane": "agent_only", "agent": "chat", "query": "Review incident."},
            "tools": {
                "mcp_servers": {
                    "example_incident": {
                        "capability": "diagnostics",
                        "tools": {
                            "get_incident": {"result": {"ok": True}},
                            "get_metric_window": {"result": {"ok": True}},
                        },
                    }
                }
            },
            "expectations": {
                "required_tool_calls": [
                    {
                        "provider_family": "mcp",
                        "server_name": "example_incident",
                        "operation": "get_incident",
                    },
                    {
                        "provider_family": "mcp",
                        "server_name": "example_incident",
                        "operation": "get_metric_window",
                    },
                ]
            },
        }
    )

    results = score_structured_assertions(
        scenario,
        tool_trace=[
            {
                "concrete_name": "mcp_example_incident_deadbeef_get_incident",
                "status": "success",
                "args": {"incident_id": "inc-1"},
            },
            {
                "concrete_name": "mcp_example_incident_deadbeef_get_metric_window",
                "status": "success",
                "args": {"incident_id": "inc-1", "service": "checkout-api"},
            },
        ],
    )

    assert results.required_tool_calls[0].status.value == "passed"
    assert results.required_tool_calls[1].status.value == "passed"


def test_score_structured_assertions_checks_required_response_patterns():
    scenario = EvalScenario.model_validate(
        {
            "id": "assertion-response-patterns",
            "name": "Assertion response patterns",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-14",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {"lane": "agent_only", "agent": "chat", "query": "Write the report."},
            "expectations": {
                "required_response_patterns": [
                    r"(?m)^# Incident Brief: .+$",
                    r"(?m)^## Summary$",
                    r"(?m)^## Open Questions$",
                ]
            },
        }
    )

    results = score_structured_assertions(
        scenario,
        final_answer=(
            "# Incident Brief: checkout-prod\n\n## Summary\n\nAll good.\n\n## Open Questions\n"
        ),
    )

    assert [row.status.value for row in results.required_response_patterns] == [
        "passed",
        "passed",
        "passed",
    ]


def test_score_structured_assertions_fails_missing_required_response_patterns():
    scenario = EvalScenario.model_validate(
        {
            "id": "assertion-response-patterns-missing",
            "name": "Assertion response patterns missing",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-14",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {"lane": "agent_only", "agent": "chat", "query": "Write the report."},
            "expectations": {
                "required_response_patterns": [
                    r"(?m)^## Node-level findings$",
                ]
            },
        }
    )

    results = score_structured_assertions(
        scenario,
        final_answer="# Incident Brief: checkout-prod\n\n## Summary\n",
    )

    assert results.required_response_patterns[0].status.value == "failed"
    assert results.all_passed is False


def test_score_structured_assertions_normalizes_routing_aliases():
    scenario = _scenario().model_copy(
        update={
            "expectations": _scenario().expectations.model_copy(
                update={"expected_routing_decision": "chat"}
            )
        }
    )

    results = score_structured_assertions(
        scenario,
        actual_routing_decision="redis_chat",
    )

    assert results.expected_routing_decision is not None
    assert results.expected_routing_decision.status.value == "passed"
    assert results.all_passed is False


def test_score_structured_assertions_normalizes_phrase_whitespace():
    scenario = _scenario()

    results = score_structured_assertions(
        scenario,
        tool_trace=[],
        retrieved_sources=[],
        final_answer=(
            "Maintenance   mode caused the   failover. Do not recommend CONFIG   GET changes."
        ),
        actual_routing_decision="redis_triage",
    )

    assert results.required_findings[0].status.value == "passed"
    assert results.forbidden_claims[0].status.value == "passed"


def test_score_structured_assertions_ignores_negated_forbidden_claims():
    scenario = _scenario()

    results = score_structured_assertions(
        scenario,
        tool_trace=[],
        retrieved_sources=[],
        final_answer=(
            "Maintenance mode caused the failover. Do not recommend CONFIG SET changes yet."
        ),
        actual_routing_decision="redis_triage",
    )

    assert results.required_findings[0].status.value == "passed"
    assert results.forbidden_claims[0].status.value == "passed"


def test_score_structured_assertions_still_flags_positive_forbidden_claims():
    scenario = _scenario()

    results = score_structured_assertions(
        scenario,
        tool_trace=[],
        retrieved_sources=[],
        final_answer=(
            "Maintenance mode caused the failover. Recommend CONFIG SET changes immediately."
        ),
        actual_routing_decision="redis_triage",
    )

    assert results.forbidden_claims[0].status.value == "failed"


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

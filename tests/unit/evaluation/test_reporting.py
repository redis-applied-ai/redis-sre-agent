import json

from redis_sre_agent.evaluation.judge import EvaluationResult
from redis_sre_agent.evaluation.reporting import (
    AssertionStatus,
    EvalArtifactBundle,
    EvalArtifactFiles,
    EvalAssertionResult,
    JudgeRubricScores,
    StructuredAssertionResults,
    ToolIdentityMapEntry,
    build_eval_artifact_bundle,
    write_eval_artifact_bundle,
)
from redis_sre_agent.evaluation.scenarios import EvalScenario, ExecutionLane, ScenarioProvenance
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


def _scenario() -> EvalScenario:
    return EvalScenario.model_validate(
        {
            "id": "redis/memory-pressure-oss",
            "name": "Redis memory pressure OSS",
            "provenance": _scenario_provenance().model_dump(mode="json"),
            "execution": {
                "lane": "full_turn",
                "query": "Why is memory usage climbing?",
                "agent": "redis_triage",
                "llm_mode": "replay",
            },
            "knowledge": {
                "mode": "full",
                "version": "2026-04-01",
            },
        }
    )


def test_structured_assertion_results_derive_all_passed():
    results = StructuredAssertionResults(
        required_tool_calls=[
            EvalAssertionResult(status=AssertionStatus.PASSED),
            EvalAssertionResult(status=AssertionStatus.SKIPPED),
        ],
        forbidden_claims=[EvalAssertionResult(status=AssertionStatus.PASSED)],
    )

    assert results.all_passed is True


def test_judge_rubric_scores_convert_from_existing_judge_output():
    source = EvaluationResult(
        test_case_id="tc-1",
        overall_score=91.0,
        criteria_scores={"technical_accuracy": 24.0},
        strengths=["Accurate diagnosis"],
        weaknesses=[],
        factual_errors=[],
        missing_elements=[],
        detailed_feedback="Solid answer.",
    )

    scores = JudgeRubricScores.from_evaluation_result(source, pass_threshold=85.0)

    assert scores.overall_score == 91.0
    assert scores.passed is True
    assert scores.criteria_scores == {"technical_accuracy": 24.0}


def test_tool_identity_map_entry_round_trips_normalized_concrete_identity():
    concrete = ConcreteToolIdentity(
        concrete_name="re_admin_abcdef_get_cluster_info",
        provider_name="re_admin",
        provider_family="redis_enterprise_admin",
        operation="get_cluster_info",
        target_handle="tgt_cluster_prod_east",
        requires_instance=True,
    )

    row = ToolIdentityMapEntry.from_concrete(concrete)

    assert row.provider_family == "redis_enterprise_admin"
    assert row.operation == "get_cluster_info"
    assert row.concrete_tool_name == "re_admin_abcdef_get_cluster_info"
    assert row.target_handle == "tgt_cluster_prod_east"
    assert row.provider_name == "re_admin"
    assert row.requires_instance is True
    assert row.logical == LogicalToolIdentity(
        provider_family="redis_enterprise_admin",
        operation="get_cluster_info",
        target_handle="tgt_cluster_prod_east",
    )


def test_full_turn_artifact_bundle_requires_judge_scores():
    assertions = StructuredAssertionResults(
        required_tool_calls=[EvalAssertionResult(status=AssertionStatus.PASSED)]
    )

    try:
        EvalArtifactBundle(
            scenario_id="redis/memory-pressure-oss",
            git_sha="abc1234",
            scenario_provenance=_scenario_provenance(),
            agent_type="redis_triage",
            model="gpt-5.4",
            system_prompt_digest="prompt-digest",
            knowledge_mode="full",
            tool_trace=[],
            retrieved_source_trace=[],
            final_answer="Investigate memory pressure.",
            structured_assertion_results=assertions,
            execution_lane=ExecutionLane.FULL_TURN,
            llm_mode="replay",
        )
    except ValueError as exc:
        assert "must include judge_scores" in str(exc)
    else:
        raise AssertionError("Expected full_turn artifact bundle to require judge_scores")


def test_artifact_bundle_derives_overall_pass_and_markdown_summary():
    assertions = StructuredAssertionResults(
        required_tool_calls=[EvalAssertionResult(status=AssertionStatus.PASSED)]
    )
    judge_scores = JudgeRubricScores(
        overall_score=92.0,
        criteria_scores={"technical_accuracy": 24.0},
        detailed_feedback="Solid answer.",
        passed=True,
    )

    bundle = EvalArtifactBundle(
        scenario_id="redis/enterprise-maintenance-mode",
        scenario_name="Enterprise maintenance mode",
        git_sha="abc1234",
        scenario_provenance=_scenario_provenance(),
        agent_type="redis_triage",
        model="gpt-5.4",
        system_prompt_digest="prompt-digest",
        knowledge_mode="full",
        tool_trace=[
            {
                "tool_key": "re_admin_abcdef_list_nodes",
                "name": "list_nodes",
                "args": {},
                "status": "success",
                "data": {"nodes": []},
            }
        ],
        retrieved_source_trace=[{"id": "doc-1", "title": "Runbook"}],
        startup_context_snapshot="Pinned docs loaded",
        final_answer="Maintenance mode caused the failover.",
        structured_assertion_results=assertions,
        judge_scores=judge_scores,
        execution_lane=ExecutionLane.FULL_TURN,
        llm_mode="replay",
    )

    assert bundle.overall_pass is True
    assert bundle.golden_review_status == "approved"
    assert bundle.artifacts == EvalArtifactFiles()
    assert "Judge score: 92.0" in bundle.to_markdown_summary()
    assert "- Pass: yes" in bundle.to_markdown_summary()
    assert "- Tool trace entries: 1" in bundle.to_markdown_summary()
    assert "- Tool identity mappings: 0" in bundle.to_markdown_summary()


def test_build_eval_artifact_bundle_derives_metadata_and_identity_rows():
    assertions = StructuredAssertionResults(
        required_tool_calls=[EvalAssertionResult(status=AssertionStatus.PASSED)]
    )
    judge_result = EvaluationResult(
        test_case_id="redis/memory-pressure-oss",
        overall_score=95.0,
        criteria_scores={"technical_accuracy": 24.0},
        strengths=["Used the right Redis command"],
        weaknesses=[],
        factual_errors=[],
        missing_elements=[],
        detailed_feedback="Solid response.",
    )
    concrete_identity = ConcreteToolIdentity(
        concrete_name="redis_command_deadbeef_redis_command",
        provider_name="redis_command",
        provider_family="redis_command",
        operation="redis_command",
        target_handle="cache-prod",
        requires_instance=True,
    )

    bundle = build_eval_artifact_bundle(
        scenario=_scenario(),
        git_sha="abc1234",
        final_answer="Memory fragmentation is elevated.",
        startup_context_snapshot={"pinned": ["redis-memory-runbook"]},
        tool_trace=[
            {
                "tool_key": "redis_command_deadbeef_redis_command",
                "status": "success",
                "args": {"command": "INFO memory"},
                "data": {"used_memory_human": "4.1G"},
            }
        ],
        retrieved_source_trace=[
            {
                "id": "redis-memory-runbook",
                "source_kind": "runbook",
                "title": "Redis Memory Runbook",
            }
        ],
        structured_assertion_results=assertions,
        judge_scores=judge_result,
        judge_pass_threshold=90.0,
        tool_identity_map=[concrete_identity],
        system_prompt_digest="prompt-digest",
        model="gpt-5.4",
        baseline_policy="locked",
    )

    assert bundle.overall_pass is True
    assert bundle.agent_type == "redis_triage"
    assert bundle.llm_mode == "replay"
    assert bundle.knowledge_mode == "full"
    assert bundle.corpus_version == "2026-04-01"
    assert bundle.golden_review_status == "approved"
    assert bundle.judge_scores is not None
    assert bundle.judge_scores.passed is True
    assert bundle.tool_identity_map[0].model_dump(
        mode="json"
    ) == ToolIdentityMapEntry.from_concrete(concrete_identity).model_dump(mode="json")
    assert bundle.structured_assertions[0].assertion_type == "required_tool_call"


def test_write_eval_artifact_bundle_persists_bundle_and_sidecars(tmp_path):
    bundle = build_eval_artifact_bundle(
        scenario=_scenario(),
        git_sha="abc1234",
        final_answer="Investigate fragmentation.",
        startup_context_snapshot={"pinned": ["redis-memory-runbook"]},
        tool_trace=[
            {
                "tool_key": "redis_command_deadbeef_redis_command",
                "status": "success",
                "args": {"command": "INFO memory"},
                "data": {"used_memory_human": "4.1G"},
            }
        ],
        retrieved_source_trace=[
            {
                "id": "redis-memory-runbook",
                "source_kind": "runbook",
                "title": "Redis Memory Runbook",
            }
        ],
        structured_assertion_results=StructuredAssertionResults(
            required_tool_calls=[EvalAssertionResult(status=AssertionStatus.PASSED)]
        ),
        judge_scores=JudgeRubricScores(
            overall_score=91.0,
            criteria_scores={"technical_accuracy": 23.0},
            detailed_feedback="Good enough.",
            passed=True,
        ),
    )

    paths = write_eval_artifact_bundle(bundle, tmp_path)

    assert paths["bundle_dir"] == tmp_path.resolve() / "redis/memory-pressure-oss"
    assert paths["report_json"].exists()
    assert paths["report_markdown"].exists()
    assert paths["tool_trace_json"].exists()
    assert paths["retrieved_sources_json"].exists()
    assert paths["startup_context_json"].exists()

    report_json = json.loads(paths["report_json"].read_text(encoding="utf-8"))
    assert report_json["scenario_id"] == "redis/memory-pressure-oss"
    assert report_json["scenario_provenance"]["source_pack_version"] == "2026-04-01"

    tool_trace_json = json.loads(paths["tool_trace_json"].read_text(encoding="utf-8"))
    assert tool_trace_json[0]["concrete_name"] == "redis_command_deadbeef_redis_command"

    markdown = paths["report_markdown"].read_text(encoding="utf-8")
    assert "# Eval Report: redis/memory-pressure-oss" in markdown
    assert "- Judge score: 91.0" in markdown

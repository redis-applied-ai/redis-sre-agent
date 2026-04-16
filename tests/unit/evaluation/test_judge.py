from types import SimpleNamespace

import pytest

from redis_sre_agent.evaluation.judge import (
    SREAgentJudge,
    build_default_eval_criteria,
    build_eval_judge_test_case,
    evaluate_eval_scenario_response,
)
from redis_sre_agent.evaluation.report_schema import (
    AssertionStatus,
    EvalAssertionResult,
    StructuredAssertionResults,
)
from redis_sre_agent.evaluation.scenarios import EvalScenario


def _scenario() -> EvalScenario:
    return EvalScenario.model_validate(
        {
            "id": "redis/memory-pressure",
            "name": "Redis memory pressure",
            "description": "Judge should see startup context, tool traces, and expected findings.",
            "provenance": {
                "source_kind": "redis_docs",
                "source_pack": "redis-docs-curated",
                "source_pack_version": "2026-04-01",
                "golden": {
                    "expectation_basis": "human_from_docs",
                    "review_status": "approved",
                },
            },
            "execution": {
                "lane": "full_turn",
                "query": "Why is Redis using so much memory?",
                "agent": "redis_triage",
                "route_via_router": False,
            },
            "expectations": {
                "required_findings": ["memory fragmentation is elevated"],
                "required_sources": ["redis-memory-runbook"],
                "required_tool_calls": [
                    {
                        "provider_family": "redis",
                        "operation": "redis_command",
                        "target_handle": "cache-prod",
                    }
                ],
                "expected_routing_decision": "triage",
            },
        }
    )


def test_build_default_eval_criteria_matches_phase_five_rubric():
    criteria = build_default_eval_criteria()

    assert [criterion.name for criterion in criteria] == [
        "technical_accuracy",
        "completeness_relevance",
        "actionability",
        "evidence_use",
        "instruction_following",
        "citation_quality",
    ]


def test_build_eval_judge_test_case_includes_rich_context():
    scenario = _scenario()
    assertions = StructuredAssertionResults(
        required_tool_calls=[
            EvalAssertionResult(
                status=AssertionStatus.PASSED,
                message="Observed redis command call.",
            )
        ]
    )

    payload = build_eval_judge_test_case(
        scenario,
        startup_context={"startup": ["redis-memory-runbook"]},
        tool_trace=[
            {
                "concrete_name": "redis_cache_prod_redis_command",
                "logical": {
                    "provider_family": "redis",
                    "operation": "redis_command",
                    "target_handle": "cache-prod",
                },
                "status": "success",
                "args": {"command": "INFO memory"},
            }
        ],
        retrieved_sources=[
            {
                "source_id": "redis-memory-runbook",
                "source_kind": "runbook",
                "title": "Redis Memory Runbook",
            }
        ],
        structured_assertions=assertions,
        actual_routing_decision="triage",
    )

    assert payload["id"] == "redis/memory-pressure"
    assert payload["execution_lane"] == "full_turn"
    assert payload["expectations"]["required_findings"] == ["memory fragmentation is elevated"]
    assert "tool:redis/redis_command" in payload["expected_elements"]
    assert payload["actual_routing_decision"] == "triage"
    assert payload["structured_assertions"]["all_passed"] is True


def test_judge_sanitizes_fenced_json_with_trailing_commas():
    sanitized = SREAgentJudge._sanitize_judge_response(
        """```json
{
  "overall_score": 85,
  "criteria_scores": {
    "technical_accuracy": 90,
    "evidence_use": 80,
  },
  "strengths": ["Grounded in tool output"],
  "weaknesses": [],
}
```"""
    )

    assert (
        sanitized
        == """
{
  "overall_score": 85,
  "criteria_scores": {
    "technical_accuracy": 90,
    "evidence_use": 80
  },
  "strengths": ["Grounded in tool output"],
  "weaknesses": []
}
""".strip()
    )


def test_judge_sanitizes_smart_quotes_and_newlines_inside_strings():
    sanitized = SREAgentJudge._sanitize_judge_response(
        """```json
{
  "overall_score": 80,
  "detailed_feedback": "Line one
Line two with smart quote ”
}
```"""
    )

    assert "\nLine two" not in sanitized
    assert 'smart quote "' in sanitized
    assert sanitized.endswith("}")


@pytest.mark.asyncio
async def test_evaluate_eval_scenario_response_sends_enriched_prompt(monkeypatch):
    captured_messages: list[dict[str, str]] = []

    class _StubLLM:
        async def ainvoke(self, messages):
            captured_messages.extend(messages)
            return SimpleNamespace(
                content="""
{
  "overall_score": 91,
  "criteria_scores": {"technical_accuracy": 24, "evidence_use": 15},
  "strengths": ["Grounded in tool output"],
  "weaknesses": [],
  "factual_errors": [],
  "missing_elements": [],
  "detailed_feedback": "Good evidence use."
}
""".strip()
            )

    monkeypatch.setattr(
        "redis_sre_agent.evaluation.judge.create_mini_llm",
        lambda model: _StubLLM(),
    )

    judge = SREAgentJudge()
    scenario = _scenario()
    assertions = StructuredAssertionResults(
        required_tool_calls=[EvalAssertionResult(status=AssertionStatus.PASSED)],
        expected_routing_decision=EvalAssertionResult(status=AssertionStatus.PASSED),
    )

    result = await evaluate_eval_scenario_response(
        scenario=scenario,
        agent_response=(
            "Memory fragmentation is elevated. The INFO memory output and Redis Memory Runbook "
            "both point to allocator overhead."
        ),
        judge=judge,
        startup_context={"startup_documents": ["redis-memory-runbook"]},
        tool_trace=[
            {
                "concrete_name": "redis_cache_prod_redis_command",
                "logical": {
                    "provider_family": "redis",
                    "operation": "redis_command",
                    "target_handle": "cache-prod",
                },
                "status": "success",
                "args": {"command": "INFO memory"},
                "result_preview": {"used_memory_human": "4.1G"},
            }
        ],
        retrieved_sources=[
            {
                "source_id": "redis-memory-runbook",
                "source_kind": "runbook",
                "title": "Redis Memory Runbook",
                "metadata": {"document_hash": "doc-123"},
            }
        ],
        structured_assertions=assertions,
        actual_routing_decision="triage",
    )

    assert result.overall_score == 91
    user_prompt = captured_messages[1]["content"]
    assert "## Startup Context" in user_prompt
    assert "## Tool Trace" in user_prompt
    assert "## Retrieved Sources" in user_prompt
    assert "## Expectation Set" in user_prompt
    assert "## Structured Assertions" in user_prompt
    assert "## Actual Routing Decision" in user_prompt
    assert "redis/memory-pressure" in user_prompt
    assert "redis-memory-runbook" in user_prompt
    assert "INFO memory" in user_prompt


@pytest.mark.asyncio
async def test_evaluate_eval_scenario_response_accepts_fenced_json_with_trailing_commas(
    monkeypatch,
):
    class _StubLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(
                content="""```json
{
  "overall_score": 85,
  "criteria_scores": {
    "technical_accuracy": 90,
    "evidence_use": 80,
  },
  "strengths": ["Grounded in tool output"],
  "weaknesses": [],
  "factual_errors": [],
  "missing_elements": [],
  "detailed_feedback": "Good evidence use.",
}
```"""
            )

    monkeypatch.setattr(
        "redis_sre_agent.evaluation.judge.create_mini_llm",
        lambda model: _StubLLM(),
    )

    result = await evaluate_eval_scenario_response(
        scenario=_scenario(),
        agent_response="Answer",
        startup_context={},
        tool_trace=[],
        retrieved_sources=[],
        structured_assertions=StructuredAssertionResults(),
        actual_routing_decision="triage",
    )

    assert result.overall_score == 85
    assert result.criteria_scores == {"technical_accuracy": 90, "evidence_use": 80}


@pytest.mark.asyncio
async def test_evaluate_eval_scenario_response_accepts_smart_quotes_and_newlines(
    monkeypatch,
):
    class _StubLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(
                content="""```json
{
  "overall_score": 80,
  "criteria_scores": {
    "technical_accuracy": 85
  },
  "strengths": ["Clear limitation statement"],
  "weaknesses": [],
  "factual_errors": [],
  "missing_elements": [],
  "detailed_feedback": "Line one
Line two with smart quote ”
}
```"""
            )

    monkeypatch.setattr(
        "redis_sre_agent.evaluation.judge.create_mini_llm",
        lambda model: _StubLLM(),
    )

    result = await evaluate_eval_scenario_response(
        scenario=_scenario(),
        agent_response="Answer",
        startup_context={},
        tool_trace=[],
        retrieved_sources=[],
        structured_assertions=StructuredAssertionResults(),
        actual_routing_decision="triage",
    )

    assert result.overall_score == 80
    assert result.criteria_scores == {"technical_accuracy": 85}

"""LLM-as-Judge evaluation system for Redis SRE Agent responses."""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Sequence

import yaml
from pydantic import BaseModel, Field

from ..core.llm_helpers import create_mini_llm
from .scenarios import EvalScenario

logger = logging.getLogger(__name__)
_FENCED_JSON_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",(?=\s*[}\]])")
_SMART_PUNCT_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
)


class EvaluationCriteria(BaseModel):
    """Evaluation criteria for judging agent responses."""

    name: str = Field(..., description="Name of the evaluation criteria")
    description: str = Field(..., description="What this criteria evaluates")
    weight: float = Field(default=1.0, description="Weight for this criteria (0-1)")
    required_elements: List[str] = Field(
        default_factory=list, description="Required elements that should be present"
    )
    accuracy_points: List[str] = Field(
        default_factory=list, description="Specific technical accuracy points"
    )


class EvaluationResult(BaseModel):
    """Result of evaluating an agent response."""

    test_case_id: str
    overall_score: float = Field(..., description="Overall score (0-100)")
    criteria_scores: Dict[str, float] = Field(..., description="Score per criteria")
    strengths: List[str] = Field(default_factory=list, description="What the agent did well")
    weaknesses: List[str] = Field(default_factory=list, description="Areas for improvement")
    factual_errors: List[str] = Field(
        default_factory=list, description="Technical inaccuracies found"
    )
    missing_elements: List[str] = Field(
        default_factory=list, description="Required elements that were missing"
    )
    detailed_feedback: str = Field(..., description="Detailed judge feedback")


class SREAgentJudge:
    """LLM-as-Judge for evaluating Redis SRE agent responses."""

    JUDGE_SYSTEM_PROMPT = """You are an expert Redis SRE evaluator. Your role is to judge the quality, accuracy, and completeness of Redis SRE agent responses.

## Evaluation Framework

You will evaluate responses across the criteria supplied in the user prompt.

Common rubric dimensions include:
- technical accuracy
- completeness and relevance
- actionability
- evidence use
- instruction-following quality
- citation quality
- communication quality

## Response Format

Provide your evaluation as JSON:

```json
{
  "overall_score": <0-100>,
  "criteria_scores": {
    "<criteria_name>": <numeric score>
  },
  "strengths": ["specific strength 1", "specific strength 2"],
  "weaknesses": ["specific weakness 1", "specific weakness 2"],
  "factual_errors": ["error 1 with explanation", "error 2 with explanation"],
  "missing_elements": ["missing element 1", "missing element 2"],
  "detailed_feedback": "Comprehensive feedback explaining scores and observations"
}
```

Be rigorous in your evaluation. Technical accuracy is paramount - any Redis misconceptions should result in significant point deductions.
"""

    def __init__(self):
        """Initialize the judge with LLM."""
        self.llm = create_mini_llm(model="gpt-4o-mini")

    @staticmethod
    def _serialize_for_prompt(value: Any) -> str:
        """Render prompt context deterministically for the judge."""

        if value is None:
            return "None"
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, indent=2, sort_keys=True)
        except TypeError:
            return str(value)

    @staticmethod
    def _sanitize_judge_response(content: str) -> str:
        """Normalize common JSON-adjacent judge output into parseable JSON."""

        response_text = content.strip()
        fenced_match = _FENCED_JSON_RE.match(response_text)
        if fenced_match:
            response_text = fenced_match.group(1).strip()
        response_text = response_text.translate(_SMART_PUNCT_TRANSLATION)
        response_text = _TRAILING_COMMA_RE.sub("", response_text)

        cleaned: list[str] = []
        in_string = False
        escaping = False
        for char in response_text:
            if escaping:
                cleaned.append(char)
                escaping = False
                continue
            if char == "\\":
                cleaned.append(char)
                escaping = True
                continue
            if char == '"':
                cleaned.append(char)
                in_string = not in_string
                continue
            if in_string and char in {"\n", "\r", "\t"}:
                cleaned.append(" ")
                continue
            cleaned.append(char)
        return "".join(cleaned)

    @staticmethod
    def _parse_judge_payload(content: str) -> dict[str, Any]:
        """Parse sanitized judge output with a YAML fallback for near-JSON."""

        response_text = SREAgentJudge._sanitize_judge_response(content)
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            parsed = yaml.safe_load(response_text)
        if not isinstance(parsed, dict):
            raise ValueError("Judge response must deserialize to an object")
        return parsed

    async def evaluate_response(
        self, agent_response: str, test_case: Dict[str, Any], criteria: List[EvaluationCriteria]
    ) -> EvaluationResult:
        """Evaluate an agent response against criteria.

        Args:
            agent_response: The agent's response to evaluate
            test_case: Test case context (query, diagnostic_data, etc.)
            criteria: List of evaluation criteria

        Returns:
            EvaluationResult with scores and feedback
        """
        try:
            criteria_details = "\n".join(
                [
                    f"**{c.name}** (Weight: {c.weight}): {c.description}\n"
                    f"Required elements: {', '.join(c.required_elements) if c.required_elements else 'None'}\n"
                    f"Accuracy points: {', '.join(c.accuracy_points) if c.accuracy_points else 'None'}"
                    for c in criteria
                ]
            )

            prompt_sections = [
                "## Test Case Context",
                f"**Scenario ID**: {test_case.get('id', 'unknown')}",
                f"**Scenario Name**: {test_case.get('name', 'N/A')}",
                f"**User Query**: {test_case.get('query', 'N/A')}",
            ]
            if test_case.get("scenario_description"):
                prompt_sections.append(
                    f"**Scenario Description**: {test_case.get('scenario_description')}"
                )
            if test_case.get("execution_lane"):
                prompt_sections.append(f"**Execution Lane**: {test_case.get('execution_lane')}")

            prompt_sections.extend(
                [
                    "",
                    "## Startup Context",
                    self._serialize_for_prompt(test_case.get("startup_context")),
                    "",
                    "## Tool Trace",
                    self._serialize_for_prompt(test_case.get("tool_trace")),
                    "",
                    "## Retrieved Sources",
                    self._serialize_for_prompt(test_case.get("retrieved_sources")),
                    "",
                    "## Expectation Set",
                    self._serialize_for_prompt(test_case.get("expectations")),
                    "",
                    "## Structured Assertions",
                    self._serialize_for_prompt(test_case.get("structured_assertions")),
                ]
            )

            if test_case.get("actual_routing_decision") is not None:
                prompt_sections.extend(
                    [
                        "",
                        "## Actual Routing Decision",
                        self._serialize_for_prompt(test_case.get("actual_routing_decision")),
                    ]
                )

            if test_case.get("diagnostic_data") is not None:
                prompt_sections.extend(
                    [
                        "",
                        "## Diagnostic Data",
                        self._serialize_for_prompt(test_case.get("diagnostic_data")),
                    ]
                )

            if test_case.get("expected_elements") is not None:
                prompt_sections.extend(
                    [
                        "",
                        "## Expected Elements",
                        self._serialize_for_prompt(test_case.get("expected_elements")),
                    ]
                )

            prompt_sections.extend(
                [
                    "",
                    "## Evaluation Criteria",
                    criteria_details,
                    "",
                    "## Agent Response to Evaluate",
                    agent_response,
                    "",
                    "Please evaluate this Redis SRE agent response thoroughly and provide your assessment.",
                ]
            )
            evaluation_prompt = "\n".join(prompt_sections)

            messages = [
                {"role": "system", "content": self.JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": evaluation_prompt},
            ]

            response = await self.llm.ainvoke(messages)

            # Parse judge response
            try:
                result_data = self._parse_judge_payload(response.content)

                return EvaluationResult(
                    test_case_id=test_case.get("id", "unknown"),
                    overall_score=result_data.get("overall_score", 0),
                    criteria_scores=result_data.get("criteria_scores", {}),
                    strengths=result_data.get("strengths", []),
                    weaknesses=result_data.get("weaknesses", []),
                    factual_errors=result_data.get("factual_errors", []),
                    missing_elements=result_data.get("missing_elements", []),
                    detailed_feedback=result_data.get("detailed_feedback", "No feedback provided"),
                )

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse judge response: {e}")
                logger.error(f"Raw response: {response.content}")

                return EvaluationResult(
                    test_case_id=test_case.get("id", "unknown"),
                    overall_score=0,
                    criteria_scores={},
                    strengths=[],
                    weaknesses=["Evaluation failed - invalid judge response format"],
                    factual_errors=[],
                    missing_elements=[],
                    detailed_feedback=f"Judge evaluation failed: {str(e)}",
                )

        except Exception as e:
            logger.error(f"Error during evaluation: {e}")
            return EvaluationResult(
                test_case_id=test_case.get("id", "unknown"),
                overall_score=0,
                criteria_scores={},
                strengths=[],
                weaknesses=[f"Evaluation error: {str(e)}"],
                factual_errors=[],
                missing_elements=[],
                detailed_feedback=f"Evaluation failed due to error: {str(e)}",
            )


def build_default_eval_criteria() -> list[EvaluationCriteria]:
    """Return the default rubric criteria for eval-scenario judging."""

    return [
        EvaluationCriteria(
            name="technical_accuracy",
            description="Correct Redis and SRE diagnosis with no material factual errors.",
            weight=0.25,
        ),
        EvaluationCriteria(
            name="completeness_relevance",
            description="Coverage of the user's request and the scenario's expected findings.",
            weight=0.2,
        ),
        EvaluationCriteria(
            name="actionability",
            description="Clear, prioritized next steps and operational guidance.",
            weight=0.2,
        ),
        EvaluationCriteria(
            name="evidence_use",
            description="Grounding in the provided startup context, tool results, and retrieved sources.",
            weight=0.15,
        ),
        EvaluationCriteria(
            name="instruction_following",
            description="Alignment with the scenario expectations and source-constrained instructions.",
            weight=0.1,
        ),
        EvaluationCriteria(
            name="citation_quality",
            description="Use of specific source or tool evidence when making claims.",
            weight=0.1,
        ),
    ]


def _serialize_expectation_set(scenario: EvalScenario) -> dict[str, Any]:
    """Build the judge-facing expectation block for one scenario."""

    return scenario.expectations.model_dump(mode="json")


def build_eval_judge_test_case(
    scenario: EvalScenario,
    *,
    startup_context: Any = None,
    tool_trace: Sequence[Any] | None = None,
    retrieved_sources: Sequence[Any] | None = None,
    structured_assertions: Any = None,
    actual_routing_decision: str | None = None,
    diagnostic_data: Any = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the richer judge input payload for one eval scenario."""

    expected_elements: list[str] = []
    expected_elements.extend(scenario.expectations.required_findings)
    expected_elements.extend(
        f"source:{source}" for source in scenario.expectations.required_sources
    )
    expected_elements.extend(
        f"tool:{tool.provider_family}/{tool.operation}"
        for tool in scenario.expectations.required_tool_calls
    )
    if scenario.expectations.expected_routing_decision:
        expected_elements.append(f"routing:{scenario.expectations.expected_routing_decision}")

    payload = {
        "id": scenario.id,
        "name": scenario.name,
        "query": scenario.execution.query,
        "scenario_description": scenario.description,
        "execution_lane": scenario.execution.lane.value,
        "startup_context": startup_context,
        "tool_trace": list(tool_trace or []),
        "retrieved_sources": list(retrieved_sources or []),
        "expectations": _serialize_expectation_set(scenario),
        "structured_assertions": structured_assertions.model_dump(mode="json")
        if hasattr(structured_assertions, "model_dump")
        else structured_assertions,
        "actual_routing_decision": actual_routing_decision,
        "diagnostic_data": diagnostic_data,
        "expected_elements": expected_elements,
    }
    if extra_fields:
        payload.update(extra_fields)
    return payload


async def evaluate_eval_scenario_response(
    *,
    scenario: EvalScenario,
    agent_response: str,
    judge: SREAgentJudge | None = None,
    criteria: Iterable[EvaluationCriteria] | None = None,
    startup_context: Any = None,
    tool_trace: Sequence[Any] | None = None,
    retrieved_sources: Sequence[Any] | None = None,
    structured_assertions: Any = None,
    actual_routing_decision: str | None = None,
    diagnostic_data: Any = None,
    extra_fields: dict[str, Any] | None = None,
) -> EvaluationResult:
    """Evaluate one scenario response using the richer Phase 5 judge context."""

    active_judge = judge or SREAgentJudge()
    test_case = build_eval_judge_test_case(
        scenario,
        startup_context=startup_context,
        tool_trace=tool_trace,
        retrieved_sources=retrieved_sources,
        structured_assertions=structured_assertions,
        actual_routing_decision=actual_routing_decision,
        diagnostic_data=diagnostic_data,
        extra_fields=extra_fields,
    )
    active_criteria = list(criteria or build_default_eval_criteria())
    return await active_judge.evaluate_response(agent_response, test_case, active_criteria)


class EvaluationSuite:
    """Test suite for evaluating Redis SRE agent performance."""

    def __init__(self):
        """Initialize evaluation suite."""
        self.judge = SREAgentJudge()
        self.test_cases = []

    def add_test_case(self, test_case: Dict[str, Any]):
        """Add a test case to the suite."""
        self.test_cases.append(test_case)

    async def run_evaluation(self, agent_function) -> List[EvaluationResult]:
        """Run full evaluation suite against an agent function.

        Args:
            agent_function: Async function that takes (query, session_id, user_id) and returns response

        Returns:
            List of evaluation results
        """
        results = []

        for i, test_case in enumerate(self.test_cases):
            logger.info(
                f"Running test case {i + 1}/{len(self.test_cases)}: {test_case.get('name', 'Unnamed')}"
            )

            try:
                # Get agent response
                response = await agent_function(
                    test_case["query"], f"eval_session_{i}", "evaluation_user"
                )

                # Evaluate response
                criteria = [EvaluationCriteria(**c) for c in test_case.get("criteria", [])]
                result = await self.judge.evaluate_response(response, test_case, criteria)
                results.append(result)

                logger.info(f"Test case {i + 1} completed: Score {result.overall_score:.1f}/100")

            except Exception as e:
                logger.error(f"Failed to run test case {i + 1}: {e}")
                results.append(
                    EvaluationResult(
                        test_case_id=test_case.get("id", f"test_{i}"),
                        overall_score=0,
                        criteria_scores={},
                        strengths=[],
                        weaknesses=[f"Test execution failed: {str(e)}"],
                        factual_errors=[],
                        missing_elements=[],
                        detailed_feedback=f"Test case failed to execute: {str(e)}",
                    )
                )

        return results

    def generate_report(self, results: List[EvaluationResult]) -> str:
        """Generate a comprehensive evaluation report.

        Args:
            results: List of evaluation results

        Returns:
            Formatted report string
        """
        if not results:
            return "No evaluation results available."

        total_score = sum(r.overall_score for r in results) / len(results)

        report = f"""# Redis SRE Agent Evaluation Report

**Date**: {datetime.now().isoformat()}
**Test Cases**: {len(results)}
**Average Score**: {total_score:.1f}/100

## Summary Statistics

"""

        # Score distribution
        score_ranges = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "<60": 0}
        for result in results:
            score = result.overall_score
            if score >= 90:
                score_ranges["90-100"] += 1
            elif score >= 80:
                score_ranges["80-89"] += 1
            elif score >= 70:
                score_ranges["70-79"] += 1
            elif score >= 60:
                score_ranges["60-69"] += 1
            else:
                score_ranges["<60"] += 1

        report += "**Score Distribution:**\n"
        for range_name, count in score_ranges.items():
            percentage = (count / len(results)) * 100
            report += f"- {range_name}: {count} tests ({percentage:.1f}%)\n"

        # Common issues
        all_weaknesses = []
        all_errors = []
        for result in results:
            all_weaknesses.extend(result.weaknesses)
            all_errors.extend(result.factual_errors)

        if all_weaknesses:
            report += "\n**Most Common Weaknesses:**\n"
            weakness_counts = {}
            for weakness in all_weaknesses:
                weakness_counts[weakness] = weakness_counts.get(weakness, 0) + 1

            for weakness, count in sorted(
                weakness_counts.items(), key=lambda x: x[1], reverse=True
            )[:5]:
                report += f"- {weakness} ({count} cases)\n"

        if all_errors:
            report += "\n**Factual Errors Found:**\n"
            error_counts = {}
            for error in all_errors:
                error_counts[error] = error_counts.get(error, 0) + 1

            for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                report += f"- {error} ({count} cases)\n"

        # Individual test results
        report += "\n## Individual Test Results\n\n"
        for i, result in enumerate(results, 1):
            report += f"### Test Case {i}\n"
            report += f"**Score**: {result.overall_score:.1f}/100\n"
            report += f"**Criteria Scores**: {', '.join(f'{k}: {v}' for k, v in result.criteria_scores.items())}\n"

            if result.strengths:
                report += f"**Strengths**: {'; '.join(result.strengths)}\n"
            if result.weaknesses:
                report += f"**Weaknesses**: {'; '.join(result.weaknesses)}\n"
            if result.factual_errors:
                report += f"**Factual Errors**: {'; '.join(result.factual_errors)}\n"

            report += "\n"

        return report


__all__ = [
    "EvaluationCriteria",
    "EvaluationResult",
    "EvaluationSuite",
    "SREAgentJudge",
    "build_default_eval_criteria",
    "build_eval_judge_test_case",
    "evaluate_eval_scenario_response",
]

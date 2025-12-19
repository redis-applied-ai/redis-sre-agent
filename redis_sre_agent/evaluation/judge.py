"""LLM-as-Judge evaluation system for Redis SRE Agent responses."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ..core.llm_helpers import create_mini_llm

logger = logging.getLogger(__name__)


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

You will evaluate responses across these dimensions:

### 1. Technical Accuracy (25 points)
- Correct interpretation of Redis metrics and diagnostics
- Accurate understanding of Redis internals (memory management, keyspace operations, etc.)
- Proper use of Redis terminology and concepts
- No factual errors or misconceptions

### 2. Completeness & Relevance (25 points)
- Addresses all aspects of the user's question
- Includes all required elements specified in criteria
- Stays focused on relevant Redis/SRE topics
- Provides appropriate level of detail

### 3. Actionability (20 points)
- Provides clear, specific recommendations
- Includes step-by-step procedures when appropriate
- Suggests monitoring, prevention, and remediation strategies
- Prioritizes actions appropriately (critical vs. nice-to-have)

### 4. Evidence-Based Reasoning (20 points)
- Uses diagnostic data to support conclusions
- References specific metrics and values
- Shows clear reasoning path from data to recommendations
- Avoids unsupported assumptions

### 5. Communication Quality (10 points)
- Clear, professional language
- Well-organized structure
- Appropriate technical level for SRE audience
- Includes necessary context and explanations

## Response Format

Provide your evaluation as JSON:

```json
{
  "overall_score": <0-100>,
  "criteria_scores": {
    "technical_accuracy": <0-25>,
    "completeness_relevance": <0-25>,
    "actionability": <0-20>,
    "evidence_based": <0-20>,
    "communication": <0-10>
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
            # Prepare evaluation prompt
            criteria_details = "\n".join(
                [
                    f"**{c.name}** (Weight: {c.weight}): {c.description}\n"
                    f"Required elements: {', '.join(c.required_elements) if c.required_elements else 'None'}\n"
                    f"Accuracy points: {', '.join(c.accuracy_points) if c.accuracy_points else 'None'}"
                    for c in criteria
                ]
            )

            evaluation_prompt = f"""
## Test Case Context
**User Query**: {test_case.get("query", "N/A")}
**Diagnostic Data**: {json.dumps(test_case.get("diagnostic_data", {}), indent=2) if test_case.get("diagnostic_data") else "None provided"}
**Expected Elements**: {test_case.get("expected_elements", "None specified")}

## Evaluation Criteria
{criteria_details}

## Agent Response to Evaluate
{agent_response}

Please evaluate this Redis SRE agent response thoroughly and provide your assessment.
"""

            messages = [
                {"role": "system", "content": self.JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": evaluation_prompt},
            ]

            response = await self.llm.ainvoke(messages)

            # Parse judge response
            try:
                # Handle markdown code blocks if present
                response_text = response.content.strip()
                if response_text.startswith("```json"):
                    response_text = response_text[7:]  # Remove ```json
                if response_text.endswith("```"):
                    response_text = response_text[:-3]  # Remove ```
                response_text = response_text.strip()

                result_data = json.loads(response_text)

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

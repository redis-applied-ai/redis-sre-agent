"""
Simplified Multi-Turn Agent Evaluation - Tests tool usage in agent responses.

This simplified version focuses on:
1. Whether agent uses multiple tools strategically
2. Quality of the final response
3. Evidence of tool usage in the response content
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

import openai
import pytest

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent
from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai.api_key = settings.openai_api_key

# Test scenarios requiring multiple tools
MULTI_TOOL_SCENARIOS = [
    {
        "scenario_id": "memory_spike",
        "scenario": "Memory Spike Investigation",
        "user_query": "Our Redis memory usage just spiked from 2GB to 7GB in 30 minutes and users are experiencing timeouts. I need to understand what's happening and get immediate guidance.",
        "expected_tools": [
            "search_knowledge_base",
            "check_service_health",
            "analyze_system_metrics",
        ],
        "expected_content": ["memory", "diagnostic", "immediate actions", "monitoring"],
    },
    {
        "scenario_id": "connection_cascade",
        "scenario": "Connection Cascade Failure",
        "user_query": "URGENT: Redis connections climbed from 500 to 2800 in 10 minutes, new connections failing with max clients reached. Multiple services down. What should I do?",
        "expected_tools": ["search_knowledge_base", "check_service_health"],
        "expected_content": ["connection", "maxclients", "immediate", "troubleshooting"],
    },
    {
        "scenario_id": "performance_mystery",
        "scenario": "Performance Degradation",
        "user_query": "Application latency increased 300% over 2 hours but Redis looks fine and traffic is normal. Help me investigate this systematically.",
        "expected_tools": [
            "search_knowledge_base",
            "check_service_health",
            "analyze_system_metrics",
        ],
        "expected_content": ["latency", "performance", "investigation", "diagnostic"],
    },
]

EVALUATION_PROMPT = """You are evaluating an AI agent's response to a Redis troubleshooting scenario.

Assess the response quality across these dimensions:

1. **Tool Usage Evidence** (1-5): Does the response show evidence of using multiple diagnostic tools?
2. **Technical Quality** (1-5): Is the technical guidance accurate and appropriate?
3. **Systematic Approach** (1-5): Does it follow a logical troubleshooting methodology?
4. **Actionability** (1-5): Are there clear, executable steps provided?
5. **Completeness** (1-5): Does it address both immediate and longer-term concerns?

Look for evidence of:
- Knowledge base searches (references to runbooks, best practices)
- Health checks (current Redis status, diagnostics)
- Metric analysis (performance data, trends)
- Systematic investigation approach
- Immediate vs long-term recommendations

Rate each dimension 1-5 and provide your assessment as JSON."""


async def evaluate_agent_response(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate a single scenario with the agent."""

    logger.info(f"🔍 Testing scenario: {scenario['scenario']}")

    try:
        # Initialize agent
        agent = SRELangGraphAgent()

        # Get agent response
        response = await agent.process_query(
            query=scenario["user_query"],
            session_id=f"test_{scenario['scenario_id']}",
            user_id="evaluator",
        )

        # Analyze response content for tool usage evidence
        tool_evidence = analyze_tool_evidence(response, scenario["expected_tools"])
        content_quality = analyze_content_quality(response, scenario["expected_content"])

        # Get LLM evaluation
        llm_evaluation = await evaluate_with_llm(scenario, response)

        result = {
            "scenario_id": scenario["scenario_id"],
            "scenario": scenario["scenario"],
            "user_query": scenario["user_query"],
            "agent_response": response,
            "response_length": len(response),
            "tool_evidence": tool_evidence,
            "content_quality": content_quality,
            "llm_evaluation": llm_evaluation,
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(f"✅ Completed: Score {llm_evaluation.get('overall_score', 0):.1f}/5.0")
        return result

    except Exception as e:
        logger.error(f"❌ Error evaluating {scenario['scenario_id']}: {e}")
        return {
            "scenario_id": scenario["scenario_id"],
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


def analyze_tool_evidence(response: str, expected_tools: List[str]) -> Dict[str, Any]:
    """Analyze response for evidence of tool usage."""

    response_lower = response.lower()

    evidence = {
        "knowledge_search_evidence": any(
            term in response_lower
            for term in ["runbook", "documentation", "best practices", "procedure", "guide"]
        ),
        "health_check_evidence": any(
            term in response_lower
            for term in ["redis info", "connection count", "memory usage", "diagnostic", "status"]
        ),
        "metrics_analysis_evidence": any(
            term in response_lower
            for term in ["metrics", "monitoring", "trend", "pattern", "analysis", "threshold"]
        ),
        "systematic_approach": any(
            term in response_lower
            for term in ["first", "next step", "then", "follow", "systematic", "methodology"]
        ),
        "immediate_actions": any(
            term in response_lower
            for term in ["immediate", "urgent", "now", "first priority", "emergency"]
        ),
    }

    # Count evidence types
    evidence_count = sum(1 for v in evidence.values() if v)
    evidence["evidence_score"] = evidence_count / len(evidence)

    return evidence


def analyze_content_quality(response: str, expected_content: List[str]) -> Dict[str, Any]:
    """Analyze response content quality."""

    response_lower = response.lower()

    # Check for expected content keywords
    content_coverage = {}
    for keyword in expected_content:
        content_coverage[keyword] = keyword.lower() in response_lower

    coverage_score = sum(content_coverage.values()) / len(expected_content)

    return {
        "content_coverage": content_coverage,
        "coverage_score": coverage_score,
        "response_sections": count_response_sections(response),
        "has_commands": "redis-cli" in response_lower or "config" in response_lower,
        "has_recommendations": any(
            term in response_lower
            for term in ["recommend", "suggest", "should", "consider", "advice"]
        ),
    }


def count_response_sections(response: str) -> int:
    """Count structured sections in response."""
    sections = 0
    for marker in ["##", "###", "**", "1.", "2.", "3.", "-"]:
        if marker in response:
            sections += response.count(marker)
    return min(sections, 10)  # Cap at reasonable number


async def evaluate_with_llm(scenario: Dict[str, Any], response: str) -> Dict[str, Any]:
    """Use LLM to evaluate response quality."""

    evaluation_prompt = f"""
## Scenario: {scenario["scenario"]}

**User Query**: "{scenario["user_query"]}"

**Agent Response**:
{response}

## Evaluation

Please evaluate this Redis SRE agent response on these 5 dimensions (1-5 scale):

1. **Tool Usage Evidence**: Does the response show evidence of using diagnostic tools?
2. **Technical Quality**: Is the guidance technically sound and appropriate?
3. **Systematic Approach**: Does it follow logical troubleshooting methodology?
4. **Actionability**: Are there clear, executable steps?
5. **Completeness**: Does it address immediate and long-term needs?

Expected tools: {scenario.get("expected_tools", [])}
Expected content: {scenario.get("expected_content", [])}

Format as JSON:
```json
{{
    "overall_score": <average of 5 dimensions>,
    "tool_usage_evidence": <1-5>,
    "technical_quality": <1-5>,
    "systematic_approach": <1-5>,
    "actionability": <1-5>,
    "completeness": <1-5>,
    "analysis": "<detailed assessment>",
    "strengths": ["strength1", "strength2"],
    "weaknesses": ["weakness1", "weakness2"],
    "tool_evidence_assessment": "<assessment of tool usage evidence>"
}}
```
"""

    try:
        response_obj = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": EVALUATION_PROMPT},
                {"role": "user", "content": evaluation_prompt},
            ],
            temperature=0.1,
            max_tokens=1500,
        )

        # Parse JSON response
        judge_response = response_obj.choices[0].message.content

        # Extract JSON
        json_start = judge_response.find("```json")
        json_end = judge_response.find("```", json_start + 7)

        if json_start != -1 and json_end != -1:
            json_content = judge_response[json_start + 7 : json_end].strip()
            evaluation = json.loads(json_content)
        else:
            evaluation = json.loads(judge_response)

        return evaluation

    except Exception as e:
        logger.error(f"LLM evaluation failed: {e}")
        return {"error": str(e), "overall_score": 0}


async def run_multi_tool_evaluation() -> List[Dict[str, Any]]:
    """Run multi-tool agent evaluation."""

    logger.info("🚀 Starting Multi-Tool Agent Evaluation")
    logger.info("=" * 60)

    results = []

    for i, scenario in enumerate(MULTI_TOOL_SCENARIOS, 1):
        logger.info(f"\n[{i}/{len(MULTI_TOOL_SCENARIOS)}] Testing: {scenario['scenario']}")

        result = await evaluate_agent_response(scenario)
        results.append(result)

    # Generate summary
    logger.info("\n📊 Multi-Tool Evaluation Summary")
    logger.info("=" * 60)

    successful_results = [r for r in results if "error" not in r]

    if successful_results:
        scores = [r["llm_evaluation"]["overall_score"] for r in successful_results]
        evidence_scores = [r["tool_evidence"]["evidence_score"] for r in successful_results]
        coverage_scores = [r["content_quality"]["coverage_score"] for r in successful_results]

        avg_score = sum(scores) / len(scores)
        avg_evidence = sum(evidence_scores) / len(evidence_scores)
        avg_coverage = sum(coverage_scores) / len(coverage_scores)

        logger.info("📈 Performance Metrics:")
        logger.info(f"   🎯 Average Overall Score: {avg_score:.2f}/5.0")
        logger.info(f"   🔧 Average Tool Evidence: {avg_evidence:.1%}")
        logger.info(f"   📝 Average Content Coverage: {avg_coverage:.1%}")

        # Performance distribution
        excellent = sum(1 for s in scores if s >= 4.0)
        good = sum(1 for s in scores if 3.0 <= s < 4.0)
        needs_improvement = sum(1 for s in scores if s < 3.0)

        logger.info("\n📊 Performance Distribution:")
        logger.info(f"   🟢 Excellent (≥4.0): {excellent}/{len(successful_results)}")
        logger.info(f"   🟡 Good (3.0-3.9): {good}/{len(successful_results)}")
        logger.info(
            f"   🔴 Needs Improvement (<3.0): {needs_improvement}/{len(successful_results)}"
        )

        # Show detailed results
        logger.info("\n🔍 Detailed Results:")
        for result in successful_results:
            score = result["llm_evaluation"]["overall_score"]
            evidence_score = result["tool_evidence"]["evidence_score"]
            scenario = result["scenario"]

            logger.info(f"   • {scenario}: {score:.1f}/5.0 (Tool Evidence: {evidence_score:.1%})")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"eval_reports/multi_tool_evaluation_{timestamp}.json"

    # Ensure eval_reports directory exists
    os.makedirs("eval_reports", exist_ok=True)

    with open(results_file, "w") as f:
        json.dump(
            {
                "evaluation_timestamp": datetime.now().isoformat(),
                "total_scenarios": len(MULTI_TOOL_SCENARIOS),
                "successful_evaluations": len(successful_results),
                "summary_metrics": {
                    "avg_overall_score": avg_score if successful_results else 0,
                    "avg_tool_evidence": avg_evidence if successful_results else 0,
                    "avg_content_coverage": avg_coverage if successful_results else 0,
                },
                "detailed_results": results,
            },
            f,
            indent=2,
        )

    logger.info(f"\n💾 Results saved to: {results_file}")

    if avg_score >= 4.0:
        logger.info("\n🎉 EXCELLENT: Multi-tool agent capabilities meet production standards!")
    elif avg_score >= 3.0:
        logger.info("\n✅ GOOD: Strong multi-tool usage with room for optimization")
    else:
        logger.info("\n⚠️  NEEDS WORK: Multi-tool workflow requires improvements")

    return results


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multi_tool_evaluation():
    """Test multi-tool agent evaluation."""
    results = await run_multi_tool_evaluation()

    # Assertions
    assert len(results) > 0, "Should have evaluation results"

    successful_results = [r for r in results if "error" not in r]
    assert len(successful_results) > 0, "Should have successful evaluations"

    # Check tool evidence
    for result in successful_results:
        evidence = result["tool_evidence"]
        assert evidence["evidence_score"] > 0, "Should show some tool usage evidence"

    # Check evaluation quality
    for result in successful_results:
        evaluation = result["llm_evaluation"]
        assert "overall_score" in evaluation, "Should have overall score"
        assert 0 <= evaluation["overall_score"] <= 5, "Score should be in valid range"


if __name__ == "__main__":
    asyncio.run(run_multi_tool_evaluation())

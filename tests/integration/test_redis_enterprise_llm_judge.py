"""
LLM Judge Evaluation for Redis Enterprise-Specific Scenarios.

Tests that the SRE Agent provides enterprise-specific guidance when working with
Redis Enterprise instances, including proper recognition of enterprise features,
configuration options, and operational procedures.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

import openai
import pytest

from redis_sre_agent.agent.langgraph_agent import get_sre_agent
from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai.api_key = settings.openai_api_key

ENTERPRISE_JUDGE_SYSTEM_PROMPT = """You are an expert Redis Enterprise Site Reliability Engineer with 10+ years of production experience managing Redis Enterprise clusters at scale. You will evaluate agent responses to Redis Enterprise-specific scenarios.

For each scenario and agent response, assess:
1. **Enterprise Recognition**: Does the agent recognize this is a Redis Enterprise instance?
2. **Enterprise-Specific Guidance**: Are recommendations specific to Redis Enterprise features/tools?
3. **Technical Accuracy**: Are Redis Enterprise concepts and commands correct?
4. **Operational Relevance**: How well does the response address enterprise operational needs?
5. **Production Readiness**: Would this guidance be helpful for real Redis Enterprise incidents?

Rate each aspect on a scale of 1-5:
- 5: Excellent - Perfect Redis Enterprise expertise
- 4: Good - Strong enterprise knowledge with minor gaps
- 3: Adequate - Some enterprise awareness but generic advice
- 2: Poor - Limited enterprise understanding
- 1: Unacceptable - No enterprise recognition or incorrect guidance

Provide specific reasoning focusing on Redis Enterprise features like rladmin, cluster management, database tuning, and enterprise-specific monitoring."""

# Redis Enterprise-specific scenarios
REDIS_ENTERPRISE_SCENARIOS = [
    {
        "scenario": "Redis Enterprise Buffer Configuration Crisis",
        "context": "Redis Enterprise database with slave_buffer and client_buffer set to 1MB each. Database using 54MB memory with active replication. Risk of buffer overflows and connection drops.",
        "query": "Redis Enterprise database has very low buffer settings (slave_buffer=1MB, client_buffer=1MB) but is using 54MB of memory. What are the risks and how should I optimize these settings?",
        "instance_type": "enterprise",
        "expected_enterprise_elements": [
            "rladmin tune command",
            "Redis Enterprise buffer management",
            "Enterprise-specific buffer recommendations",
            "Cluster-level configuration",
            "Enterprise monitoring tools",
        ],
    },
    {
        "scenario": "Redis Enterprise Cluster Node Maintenance",
        "context": "Need to perform maintenance on Redis Enterprise cluster node. Single-node cluster preventing standard maintenance mode due to shard evacuation requirements.",
        "query": "How do I put a Redis Enterprise cluster node into maintenance mode when I have a single-node cluster and can't evacuate shards?",
        "instance_type": "enterprise",
        "expected_enterprise_elements": [
            "rladmin maintenance_mode command",
            "Enterprise cluster management",
            "Shard evacuation options",
            "Enterprise-specific maintenance procedures",
            "Cluster topology considerations",
        ],
    },
    {
        "scenario": "Redis Enterprise Database Memory Pressure",
        "context": "Redis Enterprise database approaching memory limit with enterprise-specific eviction policies. Need to optimize memory usage while maintaining enterprise features.",
        "query": "Redis Enterprise database memory usage is high and approaching limits. How should I optimize memory for enterprise workloads?",
        "instance_type": "enterprise",
        "expected_enterprise_elements": [
            "Enterprise memory management",
            "rladmin memory tuning",
            "Enterprise-specific eviction policies",
            "Database-level memory configuration",
            "Enterprise monitoring and alerting",
        ],
    },
    {
        "scenario": "Redis Enterprise Replication Lag Investigation",
        "context": "Redis Enterprise cluster experiencing replication lag between master and replica databases. Enterprise-specific replication features need tuning.",
        "query": "Redis Enterprise cluster has replication lag issues. How do I diagnose and fix replication problems in an enterprise environment?",
        "instance_type": "enterprise",
        "expected_enterprise_elements": [
            "Enterprise replication monitoring",
            "rladmin replication commands",
            "Enterprise-specific replication tuning",
            "Cluster replication topology",
            "Enterprise replication metrics",
        ],
    },
    {
        "scenario": "Redis Enterprise Security Configuration",
        "context": "Need to implement enterprise-grade security for Redis Enterprise cluster including authentication, encryption, and access controls.",
        "query": "How do I configure enterprise security features for Redis Enterprise including authentication and encryption?",
        "instance_type": "enterprise",
        "expected_enterprise_elements": [
            "Enterprise authentication methods",
            "rladmin security configuration",
            "Enterprise encryption features",
            "Role-based access control",
            "Enterprise security best practices",
        ],
    },
    {
        "scenario": "Redis Enterprise Performance Optimization",
        "context": "Redis Enterprise database performance degradation under high load. Need enterprise-specific performance tuning and optimization strategies.",
        "query": "Redis Enterprise database performance is degrading under load. What enterprise-specific optimizations should I apply?",
        "instance_type": "enterprise",
        "expected_enterprise_elements": [
            "Enterprise performance tuning",
            "rladmin tune commands",
            "Enterprise-specific metrics",
            "Database-level optimization",
            "Enterprise performance monitoring",
        ],
    },
]


async def evaluate_enterprise_response_with_llm_judge(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate a Redis Enterprise scenario response using LLM judge."""

    logger.info(f"🏢 Evaluating Enterprise Scenario: {scenario['scenario']}")

    # Get agent response
    agent = get_sre_agent()

    # Create enhanced query that indicates this is an enterprise instance
    enhanced_query = f"""Instance Type: Redis Enterprise
    
{scenario["query"]}

Context: {scenario["context"]}"""

    try:
        response = await agent.process_query_with_fact_check(
            query=enhanced_query,
            session_id="enterprise_test_session",
            user_id="enterprise_test_user",
        )
    except Exception as e:
        logger.error(f"Agent query failed: {e}")
        return {
            "scenario": scenario["scenario"],
            "query": scenario["query"],
            "error": f"Agent query failed: {str(e)}",
            "overall_score": 0,
        }

    # Prepare context for the judge
    judge_prompt = f"""
## Redis Enterprise Scenario: {scenario["scenario"]}

**Context**: {scenario["context"]}

**Query**: "{scenario["query"]}"

**Expected Enterprise Elements**: {", ".join(scenario["expected_enterprise_elements"])}

## Agent Response:

{response}

## Evaluation Required:

Please evaluate this agent response from the perspective of an expert Redis Enterprise SRE. Rate each aspect (1-5) and provide detailed reasoning:

1. **Enterprise Recognition** (1-5): Does the agent recognize this is Redis Enterprise?
2. **Enterprise-Specific Guidance** (1-5): Are recommendations specific to Redis Enterprise?
3. **Technical Accuracy** (1-5): Are Redis Enterprise concepts and commands correct?
4. **Operational Relevance** (1-5): How well does it address enterprise operational needs?
5. **Production Readiness** (1-5): Useful for real Redis Enterprise incidents?

Format your response as JSON:
```json
{{
    "overall_score": <average of 5 aspects>,
    "enterprise_recognition": <1-5>,
    "enterprise_specific_guidance": <1-5>,
    "technical_accuracy": <1-5>,
    "operational_relevance": <1-5>,
    "production_readiness": <1-5>,
    "detailed_analysis": "<comprehensive analysis>",
    "enterprise_elements_found": ["<element 1>", "<element 2>"],
    "enterprise_elements_missing": ["<missing element 1>", "<missing element 2>"],
    "strengths": ["<strength 1>", "<strength 2>"],
    "weaknesses": ["<weakness 1>", "<weakness 2>"],
    "improvements": ["<improvement 1>", "<improvement 2>"]
}}
```
"""

    # Call GPT-4o for evaluation
    try:
        judge_response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": ENTERPRISE_JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": judge_prompt},
            ],
            max_tokens=2000,
        )

        # Extract and parse the JSON response
        judge_content = judge_response.choices[0].message.content

        # Try to extract JSON from the response
        json_start = judge_content.find("```json")
        json_end = judge_content.find("```", json_start + 7)

        if json_start != -1 and json_end != -1:
            json_content = judge_content[json_start + 7 : json_end].strip()
            evaluation = json.loads(json_content)
        else:
            # Fallback: try to parse the entire response as JSON
            evaluation = json.loads(judge_content)

        # Add metadata
        evaluation["scenario"] = scenario["scenario"]
        evaluation["query"] = scenario["query"]
        evaluation["agent_response"] = response
        evaluation["expected_enterprise_elements"] = scenario["expected_enterprise_elements"]

        return evaluation

    except Exception as e:
        logger.error(f"LLM judge evaluation failed: {e}")
        return {
            "scenario": scenario["scenario"],
            "query": scenario["query"],
            "error": f"Judge evaluation failed: {str(e)}",
            "overall_score": 0,
        }


async def run_redis_enterprise_llm_judge_evaluation():
    """Run comprehensive Redis Enterprise LLM judge evaluation."""

    logger.info("🏢 Starting Redis Enterprise LLM Judge Evaluation")
    logger.info("=" * 70)

    evaluations = []

    # Evaluate each enterprise scenario
    for scenario in REDIS_ENTERPRISE_SCENARIOS:
        try:
            evaluation = await evaluate_enterprise_response_with_llm_judge(scenario)
            evaluations.append(evaluation)

            # Brief summary for each scenario
            if "error" not in evaluation:
                score = evaluation.get("overall_score", 0)
                logger.info(f"✅ {scenario['scenario']}: Overall Score {score:.1f}/5.0")
            else:
                logger.error(
                    f"❌ {scenario['scenario']}: Evaluation failed - {evaluation.get('error')}"
                )

        except Exception as e:
            logger.error(f"❌ Failed to evaluate {scenario['scenario']}: {e}")

    # Aggregate results
    logger.info("\n📊 Redis Enterprise LLM Judge Evaluation Results")
    logger.info("=" * 70)

    valid_evaluations = [e for e in evaluations if "error" not in e]

    if valid_evaluations:
        # Calculate overall statistics
        avg_overall = sum(e["overall_score"] for e in valid_evaluations) / len(valid_evaluations)
        avg_enterprise_recognition = sum(
            e["enterprise_recognition"] for e in valid_evaluations
        ) / len(valid_evaluations)
        avg_enterprise_guidance = sum(
            e["enterprise_specific_guidance"] for e in valid_evaluations
        ) / len(valid_evaluations)
        avg_technical = sum(e["technical_accuracy"] for e in valid_evaluations) / len(
            valid_evaluations
        )
        avg_operational = sum(e["operational_relevance"] for e in valid_evaluations) / len(
            valid_evaluations
        )
        avg_production = sum(e["production_readiness"] for e in valid_evaluations) / len(
            valid_evaluations
        )

        logger.info("Redis Enterprise Performance Summary:")
        logger.info(f"  📈 Overall Score: {avg_overall:.2f}/5.0")
        logger.info(f"  🏢 Enterprise Recognition: {avg_enterprise_recognition:.2f}/5.0")
        logger.info(f"  🎯 Enterprise-Specific Guidance: {avg_enterprise_guidance:.2f}/5.0")
        logger.info(f"  🔧 Technical Accuracy: {avg_technical:.2f}/5.0")
        logger.info(f"  ⚙️  Operational Relevance: {avg_operational:.2f}/5.0")
        logger.info(f"  🏭 Production Readiness: {avg_production:.2f}/5.0")

        # Performance distribution
        excellent = sum(1 for e in valid_evaluations if e["overall_score"] >= 4.0)
        good = sum(1 for e in valid_evaluations if 3.0 <= e["overall_score"] < 4.0)
        needs_improvement = sum(1 for e in valid_evaluations if e["overall_score"] < 3.0)

        logger.info("\nRedis Enterprise Performance Distribution:")
        logger.info(
            f"  🟢 Excellent (≥4.0): {excellent}/{len(valid_evaluations)} ({excellent / len(valid_evaluations) * 100:.1f}%)"
        )
        logger.info(
            f"  🟡 Good (3.0-3.9): {good}/{len(valid_evaluations)} ({good / len(valid_evaluations) * 100:.1f}%)"
        )
        logger.info(
            f"  🔴 Needs Improvement (<3.0): {needs_improvement}/{len(valid_evaluations)} ({needs_improvement / len(valid_evaluations) * 100:.1f}%)"
        )

        # Detailed per-scenario results
        logger.info("\n🔍 Detailed Redis Enterprise Results by Scenario:")
        logger.info("-" * 70)

        for evaluation in valid_evaluations:
            score = evaluation["overall_score"]
            scenario = evaluation["scenario"]

            performance_level = (
                "🟢 Excellent"
                if score >= 4.0
                else "🟡 Good"
                if score >= 3.0
                else "🔴 Needs Improvement"
            )

            logger.info(f"\n{scenario}: {performance_level} ({score:.1f}/5.0)")
            logger.info(f'  Query: "{evaluation["query"]}"')

            if evaluation.get("enterprise_elements_found"):
                logger.info(
                    f"  Enterprise Elements Found: {', '.join(evaluation['enterprise_elements_found'][:3])}"
                )
            if evaluation.get("enterprise_elements_missing"):
                logger.info(
                    f"  Missing Enterprise Elements: {', '.join(evaluation['enterprise_elements_missing'][:2])}"
                )
            if evaluation.get("strengths"):
                logger.info(f"  Strengths: {', '.join(evaluation['strengths'][:2])}")
            if evaluation.get("weaknesses"):
                logger.info(f"  Weaknesses: {', '.join(evaluation['weaknesses'][:2])}")

    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"eval_reports/redis_enterprise_llm_judge_{timestamp}.json"

    # Ensure eval_reports directory exists
    os.makedirs("eval_reports", exist_ok=True)

    with open(results_file, "w") as f:
        json.dump(
            {
                "evaluation_timestamp": datetime.now().isoformat(),
                "scenarios_evaluated": len(REDIS_ENTERPRISE_SCENARIOS),
                "successful_evaluations": len(valid_evaluations),
                "summary_metrics": {
                    "avg_overall_score": avg_overall if valid_evaluations else 0,
                    "avg_enterprise_recognition": avg_enterprise_recognition
                    if valid_evaluations
                    else 0,
                    "avg_enterprise_specific_guidance": avg_enterprise_guidance
                    if valid_evaluations
                    else 0,
                    "avg_technical_accuracy": avg_technical if valid_evaluations else 0,
                    "avg_operational_relevance": avg_operational if valid_evaluations else 0,
                    "avg_production_readiness": avg_production if valid_evaluations else 0,
                },
                "detailed_evaluations": evaluations,
            },
            f,
            indent=2,
        )

    logger.info(f"\n💾 Detailed Redis Enterprise results saved to: {results_file}")

    # Enterprise-specific assessment
    if valid_evaluations:
        enterprise_recognition_avg = sum(
            e["enterprise_recognition"] for e in valid_evaluations
        ) / len(valid_evaluations)
        enterprise_guidance_avg = sum(
            e["enterprise_specific_guidance"] for e in valid_evaluations
        ) / len(valid_evaluations)

        if avg_overall >= 4.0 and enterprise_recognition_avg >= 4.0:
            logger.info("\n🎉 EXCELLENT: Agent demonstrates strong Redis Enterprise expertise!")
        elif avg_overall >= 3.0 and enterprise_recognition_avg >= 3.0:
            logger.info(
                "\n✅ GOOD: Agent shows Redis Enterprise awareness with room for improvement"
            )
        else:
            logger.info(
                "\n⚠️  NEEDS WORK: Agent requires better Redis Enterprise recognition and guidance"
            )
    else:
        logger.info("\n⚠️  No valid evaluations; infrastructure may be unavailable.")

    return evaluations


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_enterprise_llm_judge_evaluation():
    """Test comprehensive Redis Enterprise LLM judge evaluation."""
    # Skip if OpenAI API key is not available
    if (
        not os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY") == "test-openai-key"
    ):
        pytest.skip("OPENAI_API_KEY not set or using test key - skipping OpenAI integration test")

    evaluations = await run_redis_enterprise_llm_judge_evaluation()

    # Assertions for test validation
    assert len(evaluations) > 0, "Should have evaluation results"

    valid_evaluations = [e for e in evaluations if "error" not in e]
    assert len(valid_evaluations) > 0, "Should have valid evaluations"

    # Check that we have reasonable scores (not all zeros)
    avg_score = sum(e["overall_score"] for e in valid_evaluations) / len(valid_evaluations)
    assert avg_score > 0, "Should have positive average score"
    assert avg_score <= 5.0, "Score should not exceed maximum"

    # Verify evaluation structure
    for evaluation in valid_evaluations:
        assert "overall_score" in evaluation
        assert "enterprise_recognition" in evaluation
        assert "enterprise_specific_guidance" in evaluation
        assert "technical_accuracy" in evaluation
        assert "operational_relevance" in evaluation
        assert "production_readiness" in evaluation
        assert "scenario" in evaluation
        assert "query" in evaluation

    # Enterprise-specific assertions
    enterprise_recognition_scores = [e["enterprise_recognition"] for e in valid_evaluations]
    avg_enterprise_recognition = sum(enterprise_recognition_scores) / len(
        enterprise_recognition_scores
    )

    # Agent should recognize Redis Enterprise instances (score >= 3.0)
    assert avg_enterprise_recognition >= 3.0, (
        f"Agent should recognize Redis Enterprise instances (avg: {avg_enterprise_recognition:.2f})"
    )

    # At least 50% of scenarios should have good enterprise recognition (>= 4.0)
    good_enterprise_recognition = sum(1 for score in enterprise_recognition_scores if score >= 4.0)
    assert good_enterprise_recognition >= len(valid_evaluations) * 0.5, (
        "At least 50% should have good enterprise recognition"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_single_redis_enterprise_scenario():
    """Test evaluation of a single Redis Enterprise scenario for faster feedback."""
    # Skip if OpenAI API key is not available
    if (
        not os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY") == "test-openai-key"
    ):
        pytest.skip("OPENAI_API_KEY not set or using test key - skipping OpenAI integration test")

    # Test the buffer configuration scenario
    scenario = REDIS_ENTERPRISE_SCENARIOS[0]  # Buffer configuration crisis

    evaluation = await evaluate_enterprise_response_with_llm_judge(scenario)

    assert "error" not in evaluation, f"Evaluation failed: {evaluation.get('error')}"
    assert evaluation["overall_score"] > 0
    assert evaluation["overall_score"] <= 5.0
    assert evaluation["scenario"] == scenario["scenario"]

    # Enterprise-specific assertions
    assert evaluation["enterprise_recognition"] >= 2.0, "Should recognize this is Redis Enterprise"
    assert "enterprise_elements_found" in evaluation, "Should identify enterprise elements"


if __name__ == "__main__":
    asyncio.run(run_redis_enterprise_llm_judge_evaluation())

"""
LLM Judge Evaluation Integration Tests for Redis SRE Agent Search Quality.

Uses GPT-4o to evaluate search results from the perspective of an expert Redis SRE.
Assesses technical accuracy, practical usefulness, and completeness of retrieved documents.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

import openai
import pytest
import redis

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.tasks import search_knowledge_base

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai.api_key = settings.openai_api_key


def check_redis_search_available() -> bool:
    """Check if Redis with search capabilities is available (Redis 8+ or Redis Stack)."""
    try:
        r = redis.Redis.from_url(settings.redis_url)

        # Test if FT.SEARCH command is available by checking command info
        try:
            # Try to get command info for FT.SEARCH
            r.execute_command("COMMAND", "INFO", "FT.SEARCH")
            return True
        except redis.ResponseError:
            # FT.SEARCH command not available
            pass

        # Fallback: check for search module in Redis with modules
        modules = r.module_list()
        for module in modules:
            if module[b"name"] in [b"search", b"searchlight"] and module[b"ver"] >= 20600:
                return True
        return False
    except Exception:
        return False


redis_search_available = check_redis_search_available()
redis_search_required = pytest.mark.skipif(
    not redis_search_available, reason="Redis 8+ or Redis Stack with search module required"
)


JUDGE_SYSTEM_PROMPT = """You are an expert Redis Site Reliability Engineer with 10+ years of production experience managing Redis at scale. You will evaluate search results from a Redis SRE knowledge base.

For each search query and its results, assess:
1. **Technical Accuracy**: Are the retrieved documents technically correct and up-to-date?
2. **Practical Relevance**: How well do the results address the specific operational need in the query?
3. **Completeness**: Do the results provide sufficient information to resolve the issue?
4. **Actionability**: Are there clear, executable steps an SRE can follow?
5. **Production Readiness**: Would these results be helpful during a real production incident?

Rate each aspect on a scale of 1-5:
- 5: Excellent - Perfect for production SRE use
- 4: Good - Minor gaps but very useful
- 3: Adequate - Helpful but needs supplementation
- 2: Poor - Significant gaps or issues
- 1: Unacceptable - Incorrect, irrelevant, or dangerous

Provide specific reasoning for your ratings and suggest improvements."""


# Original 5 scenarios (connection-focused)
CORE_SCENARIOS = [
    {
        "scenario": "Production Incident: E-commerce Flash Sale",
        "context": "Black Friday sale causing Redis connection spike from 200 to 4,500 connections. Users experiencing checkout timeouts and 'connection refused' errors. Need immediate troubleshooting guidance.",
        "query": "Redis connection limit exceeded too many clients troubleshooting",
        "expected_needs": [
            "Immediate remediation steps",
            "Root cause analysis commands",
            "Prevention strategies",
            "Monitoring setup",
        ],
    },
    {
        "scenario": "Performance Investigation",
        "context": "Redis latency spiked from 1ms to 50ms during peak hours. Need to identify slow operations and optimize performance.",
        "query": "Redis slowlog latency performance analysis commands",
        "expected_needs": [
            "SLOWLOG commands",
            "Performance diagnostic tools",
            "Optimization techniques",
            "Monitoring recommendations",
        ],
    },
    {
        "scenario": "Memory Management Crisis",
        "context": "Redis memory usage approaching maxmemory limit. Risk of data eviction affecting application functionality. Need memory optimization guidance.",
        "query": "Redis memory optimization eviction policy configuration",
        "expected_needs": [
            "Memory diagnostic commands",
            "Eviction policy configuration",
            "Memory optimization techniques",
            "Capacity planning",
        ],
    },
    {
        "scenario": "Security Incident Response",
        "context": "Detected unauthorized Redis access attempts. Need to secure Redis instance and implement authentication quickly.",
        "query": "Redis security authentication access control setup",
        "expected_needs": [
            "Authentication configuration",
            "Access control setup",
            "Security hardening",
            "Audit procedures",
        ],
    },
    {
        "scenario": "Connection Pool Debugging",
        "context": "Application experiencing connection pool exhaustion with Redis. Connections growing but not being released properly.",
        "query": "Redis connection pool exhaustion leak detection monitoring",
        "expected_needs": [
            "Pool monitoring techniques",
            "Leak detection methods",
            "Connection lifecycle management",
            "Debugging procedures",
        ],
    },
]

# Extended scenarios covering diverse Redis operational challenges
EXTENDED_SCENARIOS = [
    {
        "scenario": "OOM Killer Termination",
        "context": "Redis process terminated by Linux OOM killer during peak traffic. Memory usage exceeded maxmemory causing system-wide memory pressure. Applications now failing with connection refused errors.",
        "query": "Redis maxmemory exceeded OOM killer prevention memory management",
        "expected_needs": [
            "Memory monitoring",
            "OOM prevention",
            "Memory limits configuration",
            "Recovery procedures",
        ],
    },
    {
        "scenario": "AOF Corruption Startup Failure",
        "context": "Redis fails to start after server crash with 'Bad file format reading the append only file' error. AOF file appears corrupted and preventing Redis recovery.",
        "query": "Redis AOF file corruption startup failure repair recovery",
        "expected_needs": [
            "AOF repair commands",
            "Data recovery procedures",
            "Backup restoration",
            "Corruption prevention",
        ],
    },
    {
        "scenario": "RDB Snapshot I/O Blocking",
        "context": "Background RDB saves consuming 100% disk I/O for 30+ seconds causing application timeouts. BGSAVE operations blocking other Redis operations.",
        "query": "Redis RDB snapshot high disk IO performance impact tuning",
        "expected_needs": [
            "Snapshot optimization",
            "I/O configuration",
            "Background save tuning",
            "Performance monitoring",
        ],
    },
    {
        "scenario": "Memory Fragmentation Crisis",
        "context": "Memory fragmentation ratio reached 4.2 causing Redis to use 8GB RAM for 2GB of data. System experiencing swap activity and performance degradation.",
        "query": "Redis memory fragmentation high ratio optimization defragmentation",
        "expected_needs": [
            "Fragmentation analysis",
            "Defragmentation techniques",
            "Memory optimization",
            "Monitoring setup",
        ],
    },
    {
        "scenario": "Replication Lag Emergency",
        "context": "Master-replica lag exceeded 45 seconds during high write load. Read queries returning stale data causing application inconsistencies and user complaints.",
        "query": "Redis replication lag high latency master replica synchronization",
        "expected_needs": [
            "Replication monitoring",
            "Lag reduction techniques",
            "Sync optimization",
            "Read consistency management",
        ],
    },
    {
        "scenario": "Sentinel False Failover",
        "context": "Redis Sentinel triggered 3 unnecessary failovers in 1 hour due to false positive master down detection. Applications experiencing connection disruptions during failovers.",
        "query": "Redis Sentinel false positive master down failover prevention tuning",
        "expected_needs": [
            "Sentinel configuration",
            "Failover prevention",
            "Detection tuning",
            "Stability optimization",
        ],
    },
    {
        "scenario": "Replica Promotion Disk Full",
        "context": "Automatic failover failed when replica unable to promote to master due to insufficient disk space for replication backlog. System now without master node.",
        "query": "Redis replica promotion failure disk space replication backlog recovery",
        "expected_needs": [
            "Disk space management",
            "Promotion troubleshooting",
            "Backlog configuration",
            "Manual failover procedures",
        ],
    },
    {
        "scenario": "Cluster Split-Brain Conflict",
        "context": "Network partition caused Redis Cluster split-brain with two masters for same slots. Conflicting writes occurred and data consistency compromised.",
        "query": "Redis Cluster split brain network partition conflicting masters recovery",
        "expected_needs": [
            "Split-brain detection",
            "Cluster recovery",
            "Data consistency repair",
            "Partition prevention",
        ],
    },
    {
        "scenario": "Cluster Slot Migration Stuck",
        "context": "Redis Cluster slot migration stuck at 52% completion for 2 hours. Clients receiving MOVED redirections and some keys becoming inaccessible.",
        "query": "Redis Cluster slot migration stuck incomplete MOVED errors troubleshooting",
        "expected_needs": [
            "Migration monitoring",
            "Stuck migration recovery",
            "Slot rebalancing",
            "Client error handling",
        ],
    },
    {
        "scenario": "Hash Slot Hotspot Imbalance",
        "context": "Redis Cluster node receiving 80% more traffic due to poor hash slot distribution. Hot node experiencing high CPU and memory pressure while others idle.",
        "query": "Redis Cluster hash slot distribution imbalance hotspot rebalancing",
        "expected_needs": [
            "Load balancing",
            "Slot redistribution",
            "Traffic analysis",
            "Cluster optimization",
        ],
    },
    {
        "scenario": "Lua Script Timeout Blocking",
        "context": "Long-running Lua script exceeded 5-second timeout causing Redis to block all operations. Clients piling up with timeouts and Redis appears frozen.",
        "query": "Redis Lua script timeout blocking server frozen client timeouts",
        "expected_needs": [
            "Script timeout handling",
            "Blocking resolution",
            "Script optimization",
            "Timeout configuration",
        ],
    },
    {
        "scenario": "Streams Consumer Lag Crisis",
        "context": "Redis Streams consumer group fell behind by 2.5 million messages during traffic spike. Processing lag growing and application queues backing up.",
        "query": "Redis Streams consumer group lag millions messages backlog processing",
        "expected_needs": [
            "Stream lag monitoring",
            "Consumer scaling",
            "Message processing optimization",
            "Backlog management",
        ],
    },
    {
        "scenario": "PubSub Message Loss",
        "context": "PubSub subscribers missing critical messages during Redis restart despite maintaining persistent connections. Message delivery not guaranteed causing data loss.",
        "query": "Redis PubSub message loss restart subscriber connection persistence",
        "expected_needs": [
            "Message durability",
            "Connection management",
            "Delivery guarantees",
            "Restart procedures",
        ],
    },
    {
        "scenario": "Rate Limiting Deadlock",
        "context": "Distributed rate limiting implementation using Redis locks causing widespread deadlock. Multiple services unable to acquire locks and system throughput degraded.",
        "query": "Redis distributed rate limiting lock contention deadlock resolution",
        "expected_needs": [
            "Lock management",
            "Deadlock prevention",
            "Rate limiting optimization",
            "Contention analysis",
        ],
    },
]

# Combine all scenarios
EVALUATION_SCENARIOS = CORE_SCENARIOS + EXTENDED_SCENARIOS


async def evaluate_search_with_llm_judge(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate a single search scenario using LLM judge."""

    logger.info(f"🔍 Evaluating: {scenario['scenario']}")

    # Perform the search
    search_result = await search_knowledge_base(scenario["query"], limit=5)
    retrieved_docs = search_result.get("results", [])

    # Prepare context for the judge
    judge_prompt = f"""
## Scenario: {scenario["scenario"]}

**Context**: {scenario["context"]}

**Search Query**: "{scenario["query"]}"

**Expected SRE Needs**: {", ".join(scenario["expected_needs"])}

## Retrieved Documents:

"""

    for i, doc in enumerate(retrieved_docs, 1):
        title = doc.get("title", "Unknown")
        content_preview = doc.get("content", "")[:500] + (
            "..." if len(doc.get("content", "")) > 500 else ""
        )
        category = doc.get("category", "Unknown")
        source = doc.get("source", "Unknown")

        judge_prompt += f"""
### Document {i}: {title}
- **Category**: {category}
- **Source**: {source}
- **Content Preview**: {content_preview}

"""

    judge_prompt += """
## Evaluation Required:

Please evaluate these search results from the perspective of an expert Redis SRE responding to this scenario. Rate each aspect (1-5) and provide detailed reasoning:

1. **Technical Accuracy** (1-5): Are the documents technically correct?
2. **Practical Relevance** (1-5): How well do results address the operational need?
3. **Completeness** (1-5): Sufficient information to resolve the issue?
4. **Actionability** (1-5): Clear, executable steps provided?
5. **Production Readiness** (1-5): Useful during real incident response?

Format your response as JSON:
```json
{
    "overall_score": <average of 5 aspects>,
    "technical_accuracy": <1-5>,
    "practical_relevance": <1-5>,
    "completeness": <1-5>,
    "actionability": <1-5>,
    "production_readiness": <1-5>,
    "detailed_analysis": "<comprehensive analysis>",
    "strengths": ["<strength 1>", "<strength 2>"],
    "weaknesses": ["<weakness 1>", "<weakness 2>"],
    "improvements": ["<improvement 1>", "<improvement 2>"],
    "best_document": "<title of most relevant document>",
    "missing_elements": ["<missing element 1>", "<missing element 2>"]
}
```
"""

    # Call GPT-4o for evaluation
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": judge_prompt},
            ],
            max_tokens=2000,
        )

        # Extract and parse the JSON response
        judge_response = response.choices[0].message.content

        # Try to extract JSON from the response
        json_start = judge_response.find("```json")
        json_end = judge_response.find("```", json_start + 7)

        if json_start != -1 and json_end != -1:
            json_content = judge_response[json_start + 7 : json_end].strip()
            evaluation = json.loads(json_content)
        else:
            # Fallback: try to parse the entire response as JSON
            evaluation = json.loads(judge_response)

        # Add metadata
        evaluation["scenario"] = scenario["scenario"]
        evaluation["query"] = scenario["query"]
        evaluation["num_retrieved_docs"] = len(retrieved_docs)
        evaluation["retrieved_titles"] = [doc.get("title", "Unknown") for doc in retrieved_docs]

        return evaluation

    except Exception as e:
        logger.error(f"LLM judge evaluation failed: {e}")
        return {
            "scenario": scenario["scenario"],
            "query": scenario["query"],
            "error": str(e),
            "overall_score": 0,
        }


async def run_comprehensive_llm_judge_evaluation():
    """Run comprehensive LLM judge evaluation across all scenarios."""

    logger.info("🤖 Starting Comprehensive LLM Judge Evaluation")
    logger.info("=" * 70)

    evaluations = []

    # Evaluate each scenario
    for scenario in EVALUATION_SCENARIOS:
        try:
            evaluation = await evaluate_search_with_llm_judge(scenario)
            evaluations.append(evaluation)

            # Brief summary for each scenario
            if "error" not in evaluation:
                score = evaluation.get("overall_score", 0)
                logger.info(f"✅ {scenario['scenario']}: Overall Score {score:.1f}/5.0")
            else:
                logger.error(f"❌ {scenario['scenario']}: Evaluation failed")

        except Exception as e:
            logger.error(f"❌ Failed to evaluate {scenario['scenario']}: {e}")

    # Aggregate results
    logger.info("\n📊 LLM Judge Evaluation Results")
    logger.info("=" * 70)

    valid_evaluations = [e for e in evaluations if "error" not in e]

    if valid_evaluations:
        # Calculate overall statistics
        avg_overall = sum(e["overall_score"] for e in valid_evaluations) / len(valid_evaluations)
        avg_technical = sum(e["technical_accuracy"] for e in valid_evaluations) / len(
            valid_evaluations
        )
        avg_relevance = sum(e["practical_relevance"] for e in valid_evaluations) / len(
            valid_evaluations
        )
        avg_completeness = sum(e["completeness"] for e in valid_evaluations) / len(
            valid_evaluations
        )
        avg_actionability = sum(e["actionability"] for e in valid_evaluations) / len(
            valid_evaluations
        )
        avg_production = sum(e["production_readiness"] for e in valid_evaluations) / len(
            valid_evaluations
        )

        logger.info("Overall Performance Summary:")
        logger.info(f"  📈 Overall Score: {avg_overall:.2f}/5.0")
        logger.info(f"  🎯 Technical Accuracy: {avg_technical:.2f}/5.0")
        logger.info(f"  🔍 Practical Relevance: {avg_relevance:.2f}/5.0")
        logger.info(f"  ✅ Completeness: {avg_completeness:.2f}/5.0")
        logger.info(f"  🚀 Actionability: {avg_actionability:.2f}/5.0")
        logger.info(f"  🏭 Production Readiness: {avg_production:.2f}/5.0")

        # Performance distribution
        excellent = sum(1 for e in valid_evaluations if e["overall_score"] >= 4.0)
        good = sum(1 for e in valid_evaluations if 3.0 <= e["overall_score"] < 4.0)
        needs_improvement = sum(1 for e in valid_evaluations if e["overall_score"] < 3.0)

        logger.info("\nPerformance Distribution:")
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
        logger.info("\n🔍 Detailed Results by Scenario:")
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
            logger.info(f"  Best Document: {evaluation.get('best_document', 'N/A')}")

            if evaluation.get("strengths"):
                logger.info(f"  Strengths: {', '.join(evaluation['strengths'][:2])}")
            if evaluation.get("weaknesses"):
                logger.info(f"  Weaknesses: {', '.join(evaluation['weaknesses'][:2])}")

    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"eval_reports/llm_judge_evaluation_{timestamp}.json"

    # Ensure eval_reports directory exists
    os.makedirs("eval_reports", exist_ok=True)

    with open(results_file, "w") as f:
        json.dump(
            {
                "evaluation_timestamp": datetime.now().isoformat(),
                "scenarios_evaluated": len(EVALUATION_SCENARIOS),
                "successful_evaluations": len(valid_evaluations),
                "summary_metrics": {
                    "avg_overall_score": avg_overall if valid_evaluations else 0,
                    "avg_technical_accuracy": avg_technical if valid_evaluations else 0,
                    "avg_practical_relevance": avg_relevance if valid_evaluations else 0,
                    "avg_completeness": avg_completeness if valid_evaluations else 0,
                    "avg_actionability": avg_actionability if valid_evaluations else 0,
                    "avg_production_readiness": avg_production if valid_evaluations else 0,
                },
                "detailed_evaluations": evaluations,
            },
            f,
            indent=2,
        )

    logger.info(f"\n💾 Detailed results saved to: {results_file}")

    # Only emit summary classification when we have valid evaluations
    if valid_evaluations:
        if avg_overall >= 4.0:
            logger.info("\n🎉 EXCELLENT: Redis SRE search quality meets production standards!")
        elif avg_overall >= 3.0:
            logger.info("\n✅ GOOD: Strong search quality with room for targeted improvements")
        else:
            logger.info("\n⚠️  NEEDS WORK: Search quality requires significant improvements")
    else:
        logger.info("\n⚠️  No valid evaluations; infrastructure may be unavailable.")

    return evaluations


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
@redis_search_required
async def test_llm_judge_evaluation():
    """Test comprehensive LLM judge evaluation of Redis SRE search quality."""
    # Skip if OpenAI API key is not available
    if (
        not os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY") == "test-openai-key"
    ):
        pytest.skip("OPENAI_API_KEY not set or using test key - skipping OpenAI integration test")

    evaluations = await run_comprehensive_llm_judge_evaluation()

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
        assert "technical_accuracy" in evaluation
        assert "practical_relevance" in evaluation
        assert "completeness" in evaluation
        assert "actionability" in evaluation
        assert "production_readiness" in evaluation
        assert "scenario" in evaluation
        assert "query" in evaluation


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
@redis_search_required
async def test_single_scenario_evaluation():
    """Test evaluation of a single scenario for faster feedback."""
    # Skip if OpenAI API key is not available
    if (
        not os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY") == "test-openai-key"
    ):
        pytest.skip("OPENAI_API_KEY not set or using test key - skipping OpenAI integration test")

    # Test just the connection scenario that we know performs well
    scenario = CORE_SCENARIOS[0]  # E-commerce flash sale connection scenario

    evaluation = await evaluate_search_with_llm_judge(scenario)

    assert "error" not in evaluation, f"Evaluation failed: {evaluation.get('error')}"
    assert evaluation["overall_score"] > 0
    assert evaluation["overall_score"] <= 5.0
    assert evaluation["scenario"] == scenario["scenario"]


if __name__ == "__main__":
    asyncio.run(run_comprehensive_llm_judge_evaluation())

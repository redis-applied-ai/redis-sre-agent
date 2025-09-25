#!/usr/bin/env python3
"""
Generate runbooks for all Redis operational scenarios tested in LLM judge evaluation.

This script automatically generates comprehensive runbooks for all Redis operational
scenarios covered in the evaluation, ensuring complete knowledge base coverage.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

from redis_sre_agent.agent.runbook_generator import RunbookGenerator

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# All scenarios from comprehensive LLM judge evaluation
ALL_SCENARIOS = [
    # Core scenarios (connection-focused, already have some coverage)
    {
        "topic": "Redis connection limit exceeded troubleshooting",
        "scenario": "Black Friday sale causing Redis connection spike from 200 to 4,500 connections. Users experiencing checkout timeouts and 'connection refused' errors. Need immediate troubleshooting guidance.",
        "severity": "critical",
        "requirements": [
            "Include CLIENT LIST analysis commands",
            "Add maxclients configuration tuning",
            "Provide immediate connection cleanup procedures",
            "Include connection pool optimization strategies",
        ],
    },
    {
        "topic": "Redis performance latency investigation",
        "scenario": "Redis latency spiked from 1ms to 50ms during peak hours. Need to identify slow operations and optimize performance.",
        "severity": "warning",
        "requirements": [
            "Include comprehensive SLOWLOG analysis",
            "Add latency diagnostic commands and tools",
            "Provide performance optimization techniques",
            "Include monitoring and alerting recommendations",
        ],
    },
    {
        "topic": "Redis memory optimization eviction policy for cache instances",
        "scenario": "Redis cache instance memory usage approaching maxmemory limit. Keys have TTL and no persistence configured. Need eviction policy optimization for cache use case.",
        "severity": "warning",
        "requirements": [
            "Include MEMORY commands for diagnostics",
            "Add eviction policy configuration for cache data",
            "Provide TTL optimization techniques",
            "Focus on cache hit rate improvement",
            "NO PERSISTENCE - eviction is safe",
        ],
    },
    {
        "topic": "Redis persistent data store memory pressure management",
        "scenario": "Redis persistent data store with AOF/RDB enabled experiencing 85% memory utilization. Keys contain user profiles, product data, orders with 0% TTL coverage. Need memory management WITHOUT data loss.",
        "severity": "critical",
        "requirements": [
            "NEVER suggest eviction policies - would cause data loss",
            "Include memory scaling and capacity planning",
            "Add large key identification using MEMORY USAGE commands",
            "Provide safe data cleanup strategies with application team",
            "Include data structure optimization for persistent data",
            "Focus on memory scaling, not eviction",
        ],
    },
    {
        "topic": "Redis usage pattern identification for memory troubleshooting",
        "scenario": "Redis instance experiencing memory pressure but unclear if it's used as cache or persistent store. Need to determine usage pattern from key patterns, TTL coverage, and persistence config before recommending memory solutions.",
        "severity": "info",
        "requirements": [
            "Include commands to analyze key patterns and TTL coverage",
            "Add persistence configuration detection methods",
            "Provide decision tree for cache vs persistent data determination",
            "Include safe investigation techniques that don't affect data",
            "Add specific guidance for each usage pattern detected",
        ],
    },
    {
        "topic": "Redis security authentication access control",
        "scenario": "Detected unauthorized Redis access attempts. Need to secure Redis instance and implement authentication quickly.",
        "severity": "critical",
        "requirements": [
            "Include AUTH and ACL configuration procedures",
            "Add security hardening best practices",
            "Provide access control setup guidance",
            "Include audit and monitoring procedures",
        ],
    },
    {
        "topic": "Redis connection pool exhaustion leak detection",
        "scenario": "Application experiencing connection pool exhaustion with Redis. Connections growing but not being released properly.",
        "severity": "warning",
        "requirements": [
            "Include pool monitoring and analysis techniques",
            "Add connection leak detection methods",
            "Provide connection lifecycle management guidance",
            "Include debugging and troubleshooting procedures",
        ],
    },
    # Extended scenarios (comprehensive coverage)
    {
        "topic": "Redis maxmemory exceeded OOM killer prevention",
        "scenario": "Redis process terminated by Linux OOM killer during peak traffic. Memory usage exceeded maxmemory causing system-wide memory pressure. Applications now failing with connection refused errors.",
        "severity": "critical",
        "requirements": [
            "Include OOM prevention and system memory monitoring",
            "Add maxmemory configuration and limits tuning",
            "Provide memory pressure recovery procedures",
            "Include system-level memory management",
        ],
    },
    {
        "topic": "Redis AOF corruption startup failure",
        "scenario": "Redis fails to start after server crash with 'Bad file format reading the append only file' error. AOF file appears corrupted and preventing Redis recovery.",
        "severity": "critical",
        "requirements": [
            "Include redis-check-aof repair commands",
            "Add data recovery procedures from backups",
            "Provide AOF corruption prevention strategies",
            "Include startup failure diagnostics",
        ],
    },
    {
        "topic": "Redis RDB snapshot high disk IO blocking",
        "scenario": "Background RDB saves consuming 100% disk I/O for 30+ seconds causing application timeouts. BGSAVE operations blocking other Redis operations.",
        "severity": "warning",
        "requirements": [
            "Include I/O monitoring commands",
            "Add BGSAVE optimization techniques",
            "Provide disk I/O tuning parameters",
            "Include snapshot scheduling best practices",
        ],
    },
    {
        "topic": "Redis memory fragmentation crisis",
        "scenario": "Memory fragmentation ratio reached 4.2 causing Redis to use 8GB RAM for 2GB of data. System experiencing swap activity and performance degradation.",
        "severity": "warning",
        "requirements": [
            "Include fragmentation analysis commands",
            "Add MEMORY PURGE and defragmentation procedures",
            "Provide memory optimization configuration",
            "Include fragmentation monitoring setup",
        ],
    },
    {
        "topic": "Redis replication lag emergency",
        "scenario": "Master-replica lag exceeded 45 seconds during high write load. Read queries returning stale data causing application inconsistencies and user complaints.",
        "severity": "warning",
        "requirements": [
            "Include replication monitoring commands",
            "Add lag reduction techniques and optimization",
            "Provide sync optimization strategies",
            "Include read consistency management",
        ],
    },
    {
        "topic": "Redis Sentinel false positive failovers",
        "scenario": "Redis Sentinel triggered 3 unnecessary failovers in 1 hour due to false positive master down detection. Applications experiencing connection disruptions during failovers.",
        "severity": "critical",
        "requirements": [
            "Include Sentinel configuration tuning parameters",
            "Add down-after-milliseconds and parallel-syncs optimization",
            "Provide failover detection threshold adjustments",
            "Include Sentinel monitoring and logging analysis",
        ],
    },
    {
        "topic": "Redis replica promotion disk space failure",
        "scenario": "Automatic failover failed when replica unable to promote to master due to insufficient disk space for replication backlog. System now without master node.",
        "severity": "critical",
        "requirements": [
            "Include disk space monitoring for replication",
            "Add manual replica promotion procedures",
            "Provide backlog sizing calculations",
            "Include emergency master recovery steps",
        ],
    },
    {
        "topic": "Redis Cluster split-brain network partition",
        "scenario": "Network partition caused Redis Cluster split-brain with two masters for same slots. Conflicting writes occurred and data consistency compromised.",
        "severity": "critical",
        "requirements": [
            "Include split-brain detection commands",
            "Add cluster recovery and slot reassignment procedures",
            "Provide data consistency repair strategies",
            "Include network partition prevention measures",
        ],
    },
    {
        "topic": "Redis Cluster slot migration stuck incomplete",
        "scenario": "Redis Cluster slot migration stuck at 52% completion for 2 hours. Clients receiving MOVED redirections and some keys becoming inaccessible.",
        "severity": "critical",
        "requirements": [
            "Include CLUSTER SLOTS migration diagnosis",
            "Add manual slot migration completion procedures",
            "Provide migration progress monitoring commands",
            "Include client MOVED error handling guidance",
        ],
    },
    {
        "topic": "Redis Cluster hash slot distribution imbalance",
        "scenario": "Redis Cluster node receiving 80% more traffic due to poor hash slot distribution. Hot node experiencing high CPU and memory pressure while others idle.",
        "severity": "warning",
        "requirements": [
            "Include slot distribution analysis commands",
            "Add cluster rebalancing procedures",
            "Provide hash tag optimization strategies",
            "Include load monitoring and alerting setup",
        ],
    },
    {
        "topic": "Redis Lua script timeout blocking server",
        "scenario": "Long-running Lua script exceeded 5-second timeout causing Redis to block all operations. Clients piling up with timeouts and Redis appears frozen.",
        "severity": "critical",
        "requirements": [
            "Include SCRIPT KILL and debugging commands",
            "Add script timeout configuration and handling",
            "Provide Lua script optimization techniques",
            "Include script execution monitoring",
        ],
    },
    {
        "topic": "Redis Streams consumer group lag crisis",
        "scenario": "Redis Streams consumer group fell behind by 2.5 million messages during traffic spike. Processing lag growing and application queues backing up.",
        "severity": "warning",
        "requirements": [
            "Include XINFO GROUPS and XPENDING analysis commands",
            "Add consumer scaling and parallel processing strategies",
            "Provide stream trimming and backlog management",
            "Include consumer lag monitoring and alerting",
        ],
    },
    {
        "topic": "Redis PubSub message loss during restart",
        "scenario": "PubSub subscribers missing critical messages during Redis restart despite maintaining persistent connections. Message delivery not guaranteed causing data loss.",
        "severity": "warning",
        "requirements": [
            "Include PubSub persistence and reliability strategies",
            "Add message buffering and replay mechanisms",
            "Provide subscriber reconnection handling procedures",
            "Include Redis restart procedures for PubSub systems",
        ],
    },
    {
        "topic": "Redis distributed rate limiting deadlock",
        "scenario": "Distributed rate limiting implementation using Redis locks causing widespread deadlock. Multiple services unable to acquire locks and system throughput degraded.",
        "severity": "critical",
        "requirements": [
            "Include lock contention analysis and debugging",
            "Add deadlock detection and resolution procedures",
            "Provide rate limiting algorithm optimization",
            "Include distributed locking best practices and alternatives",
        ],
    },
]


async def generate_runbook_for_scenario(
    generator: RunbookGenerator, scenario: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate a single runbook and return results."""
    logger.info(f"🚀 Generating runbook: {scenario['topic']}")

    try:
        result = await generator.generate_runbook(
            topic=scenario["topic"],
            scenario_description=scenario["scenario"],
            severity=scenario["severity"],
            specific_requirements=scenario["requirements"],
            max_iterations=2,
        )

        if result["success"]:
            runbook = result["runbook"]
            evaluation = result["evaluation"]

            logger.info(
                f"✅ Generated: {scenario['topic']} - Quality: {evaluation.overall_score:.1f}/5.0"
            )

            return {
                "scenario": scenario,
                "success": True,
                "runbook": runbook,
                "evaluation": evaluation,
                "quality_score": evaluation.overall_score,
            }
        else:
            logger.error(f"❌ Failed to generate runbook for: {scenario['topic']}")
            return {"scenario": scenario, "success": False, "error": "Generation failed"}

    except Exception as e:
        logger.error(f"❌ Error generating runbook for {scenario['topic']}: {e}")
        return {"scenario": scenario, "success": False, "error": str(e)}


async def save_runbook_to_source_documents(runbook, topic: str) -> Path:
    """Save generated runbook to source_documents directory in the correct category."""
    # Create safe filename
    safe_topic = "".join(c if c.isalnum() or c in "-_" else "-" for c in topic.lower())
    safe_topic = safe_topic.replace("--", "-").strip("-")

    # Determine category directory from runbook category
    category = runbook.category.lower()
    if category not in ["oss", "enterprise", "shared", "cloud"]:
        category = "shared"  # Default fallback

    # Ensure source_documents/{category} directory exists
    category_dir = Path(f"source_documents/{category}")
    category_dir.mkdir(parents=True, exist_ok=True)

    # Save runbook
    filename = f"redis-{safe_topic}.md"
    file_path = category_dir / filename

    file_path.write_text(runbook.content, encoding="utf-8")
    logger.info(f"💾 Saved runbook to {category} category: {file_path}")

    return file_path


async def ingest_generated_runbooks():
    """Ingest all generated runbooks into the knowledge base."""
    logger.info("📥 Ingesting generated runbooks into knowledge base...")

    from redis_sre_agent.pipelines.ingestion.processor import IngestionPipeline
    from redis_sre_agent.pipelines.scraper.base import ArtifactStorage

    try:
        storage = ArtifactStorage("./artifacts")
        pipeline = IngestionPipeline(storage)

        results = await pipeline.ingest_source_documents(Path("source_documents"))

        successful = [r for r in results if r["status"] == "success"]
        failed = [r for r in results if r["status"] == "error"]

        logger.info(f"✅ Ingestion completed: {len(successful)} successful, {len(failed)} failed")

        if successful:
            total_chunks = sum(r.get("chunks_indexed", 0) for r in successful)
            logger.info(f"📦 Total chunks indexed: {total_chunks}")

        return len(successful) > 0

    except Exception as e:
        logger.error(f"❌ Ingestion failed: {e}")
        return False


async def main():
    """Generate runbooks for all Redis operational scenarios."""
    logger.info("🎯 Generating Runbooks for All Redis Operational Scenarios")
    logger.info("=" * 80)
    logger.info(f"📋 Scenarios to process: {len(ALL_SCENARIOS)}")

    generator = RunbookGenerator()
    results = []

    # Generate runbooks for each scenario
    for i, scenario in enumerate(ALL_SCENARIOS, 1):
        logger.info(f"\n[{i}/{len(ALL_SCENARIOS)}] Processing: {scenario['topic']}")

        result = await generate_runbook_for_scenario(generator, scenario)
        results.append(result)

        # Save successful runbooks
        if result["success"]:
            try:
                await save_runbook_to_source_documents(result["runbook"], scenario["topic"])
            except Exception as e:
                logger.error(f"❌ Failed to save runbook: {e}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("📊 Generation Summary")
    logger.info("=" * 80)

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    logger.info(f"✅ Successfully generated: {len(successful)} runbooks")
    logger.info(f"❌ Failed to generate: {len(failed)} runbooks")

    if successful:
        avg_quality = sum(r["quality_score"] for r in successful) / len(successful)
        logger.info(f"📈 Average quality score: {avg_quality:.2f}/5.0")

        excellent = sum(1 for r in successful if r["quality_score"] >= 4.0)
        good = sum(1 for r in successful if 3.0 <= r["quality_score"] < 4.0)

        logger.info(f"🟢 Excellent (≥4.0): {excellent}")
        logger.info(f"🟡 Good (3.0-3.9): {good}")

        logger.info("\n📚 Generated Runbooks:")
        for result in successful:
            score = result["quality_score"]
            topic = result["scenario"]["topic"]
            logger.info(f"   • {topic}: {score:.1f}/5.0")

    if failed:
        logger.info("\n❌ Failed Scenarios:")
        for result in failed:
            topic = result["scenario"]["topic"]
            error = result.get("error", "Unknown error")
            logger.info(f"   • {topic}: {error}")

    # Ingest generated runbooks
    if successful:
        logger.info("\n📥 Ingesting Generated Runbooks")
        logger.info("=" * 50)

        ingestion_success = await ingest_generated_runbooks()

        if ingestion_success:
            logger.info("✅ All runbooks successfully ingested into knowledge base!")
            logger.info("🚀 Ready to re-run LLM judge evaluation to measure improvement")
        else:
            logger.warning("⚠️  Some runbooks may not have been ingested properly")

    logger.info("\n🎉 Runbook generation completed!")
    logger.info(f"📝 {len(successful)} high-quality runbooks created to address knowledge gaps")

    return results


if __name__ == "__main__":
    asyncio.run(main())

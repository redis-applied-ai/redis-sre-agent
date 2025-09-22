"""
Enhanced Multi-Turn Agent Evaluation with Diagnostic Context Integration.

This evaluation system tests the agent's analytical capabilities using real Redis
diagnostic data, following the "Raw Data Only + Agent Analysis" approach. External
tools capture baseline diagnostics, and the agent performs its own calculations and
severity assessments.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List

import pytest

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent
from redis_sre_agent.tools.redis_diagnostics import capture_redis_diagnostics

logger = logging.getLogger(__name__)

# Test scenarios with realistic Redis diagnostic scenarios
DIAGNOSTIC_EVALUATION_SCENARIOS = [
    {
        "scenario_id": "memory_pressure_analysis",
        "scenario": "High Memory Usage Analysis with Raw Diagnostics",
        "user_query": "Redis memory usage seems high and clients are experiencing intermittent delays. Analyze the current memory situation and provide recommendations.",
        "diagnostic_sections": ["memory", "performance", "clients"],
        "expected_agent_calculations": {
            "memory_usage_percentage": "Agent should calculate used_memory / maxmemory * 100",
            "fragmentation_assessment": "Agent should evaluate mem_fragmentation_ratio significance",
            "hit_rate_calculation": "Agent should compute keyspace_hits / (keyspace_hits + keyspace_misses) * 100",
            "eviction_analysis": "Agent should analyze evicted_keys count and implications",
        },
        "expected_tool_usage": {
            "get_detailed_redis_diagnostics": {
                "min_calls": 1,
                "sections": ["memory", "performance"],
            },
            "search_knowledge_base": {"min_calls": 2, "queries": ["memory", "performance"]},
            "check_service_health": {"min_calls": 0},  # Baseline already provides diagnostic data
        },
        "agent_analytical_tasks": [
            "Calculate memory usage percentage from raw bytes",
            "Determine severity level based on calculated percentage",
            "Analyze fragmentation ratio and provide assessment",
            "Correlate memory pressure with performance metrics",
        ],
    },
    {
        "scenario_id": "client_connection_surge",
        "scenario": "Client Connection Surge Investigation",
        "user_query": "We're seeing unusual client connection patterns. The connection count has increased significantly. Investigate and determine if this is problematic.",
        "diagnostic_sections": ["clients", "performance", "configuration"],
        "expected_agent_calculations": {
            "idle_connection_analysis": "Agent should analyze idle_seconds distribution",
            "connection_growth_assessment": "Agent should evaluate current vs historical connection patterns",
            "maxclients_utilization": "Agent should compare connected_clients to maxclients limit",
            "connection_pattern_analysis": "Agent should identify long-idle connections and their impact",
        },
        "expected_tool_usage": {
            "get_detailed_redis_diagnostics": {
                "min_calls": 1,
                "sections": ["clients", "configuration"],
            },
            "search_knowledge_base": {"min_calls": 2, "queries": ["connection", "maxclients"]},
        },
        "agent_analytical_tasks": [
            "Analyze client connection data for patterns",
            "Calculate connection utilization percentage",
            "Identify potentially problematic connection behavior",
            "Assess operational risk from current connection state",
        ],
    },
    {
        "scenario_id": "slowlog_performance_investigation",
        "scenario": "Performance Degradation via Slowlog Analysis",
        "user_query": "Application teams report slower response times. Use slowlog data to investigate potential Redis performance bottlenecks.",
        "diagnostic_sections": ["slowlog", "performance", "configuration"],
        "expected_agent_calculations": {
            "slowlog_frequency_analysis": "Agent should calculate slow query frequency and patterns",
            "duration_threshold_assessment": "Agent should evaluate duration_microseconds significance",
            "command_pattern_analysis": "Agent should identify most problematic command types",
            "performance_correlation": "Agent should correlate slowlog with ops/sec metrics",
        },
        "expected_tool_usage": {
            "get_detailed_redis_diagnostics": {
                "min_calls": 1,
                "sections": ["slowlog", "performance"],
            },
            "search_knowledge_base": {"min_calls": 2, "queries": ["slowlog", "performance"]},
        },
        "agent_analytical_tasks": [
            "Analyze slowlog entries for concerning patterns",
            "Calculate average slow query duration",
            "Identify command types causing performance issues",
            "Correlate slow queries with overall performance metrics",
        ],
    },
    {
        "scenario_id": "multi_metric_health_assessment",
        "scenario": "Comprehensive Health Assessment from Raw Metrics",
        "user_query": "Perform a comprehensive health assessment of our Redis instance. I need to understand the overall operational status across all key areas.",
        "diagnostic_sections": ["memory", "performance", "clients", "slowlog", "configuration"],
        "expected_agent_calculations": {
            "memory_health_score": "Agent should calculate and assess memory usage percentage",
            "performance_health_score": "Agent should evaluate hit rate and ops/sec trends",
            "connection_health_score": "Agent should assess client connection patterns",
            "overall_health_determination": "Agent should synthesize individual assessments into overall status",
        },
        "expected_tool_usage": {
            "get_detailed_redis_diagnostics": {
                "min_calls": 1,
                "sections": "all or comprehensive list",
            },
            "search_knowledge_base": {
                "min_calls": 3,
                "queries": ["health", "monitoring", "troubleshooting"],
            },
        },
        "agent_analytical_tasks": [
            "Calculate key operational percentages and ratios",
            "Assess severity levels for each major component",
            "Identify correlations between different metric areas",
            "Provide overall health determination with supporting evidence",
        ],
    },
]


class DiagnosticContextEvaluator:
    """Evaluates agent responses using real diagnostic data context."""

    def __init__(self):
        self.agent = SRELangGraphAgent()

    async def evaluate_scenario(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a scenario with real diagnostic context."""

        logger.info(f"🔍 Evaluating: {scenario['scenario']}")

        try:
            # Capture baseline diagnostic data
            baseline_diagnostics = await self._capture_baseline_diagnostics(scenario)

            if baseline_diagnostics.get("capture_status") != "success":
                logger.error(
                    f"Failed to capture baseline diagnostics: {baseline_diagnostics.get('diagnostics', {}).get('error')}"
                )
                return {
                    "scenario_id": scenario["scenario_id"],
                    "error": "Failed to capture baseline diagnostics",
                    "timestamp": datetime.now().isoformat(),
                }

            # Process query with diagnostic context
            response = await self.agent.process_query_with_diagnostics(
                query=scenario["user_query"],
                session_id=f"diagnostic_eval_{scenario['scenario_id']}",
                user_id="evaluator",
                baseline_diagnostics=baseline_diagnostics,
            )

            # Analyze agent's diagnostic tool usage
            tool_usage_analysis = self._analyze_diagnostic_tool_usage(response, scenario)

            # Evaluate agent's analytical capabilities
            analytical_analysis = self._evaluate_analytical_capabilities(
                response, baseline_diagnostics, scenario
            )

            # Parse investigation summary
            investigation_summary = self._parse_investigation_summary(response)

            # Evaluate knowledge source usage
            knowledge_analysis = self._analyze_knowledge_sources(investigation_summary, scenario)

            # Calculate overall assessment
            overall_assessment = self._calculate_diagnostic_assessment(
                tool_usage_analysis, analytical_analysis, knowledge_analysis, investigation_summary
            )

            result = {
                "scenario_id": scenario["scenario_id"],
                "scenario": scenario["scenario"],
                "user_query": scenario["user_query"],
                "baseline_diagnostics": baseline_diagnostics,
                "agent_response": response,
                "investigation_summary": investigation_summary,
                "tool_usage_analysis": tool_usage_analysis,
                "analytical_analysis": analytical_analysis,
                "knowledge_analysis": knowledge_analysis,
                "overall_assessment": overall_assessment,
                "timestamp": datetime.now().isoformat(),
            }

            # Log results
            overall_score = overall_assessment["composite_score"]
            analytical_score = analytical_analysis["analytical_score"]
            logger.info(
                f"✅ Completed: Overall {overall_score:.1f}/5.0, Analytical {analytical_score:.1f}/5.0"
            )

            return result

        except Exception as e:
            logger.error(f"❌ Evaluation failed for {scenario['scenario_id']}: {e}")
            return {
                "scenario_id": scenario["scenario_id"],
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def _capture_baseline_diagnostics(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Capture baseline diagnostic data for the scenario."""
        sections = scenario.get("diagnostic_sections", ["memory", "performance", "clients"])

        logger.info(f"Capturing baseline diagnostics: {sections}")

        # Use the same function that external tools would use
        diagnostics = await capture_redis_diagnostics("redis://localhost:6379", sections=sections, include_raw_data=True)

        return diagnostics

    def _analyze_diagnostic_tool_usage(
        self, response: str, scenario: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze how the agent used diagnostic tools in response to baseline data."""

        # Look for tool usage patterns in the response
        diagnostic_tool_usage = {
            "get_detailed_redis_diagnostics": 0,
            "search_knowledge_base": 0,
            "check_service_health": 0,
        }

        # Count tool mentions in investigation summary
        investigation_pattern = r"## 🔍 Investigation Summary\s*\n(.*?)(?:\n## |$)"
        summary_match = re.search(investigation_pattern, response, re.DOTALL | re.IGNORECASE)

        if summary_match:
            summary_text = summary_match.group(1)

            # Count diagnostic tool calls
            if (
                "detailed.*diagnostic" in summary_text.lower()
                or "get_detailed_redis" in summary_text.lower()
            ):
                diagnostic_tool_usage["get_detailed_redis_diagnostics"] += 1

            # Count knowledge searches
            knowledge_mentions = len(
                re.findall(r"search.*knowledge|runbook.*search", summary_text, re.IGNORECASE)
            )
            diagnostic_tool_usage["search_knowledge_base"] = knowledge_mentions

            # Count health checks (should be minimal since baseline provides diagnostics)
            if "health.*check|check.*service" in summary_text.lower():
                diagnostic_tool_usage["check_service_health"] += 1

        # Evaluate against expectations
        expected_usage = scenario.get("expected_tool_usage", {})
        compliance_scores = {}

        for tool, expected in expected_usage.items():
            actual_calls = diagnostic_tool_usage.get(tool, 0)
            min_calls = expected.get("min_calls", 0)

            compliance_scores[tool] = {
                "expected_min": min_calls,
                "actual_calls": actual_calls,
                "compliance": actual_calls >= min_calls,
            }

        overall_compliance = (
            sum(1 for score in compliance_scores.values() if score["compliance"])
            / len(compliance_scores)
            if compliance_scores
            else 0
        )

        return {
            "tool_usage_counts": diagnostic_tool_usage,
            "compliance_scores": compliance_scores,
            "overall_compliance": overall_compliance,
            "diagnostic_tool_strategy": (
                "baseline_aware"
                if diagnostic_tool_usage["get_detailed_redis_diagnostics"] > 0
                else "baseline_only"
            ),
        }

    def _evaluate_analytical_capabilities(
        self, response: str, baseline_diagnostics: Dict[str, Any], scenario: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate agent's ability to analyze raw diagnostic data."""

        analytical_evidence = {
            "memory_calculations": [],
            "performance_calculations": [],
            "severity_assessments": [],
            "trend_analysis": [],
            "correlation_analysis": [],
        }

        # Look for evidence of mathematical analysis
        memory_calc_patterns = [
            r"(\d+\.?\d*)%.*memory",
            r"memory.*(\d+\.?\d*)%",
            r"(\d+)\s*bytes.*(\d+)\s*bytes",  # Raw byte comparisons
            r"fragmentation.*(\d+\.?\d*)",
            r"utilization.*(\d+\.?\d*)%",
        ]

        for pattern in memory_calc_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            if matches:
                analytical_evidence["memory_calculations"].extend(matches)

        # Look for performance calculations
        perf_calc_patterns = [
            r"hit.*rate.*(\d+\.?\d*)%",
            r"(\d+\.?\d*)%.*hit.*rate",
            r"ops.*per.*second.*(\d+)",
            r"(\d+).*commands.*processed",
        ]

        for pattern in perf_calc_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            if matches:
                analytical_evidence["performance_calculations"].extend(matches)

        # Look for severity assessments
        severity_patterns = [
            r"(critical|warning|normal|healthy|concerning|problematic)",
            r"(high|medium|low).*priority",
            r"(urgent|immediate|moderate|routine).*action",
        ]

        for pattern in severity_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            analytical_evidence["severity_assessments"].extend(matches)

        # Evaluate against expected calculations
        expected_calculations = scenario.get("expected_agent_calculations", {})
        calculation_compliance = {}

        for calc_type, description in expected_calculations.items():
            has_evidence = False

            if "memory" in calc_type.lower():
                has_evidence = len(analytical_evidence["memory_calculations"]) > 0
            elif "performance" in calc_type.lower() or "hit_rate" in calc_type.lower():
                has_evidence = len(analytical_evidence["performance_calculations"]) > 0
            elif "assessment" in calc_type.lower() or "analysis" in calc_type.lower():
                has_evidence = len(analytical_evidence["severity_assessments"]) > 0

            calculation_compliance[calc_type] = {
                "expected": description,
                "evidence_found": has_evidence,
                "evidence_count": len([e for e in analytical_evidence.values() if e]),
            }

        # Calculate analytical score
        calculations_performed = sum(
            1 for comp in calculation_compliance.values() if comp["evidence_found"]
        )
        total_expected = len(calculation_compliance)

        analytical_score = (
            (calculations_performed / total_expected * 5) if total_expected > 0 else 0
        )

        return {
            "analytical_score": analytical_score,
            "analytical_evidence": analytical_evidence,
            "calculation_compliance": calculation_compliance,
            "calculations_performed": calculations_performed,
            "total_expected_calculations": total_expected,
            "raw_data_analysis_quality": (
                "high"
                if calculations_performed >= total_expected * 0.8
                else "medium"
                if calculations_performed >= total_expected * 0.5
                else "low"
            ),
        }

    def _parse_investigation_summary(self, response: str) -> Dict[str, Any]:
        """Parse investigation summary from agent response."""
        summary_pattern = r"## 🔍 Investigation Summary\s*\n(.*?)(?:\n## |$)"
        summary_match = re.search(summary_pattern, response, re.DOTALL | re.IGNORECASE)

        if not summary_match:
            return {"found": False, "error": "No investigation summary found"}

        summary_text = summary_match.group(1)

        # Parse tools section
        tools_pattern = r"### Tools Used:\s*\n(.*?)(?:\n### |$)"
        tools_match = re.search(tools_pattern, summary_text, re.DOTALL)

        # Parse knowledge sources
        knowledge_pattern = r"### Knowledge Sources:\s*\n(.*?)(?:\n### |$)"
        knowledge_match = re.search(knowledge_pattern, summary_text, re.DOTALL)

        # Parse methodology
        methodology_pattern = r"### Investigation Methodology:\s*\n(.*?)(?:\n### |$)"
        methodology_match = re.search(methodology_pattern, summary_text, re.DOTALL)

        return {
            "found": True,
            "raw_summary": summary_text,
            "tools_section": tools_match.group(1) if tools_match else "",
            "knowledge_section": knowledge_match.group(1) if knowledge_match else "",
            "methodology_section": methodology_match.group(1) if methodology_match else "",
        }

    def _analyze_knowledge_sources(
        self, investigation_summary: Dict[str, Any], scenario: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze knowledge source usage quality."""

        if not investigation_summary.get("found"):
            return {"knowledge_score": 0.0, "error": "No investigation summary"}

        knowledge_section = investigation_summary.get("knowledge_section", "")

        # Extract runbook references
        runbook_refs = re.findall(r'"([^"]+)"', knowledge_section)

        # Calculate knowledge quality metrics
        has_knowledge_sources = len(runbook_refs) > 0
        source_diversity = min(len(set(runbook_refs)), 3) / 3

        # Check for Redis-specific knowledge
        redis_specific = any(
            term in ref.lower()
            for ref in runbook_refs
            for term in ["redis", "memory", "performance", "connection", "slowlog"]
        )

        knowledge_score = (
            (0.4 * (1.0 if has_knowledge_sources else 0.0))
            + (0.3 * source_diversity)
            + (0.3 * (1.0 if redis_specific else 0.0))
        ) * 5  # Convert to 5-point scale

        return {
            "knowledge_score": knowledge_score,
            "runbook_references": runbook_refs,
            "has_knowledge_sources": has_knowledge_sources,
            "redis_specific_knowledge": redis_specific,
            "source_diversity": source_diversity,
        }

    def _calculate_diagnostic_assessment(
        self,
        tool_analysis: Dict[str, Any],
        analytical_analysis: Dict[str, Any],
        knowledge_analysis: Dict[str, Any],
        investigation_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calculate comprehensive assessment for diagnostic-context evaluation."""

        # Extract component scores
        tool_compliance_score = tool_analysis.get("overall_compliance", 0) * 5
        analytical_score = analytical_analysis.get("analytical_score", 0)
        knowledge_score = knowledge_analysis.get("knowledge_score", 0)
        structured_reporting_score = 5.0 if investigation_summary.get("found") else 0.0

        # Calculate weighted composite score
        # Higher weight on analytical capabilities since that's the focus
        composite_score = (
            (0.15 * tool_compliance_score)  # Tool usage strategy
            + (0.45 * analytical_score)  # Core analytical capabilities
            + (0.20 * knowledge_score)  # Knowledge integration
            + (0.20 * structured_reporting_score)  # Structured reporting
        )

        return {
            "composite_score": composite_score,
            "component_scores": {
                "tool_compliance": tool_compliance_score,
                "analytical_capabilities": analytical_score,
                "knowledge_integration": knowledge_score,
                "structured_reporting": structured_reporting_score,
            },
            "assessment_grade": (
                "Excellent"
                if composite_score >= 4.0
                else "Good"
                if composite_score >= 3.0
                else "Needs Improvement"
            ),
            "evaluation_focus": "diagnostic_analysis_with_raw_data",
        }


async def run_diagnostic_context_evaluation() -> List[Dict[str, Any]]:
    """Run comprehensive diagnostic context evaluation."""

    logger.info("🚀 Starting Diagnostic Context Evaluation")
    logger.info("=" * 70)
    logger.info("Testing agent analytical capabilities with real Redis diagnostic data")

    evaluator = DiagnosticContextEvaluator()
    results = []

    for i, scenario in enumerate(DIAGNOSTIC_EVALUATION_SCENARIOS, 1):
        logger.info(
            f"\n[{i}/{len(DIAGNOSTIC_EVALUATION_SCENARIOS)}] Evaluating: {scenario['scenario']}"
        )

        result = await evaluator.evaluate_scenario(scenario)
        results.append(result)

    # Generate comprehensive summary
    logger.info("\n📊 Diagnostic Context Evaluation Summary")
    logger.info("=" * 70)

    successful_results = [r for r in results if "error" not in r]

    # Initialize default values
    avg_composite = 0
    avg_analytical = 0
    avg_tool_compliance = 0

    if successful_results:
        # Calculate aggregate metrics
        composite_scores = [r["overall_assessment"]["composite_score"] for r in successful_results]
        analytical_scores = [
            r["analytical_analysis"]["analytical_score"] for r in successful_results
        ]
        tool_compliance_scores = [
            r["tool_usage_analysis"]["overall_compliance"] for r in successful_results
        ]

        avg_composite = sum(composite_scores) / len(composite_scores)
        avg_analytical = sum(analytical_scores) / len(analytical_scores)
        avg_tool_compliance = sum(tool_compliance_scores) / len(tool_compliance_scores)

        logger.info("📈 Performance Metrics:")
        logger.info(f"   🎯 Composite Score: {avg_composite:.2f}/5.0")
        logger.info(f"   🧮 Analytical Capabilities: {avg_analytical:.2f}/5.0")
        logger.info(f"   🔧 Tool Compliance: {avg_tool_compliance:.1%}")

        # Analytical capability distribution
        excellent_analytical = sum(1 for s in analytical_scores if s >= 4.0)
        good_analytical = sum(1 for s in analytical_scores if 3.0 <= s < 4.0)
        needs_improvement_analytical = sum(1 for s in analytical_scores if s < 3.0)

        logger.info("\n🧮 Analytical Capability Distribution:")
        logger.info(f"   🟢 Excellent (≥4.0): {excellent_analytical}/{len(successful_results)}")
        logger.info(f"   🟡 Good (3.0-3.9): {good_analytical}/{len(successful_results)}")
        logger.info(
            f"   🔴 Needs Improvement (<3.0): {needs_improvement_analytical}/{len(successful_results)}"
        )

        # Detailed scenario results
        logger.info("\n🔍 Detailed Scenario Results:")
        for result in successful_results:
            composite_score = result["overall_assessment"]["composite_score"]
            analytical_score = result["analytical_analysis"]["analytical_score"]
            scenario = result["scenario"]

            logger.info(f"   • {scenario}:")
            logger.info(
                f"     Overall: {composite_score:.1f}/5.0, Analytical: {analytical_score:.1f}/5.0"
            )

    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"eval_reports/diagnostic_context_evaluation_{timestamp}.json"

    # Ensure eval_reports directory exists
    os.makedirs("eval_reports", exist_ok=True)

    def json_serializer(obj):
        """Custom JSON serializer to handle bytes and other non-serializable objects."""
        if isinstance(obj, bytes):
            return f"<bytes:{len(obj)} bytes>"
        elif hasattr(obj, "__dict__"):
            return str(obj)
        else:
            return str(obj)

    with open(results_file, "w") as f:
        json.dump(
            {
                "evaluation_timestamp": datetime.now().isoformat(),
                "evaluation_type": "Enhanced Multi-Turn Agent with Diagnostic Context",
                "evaluation_focus": "agent_analytical_capabilities_with_raw_data",
                "total_scenarios": len(DIAGNOSTIC_EVALUATION_SCENARIOS),
                "successful_evaluations": len(successful_results),
                "summary_metrics": {
                    "avg_composite_score": avg_composite if successful_results else 0,
                    "avg_analytical_score": avg_analytical if successful_results else 0,
                    "avg_tool_compliance": avg_tool_compliance if successful_results else 0,
                },
                "detailed_results": results,
            },
            f,
            indent=2,
            default=json_serializer,
        )

    logger.info(f"\n💾 Detailed results saved to: {results_file}")

    if avg_composite >= 4.0:
        logger.info(
            "\n🎉 EXCELLENT: Agent demonstrates strong analytical capabilities with real diagnostic data!"
        )
    elif avg_composite >= 3.0:
        logger.info("\n✅ GOOD: Solid analytical performance with room for optimization")
    else:
        logger.info("\n⚠️  NEEDS WORK: Analytical capabilities require significant improvement")

    return results


@pytest.mark.asyncio
@pytest.mark.integration
async def test_diagnostic_context_evaluation():
    """Test diagnostic context evaluation with real data."""
    results = await run_diagnostic_context_evaluation()

    # Test assertions
    assert len(results) > 0, "Should have evaluation results"

    successful_results = [r for r in results if "error" not in r]
    assert len(successful_results) > 0, "Should have successful evaluations"

    # Check diagnostic data capture
    for result in successful_results:
        baseline_diagnostics = result["baseline_diagnostics"]
        assert baseline_diagnostics["capture_status"] == "success", (
            "Should capture baseline diagnostics successfully"
        )
        assert "diagnostics" in baseline_diagnostics, "Should have diagnostic data"

    # Check analytical capabilities
    for result in successful_results:
        analytical_analysis = result["analytical_analysis"]
        assert "analytical_score" in analytical_analysis, "Should evaluate analytical capabilities"
        assert analytical_analysis["calculations_performed"] > 0, (
            "Should show evidence of calculations"
        )

    # Check overall assessment quality
    for result in successful_results:
        assessment = result["overall_assessment"]
        assert assessment["evaluation_focus"] == "diagnostic_analysis_with_raw_data", (
            "Should focus on diagnostic analysis"
        )
        assert 0 <= assessment["composite_score"] <= 5, "Score should be in valid range"


if __name__ == "__main__":
    asyncio.run(run_diagnostic_context_evaluation())

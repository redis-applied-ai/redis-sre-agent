"""
Multi-Turn Agent Evaluation - Tests complete SRE workflow capabilities.

This evaluation system tests the agent's ability to:
1. Use multiple tools strategically (knowledge search, Redis diagnostics, metrics analysis)
2. Iterate and refine its approach based on tool results
3. Synthesize information from multiple sources
4. Make data-driven recommendations
5. Handle complex, multi-step troubleshooting scenarios
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

import openai
import pytest
from langchain_core.messages import AIMessage

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent
from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client for evaluation
openai.api_key = settings.openai_api_key


# Complex scenarios requiring multi-tool usage for success
MULTI_TURN_SCENARIOS = [
    {
        "scenario_id": "memory_spike_investigation",
        "scenario": "Production Memory Spike Investigation",
        "description": "Redis memory usage spiked from 2GB to 7GB in 30 minutes during Black Friday traffic. Application experiencing timeouts and some users unable to checkout. Need immediate investigation and resolution.",
        "user_query": "Our Redis instance just spiked from 2GB to 7GB memory usage in 30 minutes and users are experiencing checkout timeouts. What's happening and how do I fix this?",
        "required_tools": [
            "search_knowledge_base",  # Must search for memory troubleshooting guidance
            "check_service_health",  # Must check Redis diagnostics and current state
            "analyze_system_metrics",  # Must analyze memory usage patterns
        ],
        "success_criteria": {
            "must_search_memory_topics": True,
            "must_check_redis_health": True,
            "must_analyze_metrics": True,
            "must_provide_immediate_actions": True,
            "must_provide_monitoring_recommendations": True,
        },
        "evaluation_focus": [
            "Tool usage strategy and sequence",
            "Information synthesis from multiple sources",
            "Immediate vs long-term recommendation separation",
            "Data-driven analysis quality",
        ],
    },
    {
        "scenario_id": "connection_cascade_failure",
        "scenario": "Connection Cascade Failure",
        "description": "Monitoring alerts show Redis connection count climbing rapidly: 500 → 1200 → 2800 connections in 10 minutes. New connection attempts failing with 'max clients reached'. Multiple microservices affected.",
        "user_query": "URGENT: Redis connections went from 500 to 2800 in 10 minutes, new connections failing with max clients reached. Multiple services down. What tools should I use to diagnose this and what immediate actions should I take?",
        "required_tools": [
            "search_knowledge_base",  # Connection troubleshooting procedures
            "check_service_health",  # Connection diagnostics
            "analyze_system_metrics",  # Connection growth patterns
        ],
        "success_criteria": {
            "must_search_connection_topics": True,
            "must_check_current_connections": True,
            "must_analyze_connection_growth": True,
            "must_identify_connection_sources": True,
            "must_provide_immediate_remediation": True,
        },
        "evaluation_focus": [
            "Urgency recognition and triage approach",
            "Systematic diagnostic tool usage",
            "Root cause identification methodology",
            "Crisis response prioritization",
        ],
    },
    {
        "scenario_id": "performance_degradation_mystery",
        "scenario": "Performance Degradation Mystery",
        "description": "Application latency increased 300% over 2 hours. Redis appears healthy but response times are terrible. No obvious errors in logs. Traffic patterns look normal.",
        "user_query": "Our application latency went up 300% in the last 2 hours but Redis looks fine and traffic is normal. I need help figuring out what's wrong and how to investigate this systematically.",
        "required_tools": [
            "search_knowledge_base",  # Performance troubleshooting methodologies
            "check_service_health",  # Comprehensive Redis diagnostics
            "analyze_system_metrics",  # Latency and performance metrics
        ],
        "success_criteria": {
            "must_search_performance_topics": True,
            "must_check_redis_performance": True,
            "must_analyze_latency_metrics": True,
            "must_suggest_investigation_steps": True,
            "must_provide_monitoring_approach": True,
        },
        "evaluation_focus": [
            "Systematic investigation methodology",
            "Hidden performance issue identification",
            "Multi-layer diagnostic approach",
            "Evidence-based troubleshooting",
        ],
    },
    {
        "scenario_id": "cluster_slot_migration_stuck",
        "scenario": "Cluster Slot Migration Deadlock",
        "description": "Redis Cluster slot migration stuck at 47% for 3 hours. Clients getting MOVED errors for some keys. Traffic unevenly distributed across nodes. Migration progress not advancing.",
        "user_query": "Our Redis Cluster slot migration has been stuck at 47% for 3 hours and clients are getting MOVED errors. How do I diagnose what's blocking the migration and get it unstuck?",
        "required_tools": [
            "search_knowledge_base",  # Cluster troubleshooting procedures
            "check_service_health",  # Cluster state diagnostics
            "analyze_system_metrics",  # Cluster performance metrics
        ],
        "success_criteria": {
            "must_search_cluster_topics": True,
            "must_check_cluster_state": True,
            "must_analyze_migration_metrics": True,
            "must_provide_diagnostic_commands": True,
            "must_suggest_resolution_steps": True,
        },
        "evaluation_focus": [
            "Cluster-specific diagnostic expertise",
            "Migration troubleshooting methodology",
            "Multi-node analysis approach",
            "Complex distributed system understanding",
        ],
    },
    {
        "scenario_id": "security_breach_response",
        "scenario": "Security Breach Response",
        "description": "Security team detected unauthorized Redis access attempts from unknown IPs. Need to secure the instance immediately while investigating scope of potential breach.",
        "user_query": "Security detected unauthorized Redis access from unknown IPs. I need to secure this immediately and understand what they might have accessed. Walk me through the security response procedure.",
        "required_tools": [
            "search_knowledge_base",  # Security incident response procedures
            "check_service_health",  # Security diagnostics and access logs
            "analyze_system_metrics",  # Access pattern analysis
        ],
        "success_criteria": {
            "must_search_security_topics": True,
            "must_check_access_patterns": True,
            "must_analyze_security_metrics": True,
            "must_provide_immediate_security_actions": True,
            "must_suggest_forensic_steps": True,
        },
        "evaluation_focus": [
            "Security incident response protocol",
            "Immediate containment vs investigation balance",
            "Forensic evidence preservation",
            "Risk assessment and prioritization",
        ],
    },
]


EVALUATION_SYSTEM_PROMPT = """You are an expert Redis SRE evaluator. You will assess how well an AI agent handles complex Redis troubleshooting scenarios that require strategic tool usage.

Evaluate the agent's performance across these dimensions:

1. **Tool Usage Strategy** (1-5): Did the agent use the right tools in the right sequence?
2. **Information Synthesis** (1-5): How well did it combine information from multiple tools?
3. **Investigation Methodology** (1-5): Did it follow systematic troubleshooting approaches?
4. **Technical Accuracy** (1-5): Were the technical recommendations correct and safe?
5. **Urgency Recognition** (1-5): Did it properly triage and prioritize actions?
6. **Completeness** (1-5): Did it provide comprehensive guidance covering immediate and long-term actions?

For each scenario, also assess:
- Whether required tools were used appropriately
- Quality of the diagnostic process
- Practical utility for a real SRE during an incident

Rate each dimension 1-5 and provide detailed reasoning."""


class MultiTurnAgentEvaluator:
    """Evaluates multi-turn agent conversations requiring strategic tool usage."""

    def __init__(self):
        self.agent = SRELangGraphAgent()
        self.evaluation_results = []

    async def evaluate_scenario(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a single multi-turn scenario."""
        logger.info(f"🔍 Evaluating scenario: {scenario['scenario']}")

        # Create conversation thread
        thread_id = f"eval_{scenario['scenario_id']}"

        # Run agent conversation
        try:
            agent_response = await self.agent.process_query(
                query=scenario["user_query"],
                session_id=thread_id,
                user_id="evaluator",
                max_iterations=20,
            )

            # Extract conversation history with tool usage
            conversation_history = await self._extract_conversation_history(thread_id)

            # Analyze tool usage patterns
            tool_usage_analysis = self._analyze_tool_usage(conversation_history, scenario)

            # Get LLM evaluation of the agent's performance
            llm_evaluation = await self._evaluate_with_llm_judge(
                scenario, agent_response, tool_usage_analysis
            )

            result = {
                "scenario_id": scenario["scenario_id"],
                "scenario": scenario["scenario"],
                "user_query": scenario["user_query"],
                "agent_response": agent_response,
                "tool_usage_analysis": tool_usage_analysis,
                "llm_evaluation": llm_evaluation,
                "success_criteria_met": self._check_success_criteria(tool_usage_analysis, scenario),
                "timestamp": datetime.now().isoformat(),
            }

            return result

        except Exception as e:
            logger.error(f"Error evaluating scenario {scenario['scenario_id']}: {e}")
            return {
                "scenario_id": scenario["scenario_id"],
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def _extract_conversation_history(self, thread_id: str) -> List[Dict[str, Any]]:
        """Extract conversation history including tool calls from thread state."""
        try:
            # Get conversation state from agent
            state = await self.agent.get_thread_state(thread_id)

            conversation_history = []

            if state and "messages" in state:
                for message in state["messages"]:
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        # This is a tool-calling message
                        for tool_call in message.tool_calls:
                            conversation_history.append(
                                {
                                    "type": "tool_call",
                                    "tool_name": tool_call.get("name", "unknown"),
                                    "tool_args": tool_call.get("args", {}),
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                    elif hasattr(message, "content"):
                        conversation_history.append(
                            {
                                "type": "message",
                                "content": message.content,
                                "role": "ai" if isinstance(message, AIMessage) else "human",
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

            return conversation_history

        except Exception as e:
            logger.error(f"Error extracting conversation history: {e}")
            return []

    def _analyze_tool_usage(
        self, conversation_history: List[Dict[str, Any]], scenario: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze how tools were used during the conversation."""

        tool_calls = [item for item in conversation_history if item["type"] == "tool_call"]

        # Count tool usage
        tool_counts = {}
        for call in tool_calls:
            tool_name = call["tool_name"]
            tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

        # Check required tools were used
        required_tools = scenario.get("required_tools", [])
        tools_used = set(tool_counts.keys())
        required_tools_used = [tool for tool in required_tools if tool in tools_used]
        missing_tools = [tool for tool in required_tools if tool not in tools_used]

        # Analyze tool usage sequence
        tool_sequence = [call["tool_name"] for call in tool_calls]

        # Calculate metrics
        total_tools_used = len(tool_calls)
        unique_tools_used = len(tools_used)
        required_coverage = (
            len(required_tools_used) / len(required_tools) if required_tools else 1.0
        )

        return {
            "total_tool_calls": total_tools_used,
            "unique_tools_used": unique_tools_used,
            "tool_counts": tool_counts,
            "tool_sequence": tool_sequence,
            "required_tools": required_tools,
            "required_tools_used": required_tools_used,
            "missing_tools": missing_tools,
            "required_coverage": required_coverage,
            "conversation_length": len(conversation_history),
        }

    async def _evaluate_with_llm_judge(
        self,
        scenario: Dict[str, Any],
        agent_response: Dict[str, Any],
        tool_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Use LLM judge to evaluate agent performance."""

        evaluation_prompt = f"""
## Scenario: {scenario["scenario"]}

**Context**: {scenario["description"]}

**User Query**: "{scenario["user_query"]}"

**Required Tools**: {scenario.get("required_tools", [])}

## Agent Performance Analysis

**Tool Usage Summary**:
- Total tool calls: {tool_analysis["total_tool_calls"]}
- Tools used: {list(tool_analysis["tool_counts"].keys())}
- Tool sequence: {tool_analysis["tool_sequence"]}
- Required tools covered: {tool_analysis["required_coverage"]:.1%}
- Missing required tools: {tool_analysis["missing_tools"]}

**Agent Response**:
{agent_response.get("content", "No response content")}

## Evaluation Required

Assess this agent's performance on a scale of 1-5 for each dimension:

1. **Tool Usage Strategy**: Did it use the right tools in the right order?
2. **Information Synthesis**: How well did it combine tool results?
3. **Investigation Methodology**: Did it follow systematic approaches?
4. **Technical Accuracy**: Were recommendations correct and safe?
5. **Urgency Recognition**: Did it properly prioritize actions?
6. **Completeness**: Did it provide comprehensive guidance?

Also assess whether the agent successfully met these scenario-specific criteria:
{json.dumps(scenario.get("success_criteria", {}), indent=2)}

Format your response as JSON:
```json
{{
    "overall_score": <average of 6 dimensions>,
    "tool_usage_strategy": <1-5>,
    "information_synthesis": <1-5>,
    "investigation_methodology": <1-5>,
    "technical_accuracy": <1-5>,
    "urgency_recognition": <1-5>,
    "completeness": <1-5>,
    "detailed_analysis": "<comprehensive analysis>",
    "tool_usage_assessment": "<specific feedback on tool usage>",
    "strengths": ["<strength 1>", "<strength 2>"],
    "weaknesses": ["<weakness 1>", "<weakness 2>"],
    "success_criteria_assessment": {{
        "<criteria>": "<met/not met with explanation>"
    }},
    "improvement_recommendations": ["<recommendation 1>", "<recommendation 2>"]
}}
```
"""

        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": EVALUATION_SYSTEM_PROMPT},
                    {"role": "user", "content": evaluation_prompt},
                ],
                temperature=0.1,
                max_tokens=2000,
            )

            # Parse JSON response
            judge_response = response.choices[0].message.content

            # Extract JSON from response
            json_start = judge_response.find("```json")
            json_end = judge_response.find("```", json_start + 7)

            if json_start != -1 and json_end != -1:
                json_content = judge_response[json_start + 7 : json_end].strip()
                evaluation = json.loads(json_content)
            else:
                # Fallback: try to parse entire response as JSON
                evaluation = json.loads(judge_response)

            return evaluation

        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}")
            return {"error": str(e), "overall_score": 0}

    def _check_success_criteria(
        self, tool_analysis: Dict[str, Any], scenario: Dict[str, Any]
    ) -> Dict[str, bool]:
        """Check if success criteria were met based on tool usage."""

        criteria = scenario.get("success_criteria", {})
        results = {}

        # Check tool usage requirements
        tools_used = set(tool_analysis["tool_counts"].keys())

        if "must_search_memory_topics" in criteria:
            results["must_search_memory_topics"] = "search_knowledge_base" in tools_used

        if "must_search_connection_topics" in criteria:
            results["must_search_connection_topics"] = "search_knowledge_base" in tools_used

        if "must_search_performance_topics" in criteria:
            results["must_search_performance_topics"] = "search_knowledge_base" in tools_used

        if "must_search_cluster_topics" in criteria:
            results["must_search_cluster_topics"] = "search_knowledge_base" in tools_used

        if "must_search_security_topics" in criteria:
            results["must_search_security_topics"] = "search_knowledge_base" in tools_used

        if "must_check_redis_health" in criteria:
            results["must_check_redis_health"] = "check_service_health" in tools_used

        if "must_check_current_connections" in criteria:
            results["must_check_current_connections"] = "check_service_health" in tools_used

        if "must_check_redis_performance" in criteria:
            results["must_check_redis_performance"] = "check_service_health" in tools_used

        if "must_check_cluster_state" in criteria:
            results["must_check_cluster_state"] = "check_service_health" in tools_used

        if "must_check_access_patterns" in criteria:
            results["must_check_access_patterns"] = "check_service_health" in tools_used

        if "must_analyze_metrics" in criteria:
            results["must_analyze_metrics"] = "analyze_system_metrics" in tools_used

        if "must_analyze_connection_growth" in criteria:
            results["must_analyze_connection_growth"] = "analyze_system_metrics" in tools_used

        if "must_analyze_latency_metrics" in criteria:
            results["must_analyze_latency_metrics"] = "analyze_system_metrics" in tools_used

        if "must_analyze_migration_metrics" in criteria:
            results["must_analyze_migration_metrics"] = "analyze_system_metrics" in tools_used

        if "must_analyze_security_metrics" in criteria:
            results["must_analyze_security_metrics"] = "analyze_system_metrics" in tools_used

        return results


async def run_multi_turn_evaluation() -> List[Dict[str, Any]]:
    """Run comprehensive multi-turn agent evaluation."""

    logger.info("🚀 Starting Multi-Turn Agent Evaluation")
    logger.info("=" * 70)

    evaluator = MultiTurnAgentEvaluator()
    results = []

    for i, scenario in enumerate(MULTI_TURN_SCENARIOS, 1):
        logger.info(f"\n[{i}/{len(MULTI_TURN_SCENARIOS)}] Evaluating: {scenario['scenario']}")

        try:
            result = await evaluator.evaluate_scenario(scenario)
            results.append(result)

            # Brief progress summary
            if "error" not in result:
                llm_eval = result.get("llm_evaluation", {})
                score = llm_eval.get("overall_score", 0)
                tool_coverage = result["tool_usage_analysis"]["required_coverage"]

                logger.info(
                    f"✅ Completed: Overall Score {score:.1f}/5.0, Tool Coverage {tool_coverage:.1%}"
                )
            else:
                logger.error(f"❌ Failed: {result['error']}")

        except Exception as e:
            logger.error(f"❌ Evaluation failed for {scenario['scenario']}: {e}")
            results.append({"scenario_id": scenario["scenario_id"], "error": str(e)})

    # Generate summary statistics
    logger.info("\n📊 Multi-Turn Evaluation Summary")
    logger.info("=" * 70)

    successful_results = [r for r in results if "error" not in r and "llm_evaluation" in r]

    if successful_results:
        # Calculate averages
        scores = [r["llm_evaluation"]["overall_score"] for r in successful_results]
        tool_coverages = [r["tool_usage_analysis"]["required_coverage"] for r in successful_results]
        total_tool_calls = [
            r["tool_usage_analysis"]["total_tool_calls"] for r in successful_results
        ]

        avg_score = sum(scores) / len(scores)
        avg_tool_coverage = sum(tool_coverages) / len(tool_coverages)
        avg_tool_calls = sum(total_tool_calls) / len(total_tool_calls)

        logger.info("📈 Performance Metrics:")
        logger.info(f"   🎯 Average Overall Score: {avg_score:.2f}/5.0")
        logger.info(f"   🔧 Average Tool Coverage: {avg_tool_coverage:.1%}")
        logger.info(f"   📞 Average Tool Calls per Scenario: {avg_tool_calls:.1f}")

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

        # Top performing scenarios
        logger.info("\n🏆 Top Performing Scenarios:")
        sorted_results = sorted(
            successful_results, key=lambda x: x["llm_evaluation"]["overall_score"], reverse=True
        )
        for i, result in enumerate(sorted_results[:3], 1):
            score = result["llm_evaluation"]["overall_score"]
            scenario = result["scenario"]
            logger.info(f"   {i}. {scenario}: {score:.1f}/5.0")

    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"eval_reports/multi_turn_evaluation_{timestamp}.json"

    # Ensure eval_reports directory exists
    os.makedirs("eval_reports", exist_ok=True)

    with open(results_file, "w") as f:
        json.dump(
            {
                "evaluation_timestamp": datetime.now().isoformat(),
                "total_scenarios": len(MULTI_TURN_SCENARIOS),
                "successful_evaluations": len(successful_results),
                "failed_evaluations": len(results) - len(successful_results),
                "summary_metrics": {
                    "avg_overall_score": avg_score if successful_results else 0,
                    "avg_tool_coverage": avg_tool_coverage if successful_results else 0,
                    "avg_tool_calls": avg_tool_calls if successful_results else 0,
                },
                "detailed_results": results,
            },
            f,
            indent=2,
        )

    logger.info(f"\n💾 Detailed results saved to: {results_file}")

    if avg_score >= 4.0:
        logger.info("\n🎉 EXCELLENT: Multi-turn agent performance exceeds production standards!")
    elif avg_score >= 3.0:
        logger.info("\n✅ GOOD: Strong multi-turn capabilities with room for optimization")
    else:
        logger.info("\n⚠️  NEEDS WORK: Multi-turn workflows require significant improvements")

    return results


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_multi_turn_agent_evaluation():
    """Test comprehensive multi-turn agent evaluation."""
    # Skip if OpenAI API key is not available
    if (
        not os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY") == "test-openai-key"
    ):
        pytest.skip("OPENAI_API_KEY not set or using test key - skipping OpenAI integration test")

    results = await run_multi_turn_evaluation()

    # Test assertions
    assert len(results) > 0, "Should have evaluation results"

    successful_results = [r for r in results if "error" not in r]
    assert len(successful_results) > 0, "Should have successful evaluations"

    # Check that agent is using tools appropriately
    # At least some scenarios should use tools and required tools
    total_tool_calls = sum(r["tool_usage_analysis"]["total_tool_calls"] for r in successful_results)
    assert total_tool_calls > 0, "Agent should be using tools across scenarios"

    # At least some scenarios should use required tools (not necessarily all)
    scenarios_with_required_tools = sum(
        1 for r in successful_results if r["tool_usage_analysis"]["required_coverage"] > 0
    )
    assert scenarios_with_required_tools > 0, (
        "Agent should use required tools in at least some scenarios"
    )

    # Check evaluation quality
    for result in successful_results:
        if "llm_evaluation" in result:
            evaluation = result["llm_evaluation"]
            assert "overall_score" in evaluation, "Should have overall score"
            assert 0 <= evaluation["overall_score"] <= 5, "Score should be in valid range"


if __name__ == "__main__":
    asyncio.run(run_multi_turn_evaluation())

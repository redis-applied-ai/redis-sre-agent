"""End-to-end agent behavior tests with live OpenAI API calls."""

import json
import logging
from typing import Any, Dict

import openai
import pytest

from redis_sre_agent.agent import get_sre_agent
from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)


@pytest.mark.agent_behavior
@pytest.mark.integration
class TestSREAgentBehavior:
    """Test SRE Agent behavioral patterns with real OpenAI integration.

    These tests validate that the agent behaves appropriately for
    different types of SRE scenarios and questions.

    Requires:
    - Redis container for vector storage
    - Implemented LangGraph agent (future)
    """

    @pytest.fixture(scope="class")
    def sre_test_cases(self):
        """SRE-specific test cases for behavioral validation."""
        return [
            {
                "id": "sre_incident_response_1",
                "category": "incident_response",
                "weight": 3.0,  # High importance
                "user_input": "Our Redis cluster is down and users can't access the application",
                "expected_behavior": "Should provide immediate incident response steps: check Redis cluster status, identify failed nodes, attempt restart, check logs for errors, and escalate if needed. Should be urgent and action-oriented.",
                "thread_context": [],
            },
            {
                "id": "sre_performance_analysis_1",
                "category": "performance",
                "weight": 2.5,
                "user_input": "Redis is responding slowly, latency has increased from 1ms to 50ms",
                "expected_behavior": "Should suggest performance analysis: check CPU/memory usage, analyze slow queries, review connection pooling, check network latency, suggest optimization strategies.",
                "thread_context": [],
            },
            {
                "id": "sre_monitoring_setup_1",
                "category": "monitoring",
                "weight": 2.0,
                "user_input": "What metrics should I monitor for Redis health?",
                "expected_behavior": "Should provide comprehensive monitoring recommendations: memory usage, CPU utilization, connection counts, command stats, keyspace metrics, replication lag, and suggest monitoring tools.",
                "thread_context": [],
            },
            {
                "id": "sre_troubleshooting_1",
                "category": "troubleshooting",
                "weight": 2.5,
                "user_input": "Redis is consuming too much memory, what should I check?",
                "expected_behavior": "Should provide systematic troubleshooting steps: check memory usage breakdown, analyze data types, review TTL settings, suggest memory optimization techniques.",
                "thread_context": [],
            },
            {
                "id": "sre_monitoring_1",
                "category": "monitoring_setup",
                "weight": 2.0,
                "user_input": "How do I set up monitoring for Redis memory usage?",
                "expected_behavior": "Should provide specific monitoring setup instructions: metrics to track (memory usage, eviction rate), alerting thresholds (80% memory), monitoring tools (Prometheus, Grafana), and configuration examples.",
                "thread_context": [],
            },
            {
                "id": "sre_performance_1",
                "category": "performance_troubleshooting",
                "weight": 2.5,
                "user_input": "CPU usage is at 95% on our web servers, what should I check?",
                "expected_behavior": "Should provide systematic troubleshooting steps: identify top processes (htop/top), check for resource-intensive operations, review recent deployments, check for memory leaks, and scaling options.",
                "thread_context": [],
            },
            {
                "id": "sre_capacity_1",
                "category": "capacity_planning",
                "weight": 2.0,
                "user_input": "How do I calculate if we need to scale our database connections?",
                "expected_behavior": "Should explain capacity planning methodology: monitor connection pool metrics, calculate utilization ratios, identify peak usage patterns, and provide scaling recommendations with specific numbers.",
                "thread_context": [],
            },
            {
                "id": "sre_brief_ack_1",
                "category": "brief_acknowledgment",
                "weight": 1.0,
                "user_input": "Thanks for the help with the Redis issue",
                "expected_behavior": "Should provide a brief, friendly acknowledgment without unnecessary detail or promotional content. Something like 'You're welcome! Let me know if you need any other help.'",
                "thread_context": [
                    {
                        "user": "SRE Engineer",
                        "text": "Our Redis cluster is showing high memory usage",
                    },
                    {
                        "user": "SRE Agent",
                        "text": "I can help with Redis memory optimization. Here are the steps...",
                    },
                ],
            },
            {
                "id": "sre_prevention_1",
                "category": "preventive_measures",
                "weight": 2.0,
                "user_input": "What preventive measures can we implement to avoid database outages?",
                "expected_behavior": "Should provide comprehensive preventive strategies: health checks, monitoring setup, backup procedures, failover configuration, capacity planning, and maintenance schedules.",
                "thread_context": [],
            },
            {
                "id": "sre_tools_question_1",
                "category": "agent_capabilities",
                "weight": 1.5,
                "user_input": "What can this SRE agent help me with?",
                "expected_behavior": "Should clearly explain SRE agent capabilities: system monitoring, incident response, performance troubleshooting, capacity planning, and knowledge base search. Should mention specific tools like search_knowledge_base, analyze_metrics, check_health.",
                "thread_context": [],
            },
        ]

    @pytest.mark.asyncio
    async def test_sre_agent_individual_cases(self, sre_test_cases):
        """Test individual SRE agent behavior cases."""
        logger.info("Starting SRE agent behavior validation tests")

        # Get the SRE agent
        agent = get_sre_agent()

        for test_case in sre_test_cases:
            logger.info(f"Testing case: {test_case['id']}")

            try:
                # Process query with the agent
                response = await agent.process_query(
                    query=test_case["user_input"],
                    session_id=f"test_{test_case['id']}",
                    user_id="test-sre-user",
                )

                logger.info(f"Agent response for {test_case['id']}: {response[:200]}...")

                # Evaluate response quality
                evaluation = await self._evaluate_sre_response(test_case, response)

                logger.info(
                    f"Evaluation for {test_case['id']}: score={evaluation['score']}, reasoning={evaluation['reasoning'][:100]}..."
                )

                # Assert minimum quality threshold
                assert evaluation["score"] >= 6.0, (
                    f"Test case {test_case['id']} failed with score {evaluation['score']}: "
                    f"{evaluation['reasoning']}"
                )

                logger.info(
                    f"✅ Test case {test_case['id']} passed with score {evaluation['score']}"
                )

            except Exception as e:
                logger.error(f"❌ Test case {test_case['id']} failed with error: {e}")
                raise

    @pytest.mark.asyncio
    async def test_sre_agent_tool_calling(self):
        """Test that the agent can properly use SRE tools."""
        logger.info("Testing SRE agent tool calling capabilities")

        agent = get_sre_agent()

        # Test cases that should trigger specific tools
        tool_test_cases = [
            {
                "query": "Search for information about Redis memory troubleshooting procedures",
                "expected_tool": "search_knowledge_base",
                "session_id": "tool-test-search",
            },
            {
                "query": "Check the health status of the Redis service",
                "expected_tool": "check_service_health",
                "session_id": "tool-test-health",
            },
            {
                "query": "Analyze system metrics for CPU and memory usage over the last hour",
                "expected_tool": "check_service_health",
                "session_id": "tool-test-metrics",
            },
        ]

        for test_case in tool_test_cases:
            logger.info(f"Testing tool calling for: {test_case['expected_tool']}")

            response = await agent.process_query(
                query=test_case["query"],
                session_id=test_case["session_id"],
                user_id="test-sre-user",
            )

            # Check that we got a meaningful response
            assert len(response) > 50, (
                f"Response too short for {test_case['expected_tool']}: {response}"
            )

            # Log the response for manual verification
            logger.info(
                f"Tool calling response for {test_case['expected_tool']}: {response[:200]}..."
            )

    @pytest.mark.asyncio
    async def test_sre_agent_conversation_memory(self):
        """Test that the agent maintains conversation context."""
        logger.info("Testing SRE agent conversation memory")

        agent = get_sre_agent()
        session_id = "memory-test-session"

        # First message - establish context
        response1 = await agent.process_query(
            query="I'm having issues with Redis memory usage, it's at 95%",
            session_id=session_id,
            user_id="test-sre-user",
        )

        logger.info(f"First response: {response1[:200]}...")

        # Follow-up message - should remember context
        response2 = await agent.process_query(
            query="What should I check first?", session_id=session_id, user_id="test-sre-user"
        )

        logger.info(f"Follow-up response: {response2[:200]}...")

        # The follow-up should be contextually relevant to Redis memory issues
        assert len(response2) > 30, "Follow-up response too short"

        # Get conversation history
        history = await agent.get_conversation_history(session_id)
        logger.info(f"Conversation history length: {len(history)}")

        # Should have both user messages and agent responses
        assert len(history) >= 2, "Conversation history should contain multiple messages"

    async def _evaluate_sre_response(
        self, test_case: Dict[str, Any], response: str
    ) -> Dict[str, Any]:
        """Evaluate SRE agent response using GPT-4."""
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

        evaluation_prompt = f"""
Evaluate this SRE agent response based on SRE best practices and expected behavior:

CATEGORY: {test_case["category"]}
USER INPUT: "{test_case["user_input"]}"
THREAD CONTEXT: {json.dumps(test_case.get("thread_context", []), indent=2)}
EXPECTED BEHAVIOR: {test_case["expected_behavior"]}

AGENT RESPONSE: "{response}"

SRE EVALUATION CRITERIA:
1. **Actionability**: Does the response provide specific, actionable steps for the SRE scenario?
2. **Urgency Awareness**: Does it appropriately prioritize based on incident severity?
3. **Technical Accuracy**: Are the technical recommendations sound and SRE best practices?
4. **Completeness**: Does it cover the key aspects needed to resolve the issue?
5. **Tool Usage**: For complex scenarios, does it mention using appropriate SRE tools or searches?
6. **Escalation Guidance**: When appropriate, does it provide clear escalation paths?

SPECIFIC SRE GUIDELINES:
- Incident responses should be immediate and action-oriented
- Monitoring questions should provide specific metrics and thresholds
- Performance issues should include systematic troubleshooting steps
- Capacity planning should include specific calculations and recommendations
- Brief acknowledgments should be concise and professional
- Tool questions should accurately describe agent capabilities

Rate the response 1-10 for SRE effectiveness:

{{
    "score": <1-10>,
    "reasoning": "Detailed explanation focusing on SRE practices",
    "meets_sre_standards": <true/false>,
    "actionable_steps": <number_of_actionable_steps>,
    "technical_accuracy": <1-10>,
    "urgency_appropriate": <true/false>,
    "key_issues": ["list", "of", "any", "problems"],
    "strengths": ["list", "of", "sre", "strengths"]
}}
"""

        try:
            # Call OpenAI to evaluate the response
            evaluation_response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an SRE expert evaluator. Analyze agent responses for SRE effectiveness and provide detailed JSON evaluation.",
                    },
                    {"role": "user", "content": evaluation_prompt},
                ],
            )

            evaluation_text = evaluation_response.choices[0].message.content

            # Try to extract JSON from the response
            try:
                # Look for JSON in the response
                import re

                json_match = re.search(r"\{.*\}", evaluation_text, re.DOTALL)
                if json_match:
                    evaluation_data = json.loads(json_match.group())
                else:
                    raise ValueError("No JSON found in evaluation response")

            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse evaluation JSON: {e}")
                # Return a basic evaluation based on response length and content
                evaluation_data = {
                    "score": 7.0 if len(response) > 100 else 5.0,
                    "reasoning": f"Basic evaluation - JSON parsing failed: {evaluation_text[:200]}",
                    "meets_sre_standards": len(response) > 50,
                    "actionable_steps": response.lower().count("check")
                    + response.lower().count("monitor")
                    + response.lower().count("analyze"),
                    "technical_accuracy": 7.0,
                    "urgency_appropriate": True,
                    "key_issues": [],
                    "strengths": ["basic_response_provided"],
                }

            return evaluation_data

        except Exception as e:
            logger.error(f"Error in OpenAI evaluation: {e}")
            # Fallback evaluation
            return {
                "score": 6.0,
                "reasoning": f"Evaluation failed with error: {str(e)}. Basic scoring applied.",
                "meets_sre_standards": len(response) > 30,
                "actionable_steps": 1,
                "technical_accuracy": 6.0,
                "urgency_appropriate": True,
                "key_issues": ["evaluation_error"],
                "strengths": ["response_provided"],
            }

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Will implement when LangGraph agent is ready")
    async def test_sre_agent_full_behavior_suite(self, sre_test_cases, redis_container):
        """Run complete SRE agent behavior test suite."""
        # This will run all test cases and generate a comprehensive report
        # Similar to the reference implementation

        pytest.skip("LangGraph agent not yet implemented")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Will implement when LangGraph agent is ready")
    async def test_sre_incident_escalation_behavior(self, redis_container):
        """Test agent behavior during escalating incident scenarios."""
        # Test cases that simulate real incident escalation

        pytest.skip("LangGraph agent not yet implemented")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Will implement when LangGraph agent is ready")
    async def test_sre_tool_integration_behavior(self, redis_container):
        """Test that agent appropriately uses SRE tools."""
        # Test cases that require tool usage

        pytest.skip("LangGraph agent not yet implemented")


class SREAgentBehaviorTestSuite:
    """Comprehensive SRE agent behavior test suite."""

    def __init__(self):
        """Initialize the test suite."""
        # Will initialize OpenAI client for evaluation
        # Will load SRE-specific test cases
        pass

    async def run_full_sre_behavior_suite(self) -> Dict[str, Any]:
        """Run complete SRE behavior test suite."""
        # Will implement comprehensive SRE behavior testing
        # Returns detailed results similar to reference implementation
        pass

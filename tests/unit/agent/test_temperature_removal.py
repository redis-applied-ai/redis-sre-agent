"""
Test that temperature parameter is not used with reasoning models.

This module tests that the temperature parameter has been removed from all
LLM configurations since reasoning models don't support it.
"""

from unittest.mock import MagicMock, patch

from redis_sre_agent.agent.knowledge_agent import KnowledgeOnlyAgent
from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent
from redis_sre_agent.agent.runbook_generator import RunbookGenerator
from redis_sre_agent.evaluation.judge import SREAgentJudge


class TestTemperatureRemoval:
    """Test that temperature parameter is not used anywhere."""

    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    def test_knowledge_agent_no_temperature(self, mock_create_llm):
        """Test KnowledgeOnlyAgent doesn't use temperature parameter."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm

        KnowledgeOnlyAgent()

        # Verify create_llm was called without temperature
        mock_create_llm.assert_called_once()
        call_args = mock_create_llm.call_args

        # Check that temperature is not in the arguments
        assert "temperature" not in (call_args.kwargs or {})

    @patch("redis_sre_agent.agent.langgraph_agent.create_llm")
    @patch("redis_sre_agent.agent.langgraph_agent.create_mini_llm")
    def test_langgraph_agent_no_temperature(self, mock_create_mini_llm, mock_create_llm):
        """Test SRELangGraphAgent doesn't use temperature parameter."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        SRELangGraphAgent()

        # Verify create_llm and create_mini_llm were called
        mock_create_llm.assert_called_once()
        mock_create_mini_llm.assert_called_once()

        # Check all calls to ensure none use temperature
        for call_args in [mock_create_llm.call_args, mock_create_mini_llm.call_args]:
            assert "temperature" not in (call_args.kwargs or {})

    @patch("redis_sre_agent.evaluation.judge.create_mini_llm")
    def test_judge_no_temperature(self, mock_create_mini_llm):
        """Test SREAgentJudge doesn't use temperature parameter."""
        mock_llm = MagicMock()
        mock_create_mini_llm.return_value = mock_llm

        SREAgentJudge()

        # Verify create_mini_llm was called without temperature
        mock_create_mini_llm.assert_called_once()
        call_args = mock_create_mini_llm.call_args

        # Check that temperature is not in the arguments
        assert "temperature" not in (call_args.kwargs or {})

    @patch("redis_sre_agent.agent.runbook_generator.create_llm")
    def test_runbook_generator_no_temperature(self, mock_create_llm):
        """Test RunbookGenerator doesn't use temperature parameter."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm

        RunbookGenerator()

        # Verify create_llm was called without temperature
        mock_create_llm.assert_called_once()
        call_args = mock_create_llm.call_args

        # Check that temperature is not in the arguments
        assert "temperature" not in (call_args.kwargs or {})

    def test_reasoning_model_configuration(self):
        """Test that settings load model configuration correctly."""
        from redis_sre_agent.core.config import settings

        # Verify model settings are loaded (actual values depend on environment)
        assert settings.openai_model is not None
        assert settings.openai_model_mini is not None

        # The key behavior is that temperature is not passed to LLM calls
        # (tested in test_no_temperature_in_llm_calls above)


class TestRunbookDataclasses:
    """Test the runbook generator dataclasses."""

    def test_runbook_request_defaults(self):
        """Test RunbookRequest default values."""
        from redis_sre_agent.agent.runbook_generator import RunbookRequest

        request = RunbookRequest(
            topic="Memory Management",
            scenario_description="High memory usage in Redis cluster",
        )

        assert request.topic == "Memory Management"
        assert request.scenario_description == "High memory usage in Redis cluster"
        assert request.severity == "warning"
        assert request.category == "shared"
        assert request.specific_requirements is None

    def test_runbook_request_custom_values(self):
        """Test RunbookRequest with custom values."""
        from redis_sre_agent.agent.runbook_generator import RunbookRequest

        request = RunbookRequest(
            topic="Cluster Failover",
            scenario_description="Node failure in cluster",
            severity="critical",
            category="enterprise",
            specific_requirements=["HA setup", "Automatic failover"],
        )

        assert request.severity == "critical"
        assert request.category == "enterprise"
        assert request.specific_requirements == ["HA setup", "Automatic failover"]

    def test_research_result(self):
        """Test ResearchResult dataclass."""
        from redis_sre_agent.agent.runbook_generator import ResearchResult

        result = ResearchResult(
            tavily_findings=[{"title": "Redis Memory", "url": "https://redis.io"}],
            knowledge_base_results=[{"content": "Memory management tips"}],
            research_summary="Found relevant information about memory management",
        )

        assert len(result.tavily_findings) == 1
        assert len(result.knowledge_base_results) == 1
        assert "memory" in result.research_summary.lower()

    def test_generated_runbook(self):
        """Test GeneratedRunbook dataclass."""
        from redis_sre_agent.agent.runbook_generator import GeneratedRunbook

        runbook = GeneratedRunbook(
            title="Memory Management Runbook",
            content="# Steps\n1. Check memory usage\n2. Analyze keys",
            category="shared",
            severity="warning",
            sources=["https://redis.io/docs"],
            generation_timestamp="2024-01-15T10:00:00Z",
        )

        assert runbook.title == "Memory Management Runbook"
        assert "# Steps" in runbook.content
        assert len(runbook.sources) == 1

    def test_runbook_evaluation(self):
        """Test RunbookEvaluation dataclass."""
        from redis_sre_agent.agent.runbook_generator import RunbookEvaluation

        evaluation = RunbookEvaluation(
            overall_score=8.5,
            technical_accuracy=9,
            completeness=8,
            actionability=9,
            production_readiness=8,
            strengths=["Clear steps", "Good examples"],
            weaknesses=["Missing edge cases"],
            recommendations=["Add rollback procedures"],
            evaluation_summary="Good runbook with minor improvements needed",
        )

        assert evaluation.overall_score == 8.5
        assert evaluation.technical_accuracy == 9
        assert len(evaluation.strengths) == 2
        assert len(evaluation.weaknesses) == 1


class TestRunbookAgentState:
    """Test RunbookAgentState TypedDict."""

    def test_state_has_required_fields(self):
        """Test that RunbookAgentState has all required fields."""
        from redis_sre_agent.agent.runbook_generator import (
            RunbookAgentState,
            RunbookRequest,
        )

        request = RunbookRequest(topic="Test", scenario_description="Test scenario")

        state: RunbookAgentState = {
            "request": request,
            "research": None,
            "generated_runbook": None,
            "evaluation": None,
            "messages": [],
            "iteration_count": 0,
            "max_iterations": 5,
            "status": "researching",
        }

        assert state["request"] is request
        assert state["status"] == "researching"


class TestTavilySearchTool:
    """Test TavilySearchTool class."""

    def test_tavily_tool_initialization(self):
        """Test TavilySearchTool initialization."""
        from redis_sre_agent.agent.runbook_generator import TavilySearchTool

        tool = TavilySearchTool()
        assert tool.name == "tavily_search"

    @patch("redis_sre_agent.agent.runbook_generator.create_llm")
    def test_runbook_generator_initialization(self, mock_create_llm):
        """Test RunbookGenerator initialization."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm

        generator = RunbookGenerator()

        assert generator.llm is mock_llm
        assert hasattr(generator, "tavily")
        assert hasattr(generator, "graph")

    @patch("redis_sre_agent.agent.runbook_generator.create_llm")
    def test_runbook_generator_has_graph(self, mock_create_llm):
        """Test RunbookGenerator has StateGraph."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm

        generator = RunbookGenerator()

        assert generator.graph is not None

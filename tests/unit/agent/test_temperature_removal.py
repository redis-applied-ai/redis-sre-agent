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
        """Test that we're using reasoning models in configuration."""
        from redis_sre_agent.core.config import settings

        # Verify we're using reasoning models (gpt-5.x series)
        assert settings.openai_model == "gpt-5.2"
        assert settings.openai_model_mini == "gpt-5-mini"

        # These models don't support temperature, so we shouldn't use it anywhere

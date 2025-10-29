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

    @patch("redis_sre_agent.agent.knowledge_agent.ChatOpenAI")
    def test_knowledge_agent_no_temperature(self, mock_chat_openai):
        """Test KnowledgeOnlyAgent doesn't use temperature parameter."""
        mock_llm = MagicMock()
        mock_chat_openai.return_value = mock_llm

        KnowledgeOnlyAgent()

        # Verify ChatOpenAI was called without temperature
        mock_chat_openai.assert_called_once()
        call_args = mock_chat_openai.call_args

        # Check that temperature is not in the arguments
        assert "temperature" not in call_args.kwargs

        # Verify required arguments are present
        assert "model" in call_args.kwargs
        assert "openai_api_key" in call_args.kwargs

    @patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI")
    def test_langgraph_agent_no_temperature(self, mock_chat_openai):
        """Test SRELangGraphAgent doesn't use temperature parameter."""
        mock_llm = MagicMock()
        mock_chat_openai.return_value = mock_llm

        SRELangGraphAgent()

        # Verify ChatOpenAI was called without temperature
        mock_chat_openai.assert_called_once()
        call_args = mock_chat_openai.call_args

        # Check that temperature is not in the arguments
        assert "temperature" not in call_args.kwargs

        # Verify required arguments are present
        assert "model" in call_args.kwargs
        assert "openai_api_key" in call_args.kwargs

    @patch("redis_sre_agent.evaluation.judge.ChatOpenAI")
    def test_judge_no_temperature(self, mock_chat_openai):
        """Test SREAgentJudge doesn't use temperature parameter."""
        mock_llm = MagicMock()
        mock_chat_openai.return_value = mock_llm

        SREAgentJudge()

        # Verify ChatOpenAI was called without temperature
        mock_chat_openai.assert_called_once()
        call_args = mock_chat_openai.call_args

        # Check that temperature is not in the arguments
        assert "temperature" not in call_args.kwargs

        # Verify required arguments are present
        assert "model" in call_args.kwargs
        assert "openai_api_key" in call_args.kwargs

    @patch("redis_sre_agent.agent.runbook_generator.ChatOpenAI")
    def test_runbook_generator_no_temperature(self, mock_chat_openai):
        """Test RunbookGenerator doesn't use temperature parameter."""
        mock_llm = MagicMock()
        mock_chat_openai.return_value = mock_llm

        RunbookGenerator()

        # Verify ChatOpenAI was called without temperature
        mock_chat_openai.assert_called_once()
        call_args = mock_chat_openai.call_args

        # Check that temperature is not in the arguments
        assert "temperature" not in call_args.kwargs

        # Verify required arguments are present
        assert "model" in call_args.kwargs
        assert "api_key" in call_args.kwargs  # Note: uses api_key instead of openai_api_key

    def test_reasoning_model_configuration(self):
        """Test that we're using reasoning models in configuration."""
        from redis_sre_agent.core.config import settings

        # Verify we're using reasoning models (o4-mini)
        assert settings.openai_model == "gpt-5"
        assert settings.openai_model_mini == "gpt-5-mini"

        # These models don't support temperature, so we shouldn't use it anywhere

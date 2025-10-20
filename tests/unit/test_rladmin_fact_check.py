"""Unit tests for rladmin guidance and command fact-checking.

These tests verify:
- The fact-checker prompt includes an invalid_command category and mentions rladmin.
- The fact-checking input includes a Detected CLI Commands section when rladmin appears.
- The module source includes the new Redis Enterprise rladmin guidance.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.agent import langgraph_agent
from redis_sre_agent.agent.langgraph_agent import FACT_CHECKER_PROMPT, SRELangGraphAgent


class TestRladminFactCheck:
    def test_fact_checker_prompt_mentions_invalid_command_and_rladmin(self):
        """FACT_CHECKER_PROMPT should mention invalid_command and rladmin."""
        assert "invalid_command" in FACT_CHECKER_PROMPT
        assert "rladmin" in FACT_CHECKER_PROMPT

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI")
    async def test_fact_check_includes_detected_cli_commands_section(self, mock_chat_openai):
        """_fact_check_response should surface detected rladmin commands to the fact-checker."""
        # Mock LLM to return valid JSON inside a markdown code fence
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content="""```json\n{\n  \"has_errors\": false,\n  \"validation_notes\": \"ok\",\n  \"url_validation_performed\": true\n}\n```"""
            )
        )
        mock_chat_openai.return_value = mock_llm

        agent = SRELangGraphAgent()

        # Response containing an invented command
        response = "Run: rladmin list databases and then rladmin get database stats"
        result = await agent._fact_check_response(response)

        # Ensure result is parsed
        assert isinstance(result, dict)
        assert result.get("has_errors") is False

        # Capture messages passed to the fact-checker
        assert mock_llm.ainvoke.call_count >= 1
        call_args = mock_llm.ainvoke.call_args
        messages = call_args.args[0] if call_args.args else call_args.kwargs.get("messages")
        assert isinstance(messages, list) and len(messages) >= 2

        # The user content (index 1) should include the detected CLI commands section and the commands
        user_msg = messages[1]["content"] if isinstance(messages[1], dict) else messages[1].content
        assert "Detected CLI Commands (to validate)" in user_msg
        assert "rladmin list databases" in user_msg
        assert "rladmin get database stats" in user_msg

    def test_module_source_contains_rladmin_guidance_snippet(self):
        """Basic presence test for the rladmin guidance in the Redis Enterprise context."""
        src = inspect.getsource(langgraph_agent)
        assert "CLI Command Guidance (rladmin)" in src
        assert "Never invent or guess rladmin subcommands" in src

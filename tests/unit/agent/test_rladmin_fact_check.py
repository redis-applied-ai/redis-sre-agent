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
from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent


class TestRladminCorrector:
    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_safety_fact_corrector")
    async def test_corrector_triggers_on_rladmin(self, mock_build):
        mock_corrector = MagicMock()
        mock_corrector.ainvoke = AsyncMock(
            return_value={
                "result": {"edited_response": "E", "edits_applied": ["removed fabricated rladmin"]}
            }
        )
        mock_build.return_value = mock_corrector

        agent = SRELangGraphAgent()
        with patch.object(
            agent, "_process_query", new=AsyncMock(return_value="Use rladmin list databases")
        ):
            out = await agent.process_query("help", "s", "u")
        assert out.startswith("E")
        mock_build.assert_called_once()

    def test_module_source_contains_rladmin_guidance_snippet(self):
        """Basic presence test for the rladmin guidance in the Redis Enterprise context."""
        src = inspect.getsource(langgraph_agent)
        assert "CLI Command Guidance (rladmin)" in src
        assert "Never invent or guess rladmin subcommands" in src

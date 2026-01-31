"""Additional unit tests for rladmin CLI detection in fact-checker.

Covers:
- Multiple rladmin commands across lines are detected and de-duplicated
- No rladmin commands -> section is omitted in fact-check input
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent
from redis_sre_agent.agent.models import AgentResponse


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.build_safety_fact_corrector")
async def test_corrector_called_once_for_multiple_rladmin(mock_build):
    mock_corrector = MagicMock()
    mock_corrector.ainvoke = AsyncMock(
        return_value={"result": {"edited_response": "E", "edits_applied": ["dedup rladmin"]}}
    )
    mock_build.return_value = mock_corrector

    agent = SRELangGraphAgent()
    multi = (
        "First try: rladmin list databases\n"
        "Then again: rladmin list databases\n"
        "Finally check: rladmin get database stats"
    )
    mock_response = AgentResponse(response=multi, search_results=[])
    with patch.object(agent, "_process_query", new=AsyncMock(return_value=mock_response)):
        out = await agent.process_query("help", "s", "u")
    assert out.response.startswith("E")
    mock_build.assert_called_once()


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.build_safety_fact_corrector")
async def test_corrector_not_called_without_triggers(mock_build):
    agent = SRELangGraphAgent()
    mock_response = AgentResponse(response="no cli here", search_results=[])
    with patch.object(agent, "_process_query", new=AsyncMock(return_value=mock_response)):
        out = await agent.process_query("help", "s", "u")
    assert out.response == "no cli here"
    mock_build.assert_not_called()

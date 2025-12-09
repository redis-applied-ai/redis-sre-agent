from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.build_safety_fact_corrector")
async def test_corrector_runs_on_risky_patterns(mock_build):
    # Corrector returns edited content
    mock_corrector = MagicMock()
    mock_corrector.ainvoke = AsyncMock(
        return_value={
            "result": {"edited_response": "EDITED", "edits_applied": ["removed unsafe step"]}
        }
    )
    mock_build.return_value = mock_corrector

    agent = SRELangGraphAgent()
    # Skip heavy workflow: patch process_query to return risky text
    with patch.object(
        agent, "_process_query", new=AsyncMock(return_value="Use CONFIG SET to change policy")
    ):
        out = await agent.process_query("redis config help", "s", "u")

    assert out.startswith("EDITED"), (
        f"Corrector should have edited the response, which was: '{out}''"
    )
    mock_build.assert_called_once()


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.build_safety_fact_corrector")
async def test_corrector_skips_out_of_scope(mock_build):
    agent = SRELangGraphAgent()
    with patch.object(agent, "_process_query", new=AsyncMock(return_value="hello world")):
        out = await agent.process_query("just chatting", "s", "u")
    # Out of Redis scope -> returns original, corrector not run
    assert out == "hello world"
    mock_build.assert_not_called()


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.build_safety_fact_corrector")
async def test_corrector_no_change_returns_original(mock_build):
    # Corrector returns same text -> agent returns original (no edits footers)
    mock_corrector = MagicMock()
    mock_corrector.ainvoke = AsyncMock(
        return_value={"result": {"edited_response": "ORIG", "edits_applied": []}}
    )
    mock_build.return_value = mock_corrector

    agent = SRELangGraphAgent()
    with patch.object(agent, "_process_query", new=AsyncMock(return_value="ORIG")):
        out = await agent.process_query("redis config", "s", "u")

    assert out == "ORIG"


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.build_safety_fact_corrector")
async def test_corrector_gates_by_url(mock_build):
    mock_corrector = MagicMock()
    mock_corrector.ainvoke = AsyncMock(
        return_value={"result": {"edited_response": "E", "edits_applied": ["validated url"]}}
    )
    mock_build.return_value = mock_corrector

    agent = SRELangGraphAgent()
    with patch.object(
        agent, "_process_query", new=AsyncMock(return_value="See https://redis.io/docs")
    ):
        out = await agent.process_query("redis", "s", "u")
    assert out.startswith("E")
    mock_build.assert_called_once()

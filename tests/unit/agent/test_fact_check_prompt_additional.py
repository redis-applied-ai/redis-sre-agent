from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent
from redis_sre_agent.agent.subgraphs.safety_fact_corrector import (
    CorrectorState,
    build_safety_fact_corrector,
)


class TestCorrectorState:
    """Test CorrectorState TypedDict."""

    def test_state_has_required_fields(self):
        """Test that CorrectorState has all expected fields."""
        state: CorrectorState = {
            "messages": [],
            "budget": 2,
            "response_text": "test response",
            "instance": {"name": "test"},
            "result": {},
        }
        assert "messages" in state
        assert "budget" in state
        assert "response_text" in state
        assert "instance" in state
        assert "result" in state


class TestBuildSafetyFactCorrector:
    """Test build_safety_fact_corrector function."""

    def test_builds_compiled_graph(self):
        """Test that build_safety_fact_corrector returns a compiled graph."""
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.with_structured_output = MagicMock(return_value=mock_llm)

        graph = build_safety_fact_corrector(mock_llm, [])

        assert graph is not None
        # Should be a compiled graph
        assert hasattr(graph, "ainvoke")

    def test_builds_with_tool_adapters(self):
        """Test building with tool adapters."""
        from langchain_core.tools import StructuredTool

        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.with_structured_output = MagicMock(return_value=mock_llm)

        # Create a real StructuredTool instead of a mock
        def dummy_tool(query: str) -> str:
            """A dummy tool for testing."""
            return "result"

        tool = StructuredTool.from_function(
            func=dummy_tool, name="test_tool", description="A test tool"
        )

        graph = build_safety_fact_corrector(mock_llm, [tool])

        assert graph is not None

    def test_builds_with_custom_max_steps(self):
        """Test building with custom max_tool_steps."""
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.with_structured_output = MagicMock(return_value=mock_llm)

        graph = build_safety_fact_corrector(mock_llm, [], max_tool_steps=5)

        assert graph is not None

    def test_builds_with_memoize(self):
        """Test building with memoize function."""
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.with_structured_output = MagicMock(return_value=mock_llm)

        mock_memoize = AsyncMock()

        graph = build_safety_fact_corrector(mock_llm, [], memoize=mock_memoize)

        assert graph is not None


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

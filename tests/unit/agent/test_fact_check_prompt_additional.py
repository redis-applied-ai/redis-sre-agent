from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent
from redis_sre_agent.agent.models import AgentResponse
from redis_sre_agent.agent.subgraphs.safety_fact_corrector import (
    CorrectorState,
    build_safety_fact_corrector,
)
from redis_sre_agent.core.llm_request_guard import GuardedMemoizeLLMProxy


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
async def test_corrector_memoize_still_uses_guarded_ainvoke(monkeypatch):
    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    mock_structured = MagicMock()
    mock_llm.with_structured_output = MagicMock(return_value=mock_structured)

    async def naive_memoize(tag, memo_llm, messages):
        return await memo_llm.ainvoke(messages)

    graph = build_safety_fact_corrector(mock_llm, [], memoize=naive_memoize)

    from redis_sre_agent.core import llm_request_guard as guard_module

    guarded = AsyncMock(
        side_effect=[
            AIMessage(content="ok", tool_calls=[]),
            {
                "edited_response": "EDITED",
                "edits_applied": ["fixed"],
            },
        ]
    )
    monkeypatch.setattr(guard_module, "guarded_ainvoke", guarded)

    out = await graph.ainvoke(
        {
            "messages": [],
            "budget": 1,
            "response_text": "Original response",
            "instance": {},
        }
    )

    assert out["result"]["edited_response"] == "EDITED"
    assert guarded.await_count == 2


@pytest.mark.asyncio
async def test_corrector_rebuilds_structured_llm_per_invocation():
    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))

    structured_calls = 0

    class StructuredLLM:
        async def ainvoke(self, messages):
            return {
                "edited_response": "EDITED",
                "edits_applied": ["fixed"],
            }

    def make_structured(schema):
        nonlocal structured_calls
        structured_calls += 1
        return StructuredLLM()

    async def direct_memoize(tag, memo_llm, messages):
        return await memo_llm.ainvoke(messages)

    mock_llm.with_structured_output = MagicMock(side_effect=make_structured)

    graph = build_safety_fact_corrector(mock_llm, [], memoize=direct_memoize)

    state = {
        "messages": [],
        "budget": 1,
        "response_text": "Original response",
        "instance": {},
    }

    await graph.ainvoke(state)
    await graph.ainvoke(state)

    assert structured_calls == 2


@pytest.mark.asyncio
async def test_corrector_memoize_uses_bound_llm_when_tools_present(monkeypatch):
    mock_llm = MagicMock()
    bound_llm = MagicMock()
    bound_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
    mock_llm.bind_tools = MagicMock(return_value=bound_llm)
    mock_llm.with_structured_output = MagicMock(
        return_value=MagicMock(
            ainvoke=AsyncMock(
                return_value={
                    "edited_response": "EDITED",
                    "edits_applied": ["fixed"],
                }
            )
        )
    )

    async def direct_memoize(tag, memo_llm, messages):
        return await memo_llm.ainvoke(messages)

    def dummy_tool(query: str) -> str:
        return query

    tool = StructuredTool.from_function(
        func=dummy_tool,
        name="knowledge_lookup",
        description="Dummy knowledge tool",
    )

    graph = build_safety_fact_corrector(mock_llm, [tool], memoize=direct_memoize)

    from redis_sre_agent.core import llm_request_guard as guard_module

    calls = []

    async def fake_guarded_ainvoke(llm_obj, messages, request_kind, metadata=None):
        calls.append(llm_obj)
        return await llm_obj.ainvoke(messages)

    monkeypatch.setattr(guard_module, "guarded_ainvoke", fake_guarded_ainvoke)

    await graph.ainvoke(
        {
            "messages": [],
            "budget": 1,
            "response_text": "Original response",
            "instance": {},
        }
    )

    assert calls[0] is bound_llm


@pytest.mark.asyncio
async def test_corrector_does_not_rebind_already_bound_llm(monkeypatch):
    bound_llm = MagicMock()
    bound_llm.kwargs = {"tools": [{"type": "function", "function": {"name": "knowledge_lookup"}}]}
    bound_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))

    def fail_bind_tools(_adapters):
        raise AssertionError("already-bound llm should not be rebound")

    bound_llm.bind_tools = fail_bind_tools
    bound_llm.with_structured_output = MagicMock(
        return_value=MagicMock(
            ainvoke=AsyncMock(
                return_value={
                    "edited_response": "EDITED",
                    "edits_applied": ["fixed"],
                }
            )
        )
    )

    async def direct_memoize(tag, memo_llm, messages):
        return await memo_llm.ainvoke(messages)

    def dummy_tool(query: str) -> str:
        return query

    tool = StructuredTool.from_function(
        func=dummy_tool,
        name="knowledge_lookup",
        description="Dummy knowledge tool",
    )

    graph = build_safety_fact_corrector(bound_llm, [tool], memoize=direct_memoize)

    from redis_sre_agent.core import llm_request_guard as guard_module

    calls = []

    async def fake_guarded_ainvoke(llm_obj, messages, request_kind, metadata=None):
        calls.append(llm_obj)
        return await llm_obj.ainvoke(messages)

    monkeypatch.setattr(guard_module, "guarded_ainvoke", fake_guarded_ainvoke)

    await graph.ainvoke(
        {
            "messages": [],
            "budget": 1,
            "response_text": "Original response",
            "instance": {},
        }
    )

    assert calls[0] is bound_llm


@pytest.mark.asyncio
@pytest.mark.parametrize("cache_active", [False, True])
async def test_ainvoke_memo_avoids_double_guard_for_guarded_proxy(monkeypatch, cache_active):
    agent = SRELangGraphAgent()
    agent._run_cache_active = cache_active
    agent._llm_cache = {}

    class FakeLLM:
        model = "fake"
        temperature = 0.0

        async def ainvoke(self, messages):
            return AIMessage(content="ok")

    proxy = GuardedMemoizeLLMProxy(FakeLLM(), request_kind="unit.proxy")

    outer_guard_calls = []
    inner_guard_calls = []

    async def outer_guarded_ainvoke(llm, messages, request_kind, metadata=None):
        outer_guard_calls.append((request_kind, metadata or {}))
        return AIMessage(content="outer")

    async def inner_guarded_ainvoke(llm, messages, request_kind, metadata=None):
        inner_guard_calls.append((request_kind, metadata or {}))
        return AIMessage(content="inner")

    monkeypatch.setattr(
        "redis_sre_agent.agent.langgraph_agent.guarded_ainvoke", outer_guarded_ainvoke
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.llm_request_guard.guarded_ainvoke", inner_guarded_ainvoke
    )

    result = await agent._ainvoke_memo("tag", proxy, [])

    assert result.content == "inner"
    assert outer_guard_calls == []
    assert inner_guard_calls == [("unit.proxy", {})]


@pytest.mark.asyncio
async def test_ainvoke_memo_distinguishes_wrapped_models(monkeypatch):
    agent = SRELangGraphAgent()
    agent._run_cache_active = True
    agent._llm_cache = {}

    class FakeModel:
        temperature = 0.0

        def __init__(self, model_name: str, content: str):
            self.model_name = model_name
            self._content = content

        async def ainvoke(self, messages):
            return AIMessage(content=self._content)

    class BoundWrapper:
        def __init__(self, bound):
            self.bound = bound

        async def ainvoke(self, messages):
            return await self.bound.ainvoke(messages)

    inner_calls = []

    async def inner_guarded_ainvoke(llm, messages, request_kind, metadata=None):
        inner_calls.append((llm.bound.model_name, request_kind, metadata or {}))
        return await llm.ainvoke(messages)

    monkeypatch.setattr(
        "redis_sre_agent.core.llm_request_guard.guarded_ainvoke", inner_guarded_ainvoke
    )

    first_proxy = GuardedMemoizeLLMProxy(
        BoundWrapper(FakeModel("model-one", "first")),
        request_kind="unit.proxy",
    )
    second_proxy = GuardedMemoizeLLMProxy(
        BoundWrapper(FakeModel("model-two", "second")),
        request_kind="unit.proxy",
    )

    first_result = await agent._ainvoke_memo("tag", first_proxy, [])
    second_result = await agent._ainvoke_memo("tag", second_proxy, [])

    assert first_result.content == "first"
    assert second_result.content == "second"
    assert inner_calls == [
        ("model-one", "unit.proxy", {}),
        ("model-two", "unit.proxy", {}),
    ]
    assert len(agent._llm_cache) == 2


@pytest.mark.asyncio
async def test_ainvoke_memo_uses_cache_identity_source_for_fresh_proxies(monkeypatch):
    agent = SRELangGraphAgent()
    agent._run_cache_active = True
    agent._llm_cache = {}

    class BaseModel:
        model_name = "stable-model"
        temperature = 0.0

    class OpaqueStructuredWrapper:
        def __repr__(self):
            return f"<OpaqueStructuredWrapper at {id(self):x}>"

        async def ainvoke(self, messages):
            return AIMessage(content="cached")

    inner_calls = []

    async def inner_guarded_ainvoke(llm, messages, request_kind, metadata=None):
        inner_calls.append((request_kind, metadata or {}))
        return await llm.ainvoke(messages)

    monkeypatch.setattr(
        "redis_sre_agent.core.llm_request_guard.guarded_ainvoke", inner_guarded_ainvoke
    )

    first_proxy = GuardedMemoizeLLMProxy(
        OpaqueStructuredWrapper(),
        request_kind="unit.proxy",
        cache_identity_source=BaseModel(),
    )
    second_proxy = GuardedMemoizeLLMProxy(
        OpaqueStructuredWrapper(),
        request_kind="unit.proxy",
        cache_identity_source=BaseModel(),
    )

    first_result = await agent._ainvoke_memo("tag", first_proxy, [])
    second_result = await agent._ainvoke_memo("tag", second_proxy, [])

    assert first_result.content == "cached"
    assert second_result.content == "cached"
    assert inner_calls == [("unit.proxy", {})]
    assert len(agent._llm_cache) == 1


def test_guarded_memoize_proxy_missing_attribute_raises_clear_error():
    proxy = GuardedMemoizeLLMProxy(object(), request_kind="unit.proxy")

    with pytest.raises(AttributeError, match="wrapped LLM both missing attribute 'missing_attr'"):
        getattr(proxy, "missing_attr")


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
    # Skip heavy workflow: patch _process_query to return AgentResponse with risky text
    mock_response = AgentResponse(response="Use CONFIG SET to change policy", search_results=[])
    with patch.object(agent, "_process_query", new=AsyncMock(return_value=mock_response)):
        out = await agent.process_query("redis config help", "s", "u")

    assert out.response.startswith("EDITED"), (
        f"Corrector should have edited the response, which was: '{out.response}''"
    )
    mock_build.assert_called_once()


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.build_safety_fact_corrector")
async def test_corrector_skips_out_of_scope(mock_build):
    agent = SRELangGraphAgent()
    mock_response = AgentResponse(response="hello world", search_results=[])
    with patch.object(agent, "_process_query", new=AsyncMock(return_value=mock_response)):
        out = await agent.process_query("just chatting", "s", "u")
    # Out of Redis scope -> returns original, corrector not run
    assert out.response == "hello world"
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
    mock_response = AgentResponse(response="ORIG", search_results=[])
    with patch.object(agent, "_process_query", new=AsyncMock(return_value=mock_response)):
        out = await agent.process_query("redis config", "s", "u")

    assert out.response == "ORIG"


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.build_safety_fact_corrector")
async def test_corrector_gates_by_url(mock_build):
    mock_corrector = MagicMock()
    mock_corrector.ainvoke = AsyncMock(
        return_value={"result": {"edited_response": "E", "edits_applied": ["validated url"]}}
    )
    mock_build.return_value = mock_corrector

    agent = SRELangGraphAgent()
    mock_response = AgentResponse(response="See https://redis.io/docs", search_results=[])
    with patch.object(agent, "_process_query", new=AsyncMock(return_value=mock_response)):
        out = await agent.process_query("redis", "s", "u")
    assert out.response.startswith("E")
    mock_build.assert_called_once()

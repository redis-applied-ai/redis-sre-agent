"""Tests for the knowledge-only agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from redis_sre_agent.agent.knowledge_agent import KNOWLEDGE_SYSTEM_PROMPT, KnowledgeOnlyAgent
from redis_sre_agent.core.agent_memory import PreparedAgentTurnMemory, TurnMemoryContext
from redis_sre_agent.core.knowledge_helpers import (
    get_all_document_fragments,
    get_related_document_fragments,
)
from redis_sre_agent.core.knowledge_helpers import (
    ingest_sre_document_helper as ingest_sre_document,
)
from redis_sre_agent.core.knowledge_helpers import (
    search_knowledge_base_helper as search_knowledge_base,
)


class TestKnowledgeAgent:
    """Test the knowledge-only agent."""

    @pytest.mark.asyncio
    async def test_agent_initialization(self):
        """Test that KnowledgeOnlyAgent initializes correctly."""
        agent = KnowledgeOnlyAgent()

        # Verify agent has required attributes
        assert hasattr(agent, "llm")
        assert hasattr(agent, "settings")
        assert agent.llm is not None

    @pytest.mark.asyncio
    async def test_knowledge_tools_are_available(self):
        """Test that knowledge tools are available via ToolManager."""
        from redis_sre_agent.tools.manager import ToolManager

        # Create ToolManager without instance (loads only knowledge tools)
        async with ToolManager() as mgr:
            tools = mgr.get_tools()
            tool_names = [t.name for t in tools]

            # Verify knowledge tools are present
            knowledge_tools = [n for n in tool_names if "knowledge_" in n]
            assert len(knowledge_tools) == 8

            # Verify specific tools are present
            assert any("search" in n for n in knowledge_tools)
            assert any("ingest" in n for n in knowledge_tools)
            assert any("get_all_fragments" in n for n in knowledge_tools)
            assert any("get_related_fragments" in n for n in knowledge_tools)
            assert any("skills_check" in n for n in knowledge_tools)
            assert any("get_skill" in n for n in knowledge_tools)
            assert any("search_support_tickets" in n for n in knowledge_tools)
            assert any("get_support_ticket" in n for n in knowledge_tools)

    @pytest.mark.asyncio
    async def test_search_knowledge_base_wrapper(self):
        """Test that search_knowledge_base wrapper works correctly."""
        # This is a wrapper function, so we just verify it's callable
        # and has the right signature (no retry parameter)
        import inspect

        sig = inspect.signature(search_knowledge_base)
        params = list(sig.parameters.keys())

        # Should have query, category, limit, distance_threshold but NOT retry
        assert "query" in params
        assert "category" in params
        assert "limit" in params
        assert "distance_threshold" in params
        assert "retry" not in params

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.knowledge_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.knowledge_agent.ToolManager")
    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    async def test_process_query_seeds_startup_context_into_initial_state(
        self, mock_create_llm, mock_tool_manager_cls, mock_build_startup_context
    ):
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_manager_ctx = MagicMock()
        mock_tool_manager_ctx.__aenter__ = AsyncMock(return_value=mock_tool_mgr)
        mock_tool_manager_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_tool_manager_cls.return_value = mock_tool_manager_ctx

        captured: dict[str, object] = {}

        class _FakeApp:
            async def ainvoke(self, initial_state, config=None):
                captured["initial_state"] = initial_state
                return {
                    "messages": [AIMessage(content="ok", tool_calls=[])],
                    "knowledge_search_results": [],
                    "signals_envelopes": [],
                }

        class _FakeWorkflow:
            def compile(self, checkpointer=None):
                return _FakeApp()

        agent = KnowledgeOnlyAgent()
        with (
            patch(
                "redis_sre_agent.agent.helpers.build_adapters_for_tooldefs",
                AsyncMock(return_value=[]),
            ),
            patch.object(agent, "_build_workflow", return_value=_FakeWorkflow()),
        ):
            await agent.process_query(query="who runs AOP?", session_id="s1", user_id="u1")

        initial_state = captured["initial_state"]
        assert isinstance(initial_state["messages"][0], SystemMessage)
        assert "STARTUP_CONTEXT" in initial_state["messages"][0].content
        assert initial_state["startup_prompt_initialized"] is True
        assert "STARTUP_CONTEXT" in (initial_state["startup_system_prompt"] or "")
        mock_build_startup_context.assert_awaited_once_with(
            query="who runs AOP?",
            version="latest",
            available_tools=[],
        )

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.knowledge_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.knowledge_agent.ToolManager")
    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    async def test_process_query_skips_memory_persist_for_generic_fallback(
        self, mock_create_llm, mock_tool_manager_cls, mock_build_startup_context
    ):
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_manager_ctx = MagicMock()
        mock_tool_manager_ctx.__aenter__ = AsyncMock(return_value=mock_tool_mgr)
        mock_tool_manager_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_tool_manager_cls.return_value = mock_tool_manager_ctx

        prepared_memory = PreparedAgentTurnMemory(
            memory_service=MagicMock(),
            memory_context=TurnMemoryContext(
                system_prompt=None,
                user_working_memory=None,
                asset_working_memory=None,
            ),
            session_id="s1",
            user_id="u1",
            query="who runs AOP?",
            instance_id=None,
            cluster_id=None,
            emitter=None,
        )
        prepared_memory.persist_response_fail_open = AsyncMock()

        class _FakeApp:
            async def ainvoke(self, initial_state, config=None):
                return {
                    "messages": [],
                    "knowledge_search_results": [],
                    "signals_envelopes": [],
                }

        class _FakeWorkflow:
            def compile(self, checkpointer=None):
                return _FakeApp()

        agent = KnowledgeOnlyAgent()
        with (
            patch(
                "redis_sre_agent.agent.knowledge_agent.prepare_agent_turn_memory",
                AsyncMock(return_value=prepared_memory),
            ),
            patch(
                "redis_sre_agent.agent.helpers.build_adapters_for_tooldefs",
                AsyncMock(return_value=[]),
            ),
            patch.object(agent, "_build_workflow", return_value=_FakeWorkflow()),
        ):
            response = await agent.process_query(
                query="who runs AOP?", session_id="s1", user_id="u1"
            )

        assert response.response.startswith("I apologize, but I wasn't able to process your query.")
        prepared_memory.persist_response_fail_open.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.knowledge_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.knowledge_agent.ToolManager")
    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    async def test_process_query_recovers_from_blank_terminal_ai_message(
        self, mock_create_llm, mock_tool_manager_cls, mock_build_startup_context
    ):
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_manager_ctx = MagicMock()
        mock_tool_manager_ctx.__aenter__ = AsyncMock(return_value=mock_tool_mgr)
        mock_tool_manager_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_tool_manager_cls.return_value = mock_tool_manager_ctx

        prepared_memory = PreparedAgentTurnMemory(
            memory_service=MagicMock(),
            memory_context=TurnMemoryContext(
                system_prompt=None,
                user_working_memory=None,
                asset_working_memory=None,
            ),
            session_id="s1",
            user_id="u1",
            query="who runs AOP?",
            instance_id=None,
            cluster_id=None,
            emitter=None,
        )
        prepared_memory.persist_response_fail_open = AsyncMock()

        class _FakeApp:
            async def ainvoke(self, initial_state, config=None):
                return {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {"id": "tc-1", "name": "knowledge_search", "args": {"query": "x"}}
                            ],
                        )
                    ],
                    "knowledge_search_results": [],
                    "signals_envelopes": [],
                }

        class _FakeWorkflow:
            def compile(self, checkpointer=None):
                return _FakeApp()

        agent = KnowledgeOnlyAgent()
        with (
            patch(
                "redis_sre_agent.agent.knowledge_agent.prepare_agent_turn_memory",
                AsyncMock(return_value=prepared_memory),
            ),
            patch(
                "redis_sre_agent.agent.helpers.build_adapters_for_tooldefs",
                AsyncMock(return_value=[]),
            ),
            patch.object(agent, "_build_workflow", return_value=_FakeWorkflow()),
        ):
            response = await agent.process_query(
                query="who runs AOP?", session_id="s1", user_id="u1"
            )

        assert response.response.startswith("I gathered relevant evidence")
        prepared_memory.persist_response_fail_open.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ingest_sre_document_wrapper(self):
        """Test that ingest_sre_document wrapper works correctly."""
        import inspect

        sig = inspect.signature(ingest_sre_document)
        params = list(sig.parameters.keys())

        # Should have title, content, source, category, severity but NOT retry
        assert "title" in params
        assert "content" in params
        assert "source" in params
        assert "category" in params
        assert "severity" in params
        assert "retry" not in params

    @pytest.mark.asyncio
    async def test_get_all_document_fragments_signature(self):
        """Test that get_all_document_fragments has correct signature."""
        import inspect

        sig = inspect.signature(get_all_document_fragments)
        params = list(sig.parameters.keys())

        # Should have document_hash and include_metadata
        assert "document_hash" in params
        assert "include_metadata" in params

    @pytest.mark.asyncio
    async def test_get_related_document_fragments_signature(self):
        """Test that get_related_document_fragments has correct signature."""
        import inspect

        sig = inspect.signature(get_related_document_fragments)
        params = list(sig.parameters.keys())

        # Should have document_hash, current_chunk_index, context_window
        assert "document_hash" in params
        assert "current_chunk_index" in params
        assert "context_window" in params


class TestKnowledgeAgentState:
    """Test KnowledgeAgentState TypedDict."""

    def test_state_has_required_fields(self):
        """Test that KnowledgeAgentState has all required fields."""
        from redis_sre_agent.agent.knowledge_agent import KnowledgeAgentState

        state: KnowledgeAgentState = {
            "messages": [],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "tool_calls_executed": 0,
        }

        assert "messages" in state
        assert "session_id" in state
        assert "user_id" in state
        assert "current_tool_calls" in state
        assert "iteration_count" in state
        assert "max_iterations" in state
        assert "tool_calls_executed" in state


class TestKnowledgeSystemPrompt:
    """Test the knowledge agent system prompt."""

    def test_system_prompt_exists(self):
        """Test that the system prompt is defined."""
        from redis_sre_agent.agent.knowledge_agent import KNOWLEDGE_SYSTEM_PROMPT

        assert KNOWLEDGE_SYSTEM_PROMPT is not None
        assert len(KNOWLEDGE_SYSTEM_PROMPT) > 100

    def test_system_prompt_mentions_knowledge_base(self):
        """Test that the system prompt mentions knowledge base."""
        from redis_sre_agent.agent.knowledge_agent import KNOWLEDGE_SYSTEM_PROMPT

        assert "knowledge base" in KNOWLEDGE_SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_sre(self):
        """Test that the system prompt mentions SRE."""
        from redis_sre_agent.agent.knowledge_agent import KNOWLEDGE_SYSTEM_PROMPT

        assert "SRE" in KNOWLEDGE_SYSTEM_PROMPT

    def test_system_prompt_no_instance_access(self):
        """Test that the system prompt clarifies no instance access."""
        from redis_sre_agent.agent.knowledge_agent import KNOWLEDGE_SYSTEM_PROMPT

        assert (
            "NOT have access" in KNOWLEDGE_SYSTEM_PROMPT
            or "do not have access" in KNOWLEDGE_SYSTEM_PROMPT.lower()
        )


class TestKnowledgeAgentMethods:
    """Test KnowledgeOnlyAgent methods."""

    @pytest.mark.asyncio
    async def test_agent_has_llm(self):
        """Test that agent has LLM attribute."""
        agent = KnowledgeOnlyAgent()
        assert agent.llm is not None

    @pytest.mark.asyncio
    async def test_agent_has_settings(self):
        """Test that agent has settings attribute."""
        agent = KnowledgeOnlyAgent()
        assert agent.settings is not None

    @pytest.mark.asyncio
    async def test_agent_has_emitter(self):
        """Test that agent has emitter attribute."""
        agent = KnowledgeOnlyAgent()
        assert agent._emitter is not None

    @pytest.mark.asyncio
    async def test_agent_with_custom_emitter(self):
        """Test agent initialization with custom emitter."""
        from unittest.mock import MagicMock

        from redis_sre_agent.core.progress import ProgressEmitter

        mock_emitter = MagicMock(spec=ProgressEmitter)
        agent = KnowledgeOnlyAgent(progress_emitter=mock_emitter)
        assert agent._emitter is mock_emitter

    @pytest.mark.asyncio
    async def test_build_workflow_returns_state_graph(self):
        """Test that _build_workflow returns a StateGraph."""
        from unittest.mock import MagicMock

        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        agent = KnowledgeOnlyAgent()

        # Create mock tool manager
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []

        # Create mock LLM with tools
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        # Create emitter
        emitter = NullEmitter()

        workflow = agent._build_workflow(mock_tool_mgr, mock_llm, emitter)
        assert workflow is not None

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    async def test_first_iteration_forces_tool_choice_required(self, mock_create_llm):
        """Test that first iteration forces tool_choice='required' to ensure KB search."""
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        # Create mock LLM returned by create_llm
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm

        # Configure mock for workflow invocation
        mock_llm.bind = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="response", tool_calls=[]))

        # Create agent (gets mock_llm via patched create_llm)
        agent = KnowledgeOnlyAgent()

        # Build workflow
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        emitter = NullEmitter()
        workflow = agent._build_workflow(mock_tool_mgr, mock_llm, emitter)
        compiled = workflow.compile()

        # Test iteration_count=0: should call .bind(tool_choice="required")
        state_iter_0 = {
            "messages": [HumanMessage(content="test query")],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "tool_calls_executed": 0,
        }
        await compiled.nodes["agent"].ainvoke(state_iter_0)
        mock_llm.bind.assert_called_once_with(tool_choice="required")

        # Test iteration_count=1: should NOT call .bind()
        mock_llm.bind.reset_mock()
        state_iter_1 = {**state_iter_0, "iteration_count": 1}
        await compiled.nodes["agent"].ainvoke(state_iter_1)
        mock_llm.bind.assert_not_called()

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.knowledge_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    async def test_system_prompt_injected_with_conversation_history(
        self, mock_create_llm, mock_build_startup_context
    ):
        """Startup context should still be injected on follow-up turns."""
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        base_llm = MagicMock()
        bound_llm = MagicMock()
        bound_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        base_llm.bind = MagicMock(return_value=bound_llm)
        mock_create_llm.return_value = base_llm

        agent = KnowledgeOnlyAgent()
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, base_llm, NullEmitter())
        compiled = workflow.compile()

        state = {
            "messages": [
                HumanMessage(content="previous question"),
                AIMessage(content="previous answer"),
                HumanMessage(content="follow-up question"),
            ],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "tool_calls_executed": 0,
            "knowledge_search_results": [],
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state)

        sent_messages = bound_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)
        assert "STARTUP_CONTEXT" in sent_messages[0].content
        mock_build_startup_context.assert_awaited_once_with(
            query="follow-up question",
            version="latest",
            available_tools=[],
        )

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.knowledge_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    async def test_system_prompt_uses_base_prompt_when_startup_context_blank(
        self, mock_create_llm, mock_build_startup_context
    ):
        """Blank startup context should not prepend empty lines to the system prompt."""
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        mock_build_startup_context.return_value = "  "

        base_llm = MagicMock()
        bound_llm = MagicMock()
        bound_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        base_llm.bind = MagicMock(return_value=bound_llm)
        mock_create_llm.return_value = base_llm

        agent = KnowledgeOnlyAgent()
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, base_llm, NullEmitter())
        compiled = workflow.compile()

        state = {
            "messages": [HumanMessage(content="follow-up question")],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "tool_calls_executed": 0,
            "knowledge_search_results": [],
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state)

        sent_messages = bound_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)
        assert sent_messages[0].content == KNOWLEDGE_SYSTEM_PROMPT

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.knowledge_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    async def test_startup_context_built_once_across_agent_iterations(
        self, mock_create_llm, mock_build_startup_context
    ):
        """Startup context should be built once per workflow and then reused."""
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        base_llm = MagicMock()
        bound_llm = MagicMock()
        bound_llm.ainvoke = AsyncMock(return_value=AIMessage(content="turn-1", tool_calls=[]))
        base_llm.bind = MagicMock(return_value=bound_llm)
        base_llm.ainvoke = AsyncMock(return_value=AIMessage(content="turn-2", tool_calls=[]))
        mock_create_llm.return_value = base_llm

        agent = KnowledgeOnlyAgent()
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, base_llm, NullEmitter())
        compiled = workflow.compile()

        state = {
            "messages": [HumanMessage(content="follow-up question")],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "tool_calls_executed": 0,
            "knowledge_search_results": [],
            "signals_envelopes": [],
        }

        state_after_first = await compiled.nodes["agent"].ainvoke(state)
        state_after_first["messages"] = [
            m for m in state_after_first["messages"] if not isinstance(m, SystemMessage)
        ]
        state_after_first["iteration_count"] = 1
        await compiled.nodes["agent"].ainvoke(state_after_first)

        assert mock_build_startup_context.await_count == 1
        sent_messages_second = base_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages_second[0], SystemMessage)
        assert "STARTUP_CONTEXT" in sent_messages_second[0].content

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.knowledge_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    async def test_startup_context_not_shared_between_independent_invocations(
        self, mock_create_llm, mock_build_startup_context
    ):
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        mock_build_startup_context.side_effect = ["CTX_ONE", "CTX_TWO"]

        base_llm = MagicMock()
        bound_llm = MagicMock()
        bound_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        base_llm.bind = MagicMock(return_value=bound_llm)
        mock_create_llm.return_value = base_llm

        agent = KnowledgeOnlyAgent()
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, base_llm, NullEmitter())
        compiled = workflow.compile()

        state_one = {
            "messages": [HumanMessage(content="first question")],
            "session_id": "session-1",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
            "tool_calls_executed": 0,
            "knowledge_search_results": [],
            "signals_envelopes": [],
        }
        state_two = {
            "messages": [HumanMessage(content="second question")],
            "session_id": "session-2",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
            "tool_calls_executed": 0,
            "knowledge_search_results": [],
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state_one)
        await compiled.nodes["agent"].ainvoke(state_two)

        assert mock_build_startup_context.await_count == 2
        sent_messages_first = bound_llm.ainvoke.call_args_list[0].args[0]
        sent_messages_second = bound_llm.ainvoke.call_args_list[1].args[0]
        assert "CTX_ONE" in sent_messages_first[0].content
        assert "CTX_TWO" in sent_messages_second[0].content

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.knowledge_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    async def test_agent_node_rebuilds_prompt_on_first_step_when_cached_prompt_is_stale(
        self, mock_create_llm, mock_build_startup_context
    ):
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        mock_build_startup_context.return_value = "FRESH_CONTEXT"

        base_llm = MagicMock()
        bound_llm = MagicMock()
        bound_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        base_llm.bind = MagicMock(return_value=bound_llm)
        mock_create_llm.return_value = base_llm

        agent = KnowledgeOnlyAgent()
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, base_llm, NullEmitter())
        compiled = workflow.compile()

        state = {
            "messages": [HumanMessage(content="new question")],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": "STALE_CONTEXT",
            "tool_calls_executed": 0,
            "knowledge_search_results": [],
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state)

        sent_messages = bound_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)
        assert "FRESH_CONTEXT" in sent_messages[0].content
        assert "STALE_CONTEXT" not in sent_messages[0].content
        mock_build_startup_context.assert_awaited_once_with(
            query="new question",
            version="latest",
            available_tools=[],
        )

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.knowledge_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    async def test_agent_node_reuses_initialized_prompt_without_rebuild(
        self, mock_create_llm, mock_build_startup_context
    ):
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        base_llm = MagicMock()
        bound_llm = MagicMock()
        bound_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        base_llm.bind = MagicMock(return_value=bound_llm)
        mock_create_llm.return_value = base_llm

        agent = KnowledgeOnlyAgent()
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, base_llm, NullEmitter())
        compiled = workflow.compile()

        state = {
            "messages": [HumanMessage(content="new question")],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": "FRESH_CONTEXT",
            "startup_prompt_initialized": True,
            "tool_calls_executed": 0,
            "knowledge_search_results": [],
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state)

        sent_messages = bound_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)
        assert sent_messages[0].content == "FRESH_CONTEXT"
        mock_build_startup_context.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.knowledge_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.knowledge_agent.create_llm")
    async def test_agent_node_does_not_persist_injected_system_message(
        self, mock_create_llm, mock_build_startup_context
    ):
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        base_llm = MagicMock()
        bound_llm = MagicMock()
        bound_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        base_llm.bind = MagicMock(return_value=bound_llm)
        mock_create_llm.return_value = base_llm

        agent = KnowledgeOnlyAgent()
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, base_llm, NullEmitter())
        compiled = workflow.compile()

        state = {
            "messages": [HumanMessage(content="new question")],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
            "tool_calls_executed": 0,
            "knowledge_search_results": [],
            "signals_envelopes": [],
        }

        output_state = await compiled.nodes["agent"].ainvoke(state)

        sent_messages = bound_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)
        assert isinstance(output_state["messages"][0], HumanMessage)
        assert all(not isinstance(msg, SystemMessage) for msg in output_state["messages"])


class TestSafeToolNodeErrorHandling:
    """Test that safe_tool_node reports errors to LLM instead of user."""

    @pytest.mark.asyncio
    async def test_tool_execution_error_returns_tool_message(self):
        """Test that tool execution errors are returned as ToolMessages, not AIMessages.

        This ensures the LLM can decide how to handle and communicate errors,
        rather than showing raw errors directly to users.
        """
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        agent = KnowledgeOnlyAgent()

        # Create a mock tool manager that raises an exception
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_status_update.return_value = None
        mock_tool_mgr.execute_tool_calls = AsyncMock(
            side_effect=Exception("Redis connection failed")
        )

        # Create mock LLM with tools
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        # Create emitter
        emitter = NullEmitter()

        # Build the workflow to get access to the internal safe_tool_node
        workflow = agent._build_workflow(mock_tool_mgr, mock_llm, emitter)

        # Create a state with a message that has tool_calls
        tool_call_id = "test-tool-call-123"
        ai_message_with_tool_calls = AIMessage(
            content="",
            tool_calls=[
                {"id": tool_call_id, "name": "knowledge_search", "args": {"query": "test"}}
            ],
        )

        state = {
            "messages": [ai_message_with_tool_calls],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "tool_calls_executed": 0,
        }

        # Get the tools node from the compiled workflow and invoke it
        # We need to test the node directly, so we'll extract it from the workflow nodes
        compiled = workflow.compile()

        # Invoke the tools node with our test state
        # The workflow has a "tools" node that wraps safe_tool_node
        result = await compiled.nodes["tools"].ainvoke(state)

        # Verify the result contains ToolMessage(s) not AIMessage
        messages = result["messages"]
        assert len(messages) > 1, "Should have original message plus error response"

        # The last message(s) should be ToolMessage, not AIMessage
        error_messages = messages[1:]  # Skip the original AI message with tool_calls
        for msg in error_messages:
            assert isinstance(msg, ToolMessage), f"Expected ToolMessage, got {type(msg).__name__}"
            assert msg.tool_call_id == tool_call_id

            # Verify the error content has structured information for the LLM
            import json

            error_data = json.loads(msg.content)
            assert error_data["status"] == "error"
            assert "error_type" in error_data
            assert "error_message" in error_data
            assert "Redis connection failed" in error_data["error_message"]
            assert "suggestion" in error_data

    @pytest.mark.asyncio
    async def test_tool_error_includes_helpful_suggestion(self):
        """Test that error messages include suggestions for the LLM."""
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        agent = KnowledgeOnlyAgent()

        # Create a mock tool manager that raises an exception
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_status_update.return_value = None
        mock_tool_mgr.execute_tool_calls = AsyncMock(side_effect=ValueError("Invalid query"))

        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        emitter = NullEmitter()

        workflow = agent._build_workflow(mock_tool_mgr, mock_llm, emitter)

        ai_message_with_tool_calls = AIMessage(
            content="",
            tool_calls=[{"id": "tc-1", "name": "knowledge_search", "args": {"query": ""}}],
        )

        state = {
            "messages": [ai_message_with_tool_calls],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "tool_calls_executed": 0,
        }

        compiled = workflow.compile()
        result = await compiled.nodes["tools"].ainvoke(state)

        error_message = result["messages"][-1]
        assert isinstance(error_message, ToolMessage)

        import json

        error_data = json.loads(error_message.content)
        assert error_data["error_type"] == "ValueError"
        assert "retry" in error_data["suggestion"].lower()
        assert "alternative" in error_data["suggestion"].lower()

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_all_get_error_messages(self):
        """Test that when multiple tool calls fail, each gets a ToolMessage."""
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        agent = KnowledgeOnlyAgent()

        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_status_update.return_value = None
        mock_tool_mgr.execute_tool_calls = AsyncMock(
            side_effect=ConnectionError("Network unavailable")
        )

        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        emitter = NullEmitter()

        workflow = agent._build_workflow(mock_tool_mgr, mock_llm, emitter)

        # Create message with multiple tool calls
        ai_message_with_tool_calls = AIMessage(
            content="",
            tool_calls=[
                {"id": "tc-1", "name": "knowledge_search", "args": {"query": "test1"}},
                {"id": "tc-2", "name": "knowledge_search", "args": {"query": "test2"}},
                {"id": "tc-3", "name": "knowledge_ingest", "args": {"title": "doc"}},
            ],
        )

        state = {
            "messages": [ai_message_with_tool_calls],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "tool_calls_executed": 0,
        }

        compiled = workflow.compile()
        result = await compiled.nodes["tools"].ainvoke(state)

        # Should have original message + 3 ToolMessages (one per tool call)
        messages = result["messages"]
        assert len(messages) == 4, f"Expected 4 messages, got {len(messages)}"

        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 3, "Each tool call should get its own error message"

        # Verify each tool call ID is represented
        tool_call_ids = {m.tool_call_id for m in tool_messages}
        assert tool_call_ids == {"tc-1", "tc-2", "tc-3"}

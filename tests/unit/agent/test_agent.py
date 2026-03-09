"""Unit tests for SRE LangGraph Agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent, get_sre_agent


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("redis_sre_agent.agent.langgraph_agent.settings") as mock_settings:
        mock_settings.openai_api_key = "test-key"
        yield mock_settings


@pytest.fixture
def mock_llm():
    """Mock LLM for testing."""
    mock_llm_instance = MagicMock()
    with patch("redis_sre_agent.agent.langgraph_agent.create_llm") as mock_create_llm:
        with patch("redis_sre_agent.agent.langgraph_agent.create_mini_llm") as mock_create_mini:
            mock_create_llm.return_value = mock_llm_instance
            mock_create_mini.return_value = mock_llm_instance
            yield mock_llm_instance


@pytest.fixture
def mock_sre_tasks():
    """Mock SRE tasks for testing."""
    mocks = {}
    with patch("redis_sre_agent.agent.langgraph_agent.search_knowledge_base") as mock_search:
        mocks["search_knowledge_base"] = mock_search
        mock_search.return_value = {"results": [], "results_count": 0}

        with patch("redis_sre_agent.agent.langgraph_agent.check_service_health") as mock_health:
            mocks["check_service_health"] = mock_health
            mock_health.return_value = {"overall_status": "healthy", "endpoints_checked": 1}

            with patch("redis_sre_agent.agent.langgraph_agent.ingest_sre_document") as mock_ingest:
                mocks["ingest_sre_document"] = mock_ingest
                mock_ingest.return_value = {"status": "ingested", "document_id": "doc-456"}

                with patch(
                    "redis_sre_agent.agent.langgraph_agent.get_detailed_redis_diagnostics"
                ) as mock_diagnostics:
                    mocks["get_detailed_redis_diagnostics"] = mock_diagnostics
                    mock_diagnostics.return_value = {
                        "task_id": "test-789",
                        "status": "success",
                        "diagnostics": {},
                    }

                    yield mocks


class TestSRELangGraphAgent:
    """Test cases for SRE LangGraph Agent."""

    def test_init(self, mock_settings, mock_llm):
        """Test agent initialization."""
        agent = SRELangGraphAgent()

        assert agent.settings == mock_settings
        assert agent.llm is not None
        assert agent.llm_with_tools is not None
        # New architecture: tools are loaded per-query via ToolManager
        # No tools or workflow at initialization
        assert not hasattr(agent, "current_tools")
        assert not hasattr(agent, "deployment_providers")

    def test_tool_mapping(self, mock_settings, mock_llm):
        """Test that tools are loaded per-query via ToolManager."""
        agent = SRELangGraphAgent()

        # New architecture: tools are loaded per-query, not at initialization
        # This test is no longer relevant - tools come from ToolManager
        # Just verify agent initializes correctly
        assert agent.llm is not None
        assert agent.llm_with_tools is not None

    # TODO: Rewrite these tests for new ToolManager architecture
    # @pytest.mark.asyncio
    # async def test_process_query_simple(self, mock_settings, mock_llm):
    # @pytest.mark.asyncio
    # async def test_process_query_with_error(self, mock_settings, mock_llm):

    @pytest.mark.asyncio
    async def test_get_conversation_history(self, mock_settings, mock_llm):
        """Test retrieving conversation history."""
        with patch.object(SRELangGraphAgent, "__init__", lambda self: None):
            agent = SRELangGraphAgent()

            # Mock app state with real message objects
            mock_state = MagicMock()
            mock_state.values = {
                "messages": [
                    HumanMessage(content="Hello"),
                    AIMessage(content="Hi there!"),
                ]
            }

            mock_app = AsyncMock()
            mock_app.aget_state = AsyncMock(return_value=mock_state)
            agent.app = mock_app

            history = await agent.get_conversation_history("test-session")

            assert len(history) == 2
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "Hello"
            assert history[1]["role"] == "assistant"
            assert history[1]["content"] == "Hi there!"

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_process_query_seeds_startup_context_into_initial_state(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        mock_instance = MagicMock()
        mock_instance.id = "inst-1"
        mock_instance.name = "test-instance"
        mock_instance.connection_url = MagicMock()
        mock_instance.connection_url.get_secret_value.return_value = "redis://localhost:6379"
        mock_instance.environment = "development"
        mock_instance.usage = "cache"
        mock_instance.instance_type = "oss_single"
        mock_instance.repo_url = None

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr_ctx = MagicMock()
        mock_tool_mgr_ctx.__aenter__ = AsyncMock(return_value=mock_tool_mgr)
        mock_tool_mgr_ctx.__aexit__ = AsyncMock(return_value=None)

        captured: dict[str, object] = {}

        class _FakeApp:
            async def ainvoke(self, initial_state, config=None):
                captured["initial_state"] = initial_state
                return {
                    "messages": [AIMessage(content="ok", tool_calls=[])],
                    "iteration_count": 1,
                    "signals_envelopes": [],
                }

        class _FakeWorkflow:
            def compile(self, checkpointer=None):
                return _FakeApp()

        agent = SRELangGraphAgent()
        with (
            patch(
                "redis_sre_agent.agent.langgraph_agent.get_instance_by_id",
                AsyncMock(return_value=mock_instance),
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent.ToolManager",
                return_value=mock_tool_mgr_ctx,
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent._build_adapters",
                AsyncMock(return_value=[]),
            ),
            patch.object(agent, "_build_workflow", return_value=_FakeWorkflow()),
        ):
            await agent.process_query(
                query="memory question",
                session_id="s1",
                user_id="u1",
                context={"instance_id": "inst-1"},
                conversation_history=[SystemMessage(content="OLD_SYSTEM")],
            )

        initial_state = captured["initial_state"]
        assert isinstance(initial_state["messages"][0], SystemMessage)
        assert "STARTUP_CONTEXT" in initial_state["messages"][0].content
        assert initial_state["startup_system_prompt"] is None
        assert initial_state["startup_prompt_initialized"] is False

        mock_build_startup_context.assert_awaited_once()
        call_kwargs = mock_build_startup_context.await_args.kwargs
        assert call_kwargs["version"] == "latest"
        assert call_kwargs["available_tools"] == []
        assert "memory question" in call_kwargs["query"]

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_cluster_query_followup_uses_conversation_context_for_fanout(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        """Follow-up cluster queries should trigger fan-out when recent context is diagnostic."""
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        mock_cluster = MagicMock()
        mock_cluster.id = "cluster-prod-1"
        mock_cluster.name = "Production Cluster"
        mock_cluster.cluster_type = "redis_enterprise"
        mock_cluster.environment = "production"

        linked_instance = MagicMock()
        linked_instance.id = "redis-prod-1"
        linked_instance.name = "Redis Prod 1"
        linked_instance.environment = "production"
        linked_instance.cluster_id = "cluster-prod-1"

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr_ctx = MagicMock()
        mock_tool_mgr_ctx.__aenter__ = AsyncMock(return_value=mock_tool_mgr)
        mock_tool_mgr_ctx.__aexit__ = AsyncMock(return_value=None)

        fanout_payload = {
            "inspected_instances": 1,
            "total_linked_instances": 1,
            "truncated": False,
            "summary_lines": ["- Redis Prod 1: used_memory=100, connected_clients=5"],
            "aggregate": {"connected_clients": 5},
        }

        class _FakeApp:
            async def ainvoke(self, initial_state, config=None):
                return {
                    "messages": [AIMessage(content="ok", tool_calls=[])],
                    "iteration_count": 1,
                    "signals_envelopes": [],
                }

        class _FakeWorkflow:
            def compile(self, checkpointer=None):
                return _FakeApp()

        agent = SRELangGraphAgent()
        with (
            patch(
                "redis_sre_agent.core.clusters.get_cluster_by_id",
                AsyncMock(return_value=mock_cluster),
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent.get_instances",
                AsyncMock(return_value=[linked_instance]),
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent._collect_cluster_instance_diagnostics",
                AsyncMock(return_value=fanout_payload),
            ) as mock_fanout,
            patch(
                "redis_sre_agent.agent.langgraph_agent.ToolManager",
                return_value=mock_tool_mgr_ctx,
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent._build_adapters",
                AsyncMock(return_value=[]),
            ),
            patch.object(agent, "_build_workflow", return_value=_FakeWorkflow()),
        ):
            await agent.process_query(
                query="yes, check that",
                session_id="s1",
                user_id="u1",
                context={"cluster_id": "cluster-prod-1"},
                conversation_history=[
                    HumanMessage(content="check memory and clients for this cluster")
                ],
            )

        mock_fanout.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_cluster_query_followup_respects_router_context_truncation_for_fanout(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        """Fan-out heuristic context should match router formatting/truncation behavior."""
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        mock_cluster = MagicMock()
        mock_cluster.id = "cluster-prod-1"
        mock_cluster.name = "Production Cluster"
        mock_cluster.cluster_type = "redis_enterprise"
        mock_cluster.environment = "production"

        linked_instance = MagicMock()
        linked_instance.id = "redis-prod-1"
        linked_instance.name = "Redis Prod 1"
        linked_instance.environment = "production"
        linked_instance.cluster_id = "cluster-prod-1"

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr_ctx = MagicMock()
        mock_tool_mgr_ctx.__aenter__ = AsyncMock(return_value=mock_tool_mgr)
        mock_tool_mgr_ctx.__aexit__ = AsyncMock(return_value=None)

        class _FakeApp:
            async def ainvoke(self, initial_state, config=None):
                return {
                    "messages": [AIMessage(content="ok", tool_calls=[])],
                    "iteration_count": 1,
                    "signals_envelopes": [],
                }

        class _FakeWorkflow:
            def compile(self, checkpointer=None):
                return _FakeApp()

        agent = SRELangGraphAgent()
        with (
            patch(
                "redis_sre_agent.core.clusters.get_cluster_by_id",
                AsyncMock(return_value=mock_cluster),
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent.get_instances",
                AsyncMock(return_value=[linked_instance]),
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent._collect_cluster_instance_diagnostics",
                AsyncMock(return_value={}),
            ) as mock_fanout,
            patch(
                "redis_sre_agent.agent.langgraph_agent.ToolManager",
                return_value=mock_tool_mgr_ctx,
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent._build_adapters",
                AsyncMock(return_value=[]),
            ),
            patch.object(agent, "_build_workflow", return_value=_FakeWorkflow()),
        ):
            await agent.process_query(
                query="yes, check that",
                session_id="s1",
                user_id="u1",
                context={"cluster_id": "cluster-prod-1"},
                conversation_history=[
                    HumanMessage(content=f"{'x' * 520} memory and clients for this cluster")
                ],
            )

        mock_fanout.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_cluster_query_uses_fanout_and_does_not_bind_single_instance(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        """Cluster-scoped DB diagnostics should fan out across linked instances."""
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        mock_cluster = MagicMock()
        mock_cluster.id = "cluster-prod-1"
        mock_cluster.name = "Production Cluster"
        mock_cluster.cluster_type = "redis_enterprise"
        mock_cluster.environment = "production"

        mock_instance_1 = MagicMock()
        mock_instance_1.id = "redis-prod-1"
        mock_instance_1.name = "Redis Prod 1"
        mock_instance_1.environment = "production"
        mock_instance_1.cluster_id = "cluster-prod-1"

        mock_instance_2 = MagicMock()
        mock_instance_2.id = "redis-prod-2"
        mock_instance_2.name = "Redis Prod 2"
        mock_instance_2.environment = "production"
        mock_instance_2.cluster_id = "cluster-prod-1"

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr_ctx = MagicMock()
        mock_tool_mgr_ctx.__aenter__ = AsyncMock(return_value=mock_tool_mgr)
        mock_tool_mgr_ctx.__aexit__ = AsyncMock(return_value=None)

        fanout_payload = {
            "inspected_instances": 2,
            "total_linked_instances": 2,
            "truncated": False,
            "summary_lines": [
                "- Redis Prod 1: used_memory=100, connected_clients=5",
                "- Redis Prod 2: used_memory=200, connected_clients=8",
            ],
            "aggregate": {"connected_clients": 13},
        }

        captured: dict[str, object] = {}

        class _FakeApp:
            async def ainvoke(self, initial_state, config=None):
                captured["initial_state"] = initial_state
                return {
                    "messages": [AIMessage(content="ok", tool_calls=[])],
                    "iteration_count": 1,
                    "signals_envelopes": [],
                }

        class _FakeWorkflow:
            def compile(self, checkpointer=None):
                return _FakeApp()

        agent = SRELangGraphAgent()
        with (
            patch(
                "redis_sre_agent.core.clusters.get_cluster_by_id",
                AsyncMock(return_value=mock_cluster),
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent.get_instances",
                AsyncMock(return_value=[mock_instance_1, mock_instance_2]),
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent._collect_cluster_instance_diagnostics",
                AsyncMock(return_value=fanout_payload),
            ) as mock_fanout,
            patch(
                "redis_sre_agent.agent.langgraph_agent.ToolManager",
                return_value=mock_tool_mgr_ctx,
            ) as mock_tool_manager_cls,
            patch(
                "redis_sre_agent.agent.langgraph_agent._build_adapters",
                AsyncMock(return_value=[]),
            ),
            patch.object(agent, "_build_workflow", return_value=_FakeWorkflow()),
        ):
            await agent.process_query(
                query="check cluster memory and clients",
                session_id="s1",
                user_id="u1",
                context={"cluster_id": "cluster-prod-1"},
            )

        mock_fanout.assert_awaited_once()
        fanout_arg_instances = mock_fanout.await_args.args[0]
        assert len(fanout_arg_instances) == 2
        assert fanout_arg_instances[0].id == "redis-prod-1"
        assert fanout_arg_instances[1].id == "redis-prod-2"

        initial_state = captured["initial_state"]
        assert "Cluster fan-out diagnostics summary" in initial_state["messages"][-1].content
        assert "Redis Prod 1" in initial_state["messages"][-1].content
        assert "Redis Prod 2" in initial_state["messages"][-1].content

        # Fan-out mode should not bind ToolManager to a single Redis instance.
        assert mock_tool_manager_cls.call_args.kwargs.get("redis_instance") is None

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_cluster_query_with_no_linked_instances_avoids_db_specific_tools(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        """Cluster-scoped DB diagnostics should avoid DB tools when no instances are linked."""
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        mock_cluster = MagicMock()
        mock_cluster.id = "cluster-empty-1"
        mock_cluster.name = "Empty Cluster"
        mock_cluster.cluster_type = "redis_enterprise"
        mock_cluster.environment = "production"

        unrelated_instance = MagicMock()
        unrelated_instance.id = "redis-other-1"
        unrelated_instance.name = "Redis Other 1"
        unrelated_instance.environment = "production"
        unrelated_instance.cluster_id = "cluster-other"

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr_ctx = MagicMock()
        mock_tool_mgr_ctx.__aenter__ = AsyncMock(return_value=mock_tool_mgr)
        mock_tool_mgr_ctx.__aexit__ = AsyncMock(return_value=None)

        captured: dict[str, object] = {}

        class _FakeApp:
            async def ainvoke(self, initial_state, config=None):
                captured["initial_state"] = initial_state
                return {
                    "messages": [AIMessage(content="ok", tool_calls=[])],
                    "iteration_count": 1,
                    "signals_envelopes": [],
                }

        class _FakeWorkflow:
            def compile(self, checkpointer=None):
                return _FakeApp()

        agent = SRELangGraphAgent()
        with (
            patch(
                "redis_sre_agent.core.clusters.get_cluster_by_id",
                AsyncMock(return_value=mock_cluster),
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent.get_instances",
                AsyncMock(return_value=[unrelated_instance]),
            ),
            patch(
                "redis_sre_agent.agent.langgraph_agent._collect_cluster_instance_diagnostics",
                AsyncMock(return_value={}),
            ) as mock_fanout,
            patch(
                "redis_sre_agent.agent.langgraph_agent.ToolManager",
                return_value=mock_tool_mgr_ctx,
            ) as mock_tool_manager_cls,
            patch(
                "redis_sre_agent.agent.langgraph_agent._build_adapters",
                AsyncMock(return_value=[]),
            ),
            patch.object(agent, "_build_workflow", return_value=_FakeWorkflow()),
        ):
            await agent.process_query(
                query="check cluster memory and clients",
                session_id="s1",
                user_id="u1",
                context={"cluster_id": "cluster-empty-1"},
            )

        # No linked instances should skip diagnostics fan-out entirely.
        mock_fanout.assert_not_awaited()

        initial_state = captured["initial_state"]
        assert (
            "do NOT use database-specific diagnostic tools" in initial_state["messages"][-1].content
        )

        # No linked DB target should be passed into ToolManager.
        assert mock_tool_manager_cls.call_args.kwargs.get("redis_instance") is None

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_system_prompt_injected_with_conversation_history(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        """Startup context should be injected even for follow-up turns."""
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))

        agent = SRELangGraphAgent()
        agent.llm_with_tools = mock_llm
        agent._run_cache_active = False
        agent._llm_cache = {}

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, target_instance=None)
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
            "instance_context": None,
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state)

        sent_messages = mock_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)
        assert "STARTUP_CONTEXT" in sent_messages[0].content
        mock_build_startup_context.assert_awaited_once_with(
            query="follow-up question",
            version="latest",
            available_tools=[],
        )

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_system_prompt_uses_base_prompt_when_startup_context_blank(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        """Blank startup context should not prepend empty lines to the system prompt."""
        from redis_sre_agent.agent.prompts import SRE_SYSTEM_PROMPT

        mock_build_startup_context.return_value = "   "
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))

        agent = SRELangGraphAgent()
        agent.llm_with_tools = mock_llm
        agent._run_cache_active = False
        agent._llm_cache = {}

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, target_instance=None)
        compiled = workflow.compile()

        state = {
            "messages": [HumanMessage(content="follow-up question")],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "instance_context": None,
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state)

        sent_messages = mock_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)
        assert sent_messages[0].content == SRE_SYSTEM_PROMPT

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_startup_context_built_once_across_agent_iterations(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        """Startup context should be built once per workflow and then reused."""
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content="turn-1", tool_calls=[]),
                AIMessage(content="turn-2", tool_calls=[]),
            ]
        )

        agent = SRELangGraphAgent()
        agent.llm_with_tools = mock_llm
        agent._run_cache_active = False
        agent._llm_cache = {}

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, target_instance=None)
        compiled = workflow.compile()

        state = {
            "messages": [HumanMessage(content="follow-up question")],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "instance_context": None,
            "signals_envelopes": [],
        }

        state_after_first = await compiled.nodes["agent"].ainvoke(state)
        state_after_first["messages"] = [
            m for m in state_after_first["messages"] if not isinstance(m, SystemMessage)
        ]
        state_after_first["iteration_count"] = 1
        await compiled.nodes["agent"].ainvoke(state_after_first)

        assert mock_build_startup_context.await_count == 1
        sent_messages_second = mock_llm.ainvoke.call_args_list[1].args[0]
        assert isinstance(sent_messages_second[0], SystemMessage)
        assert "STARTUP_CONTEXT" in sent_messages_second[0].content

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_startup_context_not_shared_between_independent_invocations(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        mock_build_startup_context.side_effect = ["CTX_ONE", "CTX_TWO"]
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))

        agent = SRELangGraphAgent()
        agent.llm_with_tools = mock_llm
        agent._run_cache_active = False
        agent._llm_cache = {}

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, target_instance=None)
        compiled = workflow.compile()

        state_one = {
            "messages": [HumanMessage(content="first question")],
            "session_id": "session-1",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
            "instance_context": None,
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
            "instance_context": None,
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state_one)
        await compiled.nodes["agent"].ainvoke(state_two)

        assert mock_build_startup_context.await_count == 2
        sent_messages_first = mock_llm.ainvoke.call_args_list[0].args[0]
        sent_messages_second = mock_llm.ainvoke.call_args_list[1].args[0]
        assert "CTX_ONE" in sent_messages_first[0].content
        assert "CTX_TWO" in sent_messages_second[0].content

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_agent_node_rebuilds_prompt_on_first_step_when_cached_prompt_is_stale(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        mock_build_startup_context.return_value = "FRESH_CONTEXT"
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))

        agent = SRELangGraphAgent()
        agent.llm_with_tools = mock_llm
        agent._run_cache_active = False
        agent._llm_cache = {}

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, target_instance=None)
        compiled = workflow.compile()

        state = {
            "messages": [HumanMessage(content="new question")],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": "STALE_CONTEXT",
            "instance_context": None,
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state)

        sent_messages = mock_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)
        assert "FRESH_CONTEXT" in sent_messages[0].content
        assert "STALE_CONTEXT" not in sent_messages[0].content
        mock_build_startup_context.assert_awaited_once_with(
            query="new question",
            version="latest",
            available_tools=[],
        )

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_agent_node_reuses_initialized_prompt_without_rebuild(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))

        agent = SRELangGraphAgent()
        agent.llm_with_tools = mock_llm
        agent._run_cache_active = False
        agent._llm_cache = {}

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, target_instance=None)
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
            "instance_context": None,
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state)

        sent_messages = mock_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)
        assert sent_messages[0].content == "FRESH_CONTEXT"
        mock_build_startup_context.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_cached_system_prompt_preserves_instance_context_when_reinjected(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(content="turn-1", tool_calls=[]),
                AIMessage(content="turn-2", tool_calls=[]),
            ]
        )

        agent = SRELangGraphAgent()
        agent.llm_with_tools = mock_llm
        agent._run_cache_active = False
        agent._llm_cache = {}

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        target_instance = MagicMock()
        target_instance.instance_type = "redis_cloud"
        workflow = agent._build_workflow(mock_tool_mgr, target_instance=target_instance)
        compiled = workflow.compile()

        state = {
            "messages": [
                SystemMessage(content="PREBUILT_SYSTEM_PROMPT"),
                HumanMessage(content="follow-up question"),
            ],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "instance_context": None,
            "signals_envelopes": [],
        }

        state_after_first = await compiled.nodes["agent"].ainvoke(state)
        sent_messages_first = mock_llm.ainvoke.call_args_list[0].args[0]
        assert "CRITICAL REDIS CLOUD CONTEXT" in sent_messages_first[0].content

        state_after_first["messages"] = [
            m for m in state_after_first["messages"] if not isinstance(m, SystemMessage)
        ]
        state_after_first["iteration_count"] = 1
        await compiled.nodes["agent"].ainvoke(state_after_first)

        sent_messages_second = mock_llm.ainvoke.call_args_list[1].args[0]
        assert isinstance(sent_messages_second[0], SystemMessage)
        assert "CRITICAL REDIS CLOUD CONTEXT" in sent_messages_second[0].content
        assert mock_build_startup_context.await_count == 0

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_cloud_context_does_not_fall_through_to_enterprise_context(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))

        agent = SRELangGraphAgent()
        agent.llm_with_tools = mock_llm
        agent._run_cache_active = False
        agent._llm_cache = {}

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        target_instance = MagicMock()
        target_instance.instance_type = "redis_cloud"
        workflow = agent._build_workflow(mock_tool_mgr, target_instance=target_instance)
        compiled = workflow.compile()

        state = {
            "messages": [
                SystemMessage(content="BASE\n\n## CRITICAL REDIS CLOUD CONTEXT\npresent"),
                HumanMessage(content="follow-up question"),
            ],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "instance_context": None,
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state)

        sent_messages = mock_llm.ainvoke.call_args.args[0]
        assert "CRITICAL REDIS CLOUD CONTEXT" in sent_messages[0].content
        assert "CRITICAL REDIS ENTERPRISE CONTEXT" not in sent_messages[0].content
        assert mock_build_startup_context.await_count == 0

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.langgraph_agent.build_startup_knowledge_context")
    async def test_agent_node_does_not_persist_injected_system_message(
        self, mock_build_startup_context, mock_settings, mock_llm
    ):
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))

        agent = SRELangGraphAgent()
        agent.llm_with_tools = mock_llm
        agent._run_cache_active = False
        agent._llm_cache = {}

        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        workflow = agent._build_workflow(mock_tool_mgr, target_instance=None)
        compiled = workflow.compile()

        state = {
            "messages": [HumanMessage(content="new question")],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
            "instance_context": None,
            "signals_envelopes": [],
        }

        output_state = await compiled.nodes["agent"].ainvoke(state)

        sent_messages = mock_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)
        assert isinstance(output_state["messages"][0], HumanMessage)
        assert all(not isinstance(msg, SystemMessage) for msg in output_state["messages"])

    def test_clear_conversation(self, mock_settings, mock_llm):
        """Test clearing conversation history."""
        with patch.object(SRELangGraphAgent, "__init__", lambda self: None):
            agent = SRELangGraphAgent()

            result = agent.clear_conversation("test-session")

            # For now, this always returns True
            assert result is True


class TestAgentSingleton:
    """Test agent singleton behavior."""

    def test_get_sre_agent_creates_new_instances(self):
        """Test that get_sre_agent creates new instances (no longer singleton)."""
        with patch("redis_sre_agent.agent.langgraph_agent.SRELangGraphAgent") as mock_agent_class:
            mock_instance1 = MagicMock()
            mock_instance2 = MagicMock()
            mock_agent_class.side_effect = [mock_instance1, mock_instance2]

            agent1 = get_sre_agent()
            agent2 = get_sre_agent()

            # Should create new instances each time (not singleton)
            assert agent1 is mock_instance1
            assert agent2 is mock_instance2
            assert mock_agent_class.call_count == 2


class TestAgentToolBindings:
    """Test agent tool bindings and schemas."""

    def test_tool_schemas(self, mock_settings, mock_llm):
        """Test that tool schemas are loaded per-query."""
        agent = SRELangGraphAgent()

        # The agent should have llm_with_tools attribute
        assert hasattr(agent, "llm_with_tools")

        # New architecture: bind_tools is NOT called at initialization
        # Tools are bound per-query in process_query
        # At init, llm_with_tools just equals llm
        assert agent.llm_with_tools == agent.llm


@pytest.mark.asyncio
class TestAgentWorkflow:
    """Test the LangGraph workflow construction and execution."""

    async def test_workflow_construction(self, mock_settings, mock_llm):
        """Test that the workflow is constructed per-query."""
        agent = SRELangGraphAgent()

        # New architecture: workflow is built per-query, not at initialization
        assert not hasattr(agent, "workflow")
        assert agent.llm is not None
        assert agent.llm_with_tools is not None

    async def test_agent_state_schema(self, mock_settings, mock_llm):
        """Test that AgentState schema is properly defined."""
        from redis_sre_agent.agent.langgraph_agent import AgentState

        # Test that AgentState has required fields
        required_fields = [
            "messages",
            "session_id",
            "user_id",
            "current_tool_calls",
            "iteration_count",
            "max_iterations",
            "startup_system_prompt",
            "startup_prompt_initialized",
            "instance_context",  # Added in the new implementation
            "signals_envelopes",
        ]

        # AgentState is a TypedDict, so we can check __annotations__
        assert set(AgentState.__annotations__.keys()) == set(required_fields)

    async def test_sre_tool_call_model(self):
        """Test SREToolCall model validation."""
        from redis_sre_agent.agent.langgraph_agent import SREToolCall

        # Test valid tool call
        tool_call = SREToolCall(
            tool_name="search_knowledge_base",
            arguments={"query": "redis memory", "limit": 5},
        )

        assert tool_call.tool_name == "search_knowledge_base"
        assert tool_call.arguments["query"] == "redis memory"
        assert tool_call.tool_call_id is not None  # Should be auto-generated

        # Test that tool_call_id is a valid UUID string
        import uuid

        uuid.UUID(tool_call.tool_call_id)  # Should not raise exception


@pytest.mark.asyncio
class TestAgentRetryLogic:
    """Test the retry functionality for LLM responses."""

    async def test_retry_with_backoff_success(self, mock_settings, mock_llm):
        """Test retry logic succeeds on second attempt."""
        agent = SRELangGraphAgent()

        call_count = 0

        async def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("First attempt fails")
            return "success"

        result = await agent._retry_with_backoff(failing_func, max_retries=2, initial_delay=0.01)

        assert result == "success"
        assert call_count == 2

    async def test_retry_with_backoff_all_fail(self, mock_settings, mock_llm):
        """Test retry logic when all attempts fail."""
        agent = SRELangGraphAgent()

        call_count = 0

        async def always_failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError(f"Attempt {call_count} failed")

        with pytest.raises(ValueError, match="Attempt 3 failed"):
            await agent._retry_with_backoff(always_failing_func, max_retries=2, initial_delay=0.01)

        assert call_count == 3  # Initial attempt + 2 retries


@pytest.mark.asyncio
class TestSupportPackageContext:
    """Test support package context handling.

    Regression tests for support package queries being correctly focused
    on the package data rather than configured Redis instances.
    """

    async def test_support_package_context_passed_to_tool_manager(self, mock_settings, mock_llm):
        """Test that support package context is passed to ToolManager.

        Regression test: When a support package path is provided, it should be
        passed to the ToolManager so support package tools are loaded.
        """
        # Track what ToolManager was called with
        captured_kwargs = {}

        class MockToolManager:
            def __init__(self, **kwargs):
                captured_kwargs.update(kwargs)
                self._tools = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def get_tools(self):
                return []

        # Mock ToolManager at module level before creating agent
        with patch("redis_sre_agent.agent.langgraph_agent.ToolManager", MockToolManager):
            agent = SRELangGraphAgent()

            # Execute with support package context - will fail but we just need
            # to verify ToolManager was called with the right args
            context = {"support_package_path": "/tmp/packages/test-package"}
            try:
                await agent.process_query(
                    query="What databases are in this package?",
                    session_id="test-session",
                    user_id="test-user",
                    context=context,
                )
            except Exception:
                # Expected - we're not fully mocking the workflow
                pass

        # Verify support_package_path was passed to ToolManager
        assert "support_package_path" in captured_kwargs
        assert str(captured_kwargs["support_package_path"]) == "/tmp/packages/test-package"


class TestAgentSystemPrompt:
    """Test the agent system prompt."""

    def test_system_prompt_exists(self, mock_settings, mock_llm):
        """Test that the system prompt is defined."""
        from redis_sre_agent.agent.prompts import SRE_SYSTEM_PROMPT

        assert SRE_SYSTEM_PROMPT is not None
        assert len(SRE_SYSTEM_PROMPT) > 100

    def test_system_prompt_mentions_redis(self, mock_settings, mock_llm):
        """Test that the system prompt mentions Redis."""
        from redis_sre_agent.agent.prompts import SRE_SYSTEM_PROMPT

        assert "Redis" in SRE_SYSTEM_PROMPT

    def test_system_prompt_mentions_sre(self, mock_settings, mock_llm):
        """Test that the system prompt mentions SRE."""
        from redis_sre_agent.agent.prompts import SRE_SYSTEM_PROMPT

        assert "SRE" in SRE_SYSTEM_PROMPT


class TestAgentEmitter:
    """Test the agent emitter functionality."""

    def test_agent_has_progress_emitter(self, mock_settings, mock_llm):
        """Test that agent has _progress_emitter attribute."""
        agent = SRELangGraphAgent()
        assert hasattr(agent, "_progress_emitter")

    def test_agent_with_custom_emitter(self, mock_settings, mock_llm):
        """Test agent initialization with custom emitter."""
        from redis_sre_agent.core.progress import NullEmitter

        emitter = NullEmitter()
        agent = SRELangGraphAgent(progress_emitter=emitter)
        assert agent._progress_emitter is emitter

    def test_agent_default_emitter(self, mock_settings, mock_llm):
        """Test agent uses NullEmitter by default."""
        from redis_sre_agent.core.progress import NullEmitter

        agent = SRELangGraphAgent()
        assert isinstance(agent._progress_emitter, NullEmitter)


class TestAgentMiniLLM:
    """Test the agent mini LLM functionality."""

    def test_agent_has_mini_llm(self, mock_settings, mock_llm):
        """Test that agent has mini_llm attribute."""
        agent = SRELangGraphAgent()
        assert hasattr(agent, "mini_llm")
        assert agent.mini_llm is not None

    def test_agent_has_llm(self, mock_settings, mock_llm):
        """Test that agent has llm attribute."""
        agent = SRELangGraphAgent()
        assert hasattr(agent, "llm")
        assert agent.llm is not None


class TestAgentBuildWorkflow:
    """Test the _build_workflow method."""

    def test_build_workflow_returns_state_graph(self, mock_settings, mock_llm):
        """Test that _build_workflow returns a StateGraph."""
        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        agent = SRELangGraphAgent()

        # Create mock tool manager
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_status_update.return_value = None

        # Create emitter
        emitter = NullEmitter()

        # _build_workflow takes (tool_mgr, emitter) as positional args
        workflow = agent._build_workflow(mock_tool_mgr, emitter)
        assert workflow is not None

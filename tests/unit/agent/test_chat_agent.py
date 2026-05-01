"""Unit tests for the lightweight Chat Agent."""

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from redis_sre_agent.agent.chat_agent import (
    CHAT_SYSTEM_PROMPT,
    ChatAgent,
    ChatAgentState,
    get_chat_agent,
)
from redis_sre_agent.core.agent_memory import PreparedAgentTurnMemory, TurnMemoryContext
from redis_sre_agent.core.clusters import RedisCluster, RedisClusterType
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.core.progress import NullEmitter


class TestChatAgentInitialization:
    """Test ChatAgent initialization."""

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_agent_initializes_without_instance(self, mock_create_mini_llm, mock_create_llm):
        """Test that ChatAgent initializes correctly without a Redis instance."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        assert agent.llm is mock_llm
        assert agent.mini_llm is mock_llm  # Both use the same mock
        assert agent.redis_instance is None
        # Should have NullEmitter by default
        assert isinstance(agent._emitter, NullEmitter)
        # Now creates 2 LLM instances (llm and mini_llm)
        assert mock_create_llm.call_count == 1
        assert mock_create_mini_llm.call_count == 1

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_agent_initializes_with_instance(self, mock_create_mini_llm, mock_create_llm):
        """Test that ChatAgent initializes correctly with a Redis instance."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        instance = RedisInstance(
            id="test-id",
            name="test-instance",
            connection_url="redis://localhost:6379",
            environment="development",
            usage="cache",
            description="Test instance",
            instance_type="oss_single",
        )

        agent = ChatAgent(redis_instance=instance)

        assert agent.llm is mock_llm
        assert agent.redis_instance is instance
        assert agent.redis_instance.name == "test-instance"

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_agent_initializes_with_cluster(self, mock_create_mini_llm, mock_create_llm):
        """Test that ChatAgent accepts cluster-only context."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        cluster = RedisCluster(
            id="cluster-1",
            name="test-cluster",
            cluster_type=RedisClusterType.redis_enterprise,
            environment="test",
            description="Test cluster",
            admin_url="https://cluster.example.com:9443",
            admin_username="admin@redis.com",
            admin_password="secret",
        )

        agent = ChatAgent(redis_cluster=cluster)

        assert agent.llm is mock_llm
        assert agent.redis_cluster is cluster
        assert agent.redis_instance is None

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_agent_initializes_with_progress_emitter(self, mock_create_mini_llm, mock_create_llm):
        """Test that ChatAgent accepts a progress_emitter."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        emitter = NullEmitter()
        agent = ChatAgent(progress_emitter=emitter)

        assert agent._emitter is emitter

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_agent_no_temperature_parameter(self, mock_create_mini_llm, mock_create_llm):
        """Test that ChatAgent doesn't use temperature parameter (reasoning models)."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        ChatAgent()

        # Verify create_llm was called without temperature parameter
        call_args = mock_create_llm.call_args
        if call_args is not None:
            assert "temperature" not in (call_args.kwargs or {})


class TestChatAgentSingleton:
    """Test get_chat_agent singleton behavior."""

    def test_get_chat_agent_without_instance(self):
        """Test get_chat_agent returns agent without instance."""
        with patch("redis_sre_agent.agent.chat_agent.ChatAgent") as mock_agent_class:
            mock_instance = MagicMock()
            mock_agent_class.return_value = mock_instance

            # Clear cache
            from redis_sre_agent.agent import chat_agent

            chat_agent._chat_agents.clear()

            agent = get_chat_agent()

            assert agent is mock_instance
            mock_agent_class.assert_called_once_with(
                redis_instance=None,
                redis_cluster=None,
            )

    def test_get_chat_agent_caches_by_instance_name(self):
        """Test get_chat_agent caches agents by instance name."""
        with patch("redis_sre_agent.agent.chat_agent.ChatAgent") as mock_agent_class:
            mock_agent1 = MagicMock()
            mock_agent2 = MagicMock()
            mock_agent_class.side_effect = [mock_agent1, mock_agent2]

            # Clear cache
            from redis_sre_agent.agent import chat_agent

            chat_agent._chat_agents.clear()

            instance1 = RedisInstance(
                id="id-1",
                name="instance-1",
                connection_url="redis://localhost:6379",
                environment="development",
                usage="cache",
                description="Test instance 1",
                instance_type="oss_single",
            )
            instance2 = RedisInstance(
                id="id-2",
                name="instance-2",
                connection_url="redis://localhost:6380",
                environment="development",
                usage="cache",
                description="Test instance 2",
                instance_type="oss_single",
            )

            agent1 = get_chat_agent(redis_instance=instance1)
            agent1_again = get_chat_agent(redis_instance=instance1)
            agent2 = get_chat_agent(redis_instance=instance2)

            # Same instance name should return cached agent
            assert agent1 is agent1_again
            # Different instance name should return new agent
            assert agent1 is not agent2
            assert mock_agent_class.call_count == 2

    def test_get_chat_agent_caches_by_cluster_id(self):
        """Test get_chat_agent caches cluster-scoped agents separately."""
        with patch("redis_sre_agent.agent.chat_agent.ChatAgent") as mock_agent_class:
            mock_agent1 = MagicMock()
            mock_agent2 = MagicMock()
            mock_agent_class.side_effect = [mock_agent1, mock_agent2]

            from redis_sre_agent.agent import chat_agent

            chat_agent._chat_agents.clear()

            cluster1 = RedisCluster(
                id="cluster-1",
                name="cluster-1",
                cluster_type=RedisClusterType.redis_enterprise,
                environment="test",
                description="cluster 1",
                admin_url="https://cluster-1.example.com:9443",
                admin_username="admin@redis.com",
                admin_password="secret",
            )
            cluster2 = RedisCluster(
                id="cluster-2",
                name="cluster-2",
                cluster_type=RedisClusterType.redis_enterprise,
                environment="test",
                description="cluster 2",
                admin_url="https://cluster-2.example.com:9443",
                admin_username="admin@redis.com",
                admin_password="secret",
            )

            agent1 = get_chat_agent(redis_cluster=cluster1)
            agent1_again = get_chat_agent(redis_cluster=cluster1)
            agent2 = get_chat_agent(redis_cluster=cluster2)

            assert agent1 is agent1_again
            assert agent1 is not agent2
            assert mock_agent_class.call_count == 2


class TestChatAgentSystemPrompt:
    """Test the chat agent system prompt."""

    def test_system_prompt_is_concise(self):
        """Test that the system prompt is focused and concise."""
        assert "Redis SRE agent" in CHAT_SYSTEM_PROMPT
        # Should mention an approach methodology (iterative, strategic, focused, etc.)
        prompt_lower = CHAT_SYSTEM_PROMPT.lower()
        assert any(
            term in prompt_lower
            for term in ["iterative", "strategic", "focused", "step by step", "targeted"]
        )
        # Should mention full triage as alternative
        assert "triage" in prompt_lower

    def test_system_prompt_mentions_tools(self):
        """Test that the system prompt mentions tool usage."""
        assert "tool" in CHAT_SYSTEM_PROMPT.lower()

    def test_system_prompt_guides_target_discovery_inventory_and_comparison(self):
        """Test that the prompt guides listing, resolution, and multi-target comparisons."""
        prompt_lower = CHAT_SYSTEM_PROMPT.lower()
        assert "list_known_redis_targets" in CHAT_SYSTEM_PROMPT
        assert "resolve_redis_targets" in CHAT_SYSTEM_PROMPT
        assert "allow_multiple=true" in CHAT_SYSTEM_PROMPT
        assert "what redis targets you know about" in prompt_lower

    def test_system_prompt_warns_about_managed_redis(self):
        """Test that the system prompt has Redis Enterprise/Cloud notes."""
        assert "Enterprise" in CHAT_SYSTEM_PROMPT or "Cloud" in CHAT_SYSTEM_PROMPT
        assert "INFO" in CHAT_SYSTEM_PROMPT


class TestChatAgentState:
    """Test the ChatAgentState TypedDict."""

    def test_state_has_required_fields(self):
        """Test that ChatAgentState has all required fields."""
        state: ChatAgentState = {
            "messages": [],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
            "toolset_generation": 0,
            "signals_envelopes": [],
        }

        assert "messages" in state
        assert "session_id" in state
        assert "user_id" in state
        assert "current_tool_calls" in state
        assert "iteration_count" in state
        assert "max_iterations" in state
        assert "startup_system_prompt" in state
        assert "toolset_generation" in state
        assert "signals_envelopes" in state


class TestChatAgentWorkflowBuild:
    """Test the _build_workflow method and emitter parameter."""

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_build_workflow_accepts_emitter(self, mock_create_mini_llm, mock_create_llm):
        """Test that _build_workflow accepts an emitter parameter."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        # Create a mock tool manager
        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_status_update.return_value = None
        mock_tool_mgr.get_toolset_generation.return_value = 1

        # Create a mock emitter
        emitter = NullEmitter()

        # Should not raise - emitter is now accepted
        workflow = agent._build_workflow(
            tool_mgr=mock_tool_mgr,
            emitter=emitter,
        )

        assert workflow is not None

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_build_workflow_works_without_emitter(self, mock_create_mini_llm, mock_create_llm):
        """Test that _build_workflow works when emitter is None."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        # Create a mock tool manager
        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_toolset_generation.return_value = 1

        # Should not raise when emitter is None
        workflow = agent._build_workflow(
            tool_mgr=mock_tool_mgr,
            emitter=None,
        )

        assert workflow is not None


class TestChatAgentExpandEvidenceTool:
    """Test the _build_expand_evidence_tool method.

    The method uses a mutable container pattern so the tool can be added
    to the LLM's tool list from the start, but access envelopes as they're
    populated by other tool calls.
    """

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_expand_evidence_tool_returns_full_data(self, mock_create_mini_llm, mock_create_llm):
        """Test that expand_evidence tool returns full data for known key."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        envelopes = [
            {"tool_key": "redis_info_1", "name": "get_redis_info", "data": {"memory": "1GB"}},
            {"tool_key": "cluster_info_2", "name": "get_cluster_info", "data": {"nodes": 3}},
        ]
        envelopes_container = {"envelopes": envelopes}

        tool_def = agent._build_expand_evidence_tool(envelopes_container)

        # Get the function from the tool definition
        expand_fn = tool_def["func"]

        # Test retrieving known key
        result = expand_fn("redis_info_1")
        assert result["status"] == "success"
        assert result["tool_key"] == "redis_info_1"
        assert result["full_data"] == {"memory": "1GB"}

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_expand_evidence_tool_error_for_unknown_key(
        self, mock_create_mini_llm, mock_create_llm
    ):
        """Test that expand_evidence tool returns error for unknown key."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        envelopes = [
            {"tool_key": "redis_info_1", "name": "get_redis_info", "data": {"memory": "1GB"}},
        ]
        envelopes_container = {"envelopes": envelopes}

        tool_def = agent._build_expand_evidence_tool(envelopes_container)
        expand_fn = tool_def["func"]

        # Test retrieving unknown key
        result = expand_fn("unknown_key")
        assert result["status"] == "error"
        assert "Unknown tool_key" in result["error"]

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_expand_evidence_tool_empty_envelopes(self, mock_create_mini_llm, mock_create_llm):
        """Test expand_evidence tool with empty envelopes returns helpful error."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        envelopes_container = {"envelopes": []}
        tool_def = agent._build_expand_evidence_tool(envelopes_container)
        expand_fn = tool_def["func"]

        result = expand_fn("any_key")
        assert result["status"] == "error"
        assert "No tool calls have been made yet" in result["error"]

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_expand_evidence_progress_message_without_query(
        self, mock_create_mini_llm, mock_create_llm
    ):
        """Expand-evidence progress should read naturally without a query."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()
        tool_mgr = MagicMock()
        tool_mgr.get_status_update.return_value = None

        message = agent._tool_call_progress_message(
            tool_mgr,
            "expand_evidence",
            {"tool_key": "knowledge_search_1"},
        )

        assert (
            message
            == "I have a preview of the last tool call's output. I'm retrieving the full output now."
        )

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_expand_evidence_progress_message_with_query(
        self, mock_create_mini_llm, mock_create_llm
    ):
        """Expand-evidence progress should include the requested JMESPath."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()
        tool_mgr = MagicMock()
        tool_mgr.get_status_update.return_value = None

        message = agent._tool_call_progress_message(
            tool_mgr,
            "expand_evidence",
            {"tool_key": "knowledge_search_1", "query": "results[*].title"},
        )

        assert (
            message
            == "I have a preview of the last tool call's output. I'm retrieving the full output now. Applying JMESPath query: results[*].title"
        )


class TestChatAgentExcludeMcpCategories:
    """Test exclude_mcp_categories parameter."""

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_agent_stores_exclude_categories(self, mock_create_mini_llm, mock_create_llm):
        """Test that agent stores exclude_mcp_categories."""
        from redis_sre_agent.tools.models import ToolCapability

        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        exclude = [ToolCapability.METRICS, ToolCapability.LOGS]
        agent = ChatAgent(exclude_mcp_categories=exclude)

        assert agent.exclude_mcp_categories == exclude

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_agent_none_exclude_categories(self, mock_create_mini_llm, mock_create_llm):
        """Test that agent handles None exclude_mcp_categories."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent(exclude_mcp_categories=None)

        assert agent.exclude_mcp_categories is None


class TestChatAgentSupportPackage:
    """Test support_package_path parameter."""

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_agent_stores_support_package_path(self, mock_create_mini_llm, mock_create_llm):
        """Test that agent stores support_package_path."""
        from pathlib import Path

        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        path = Path("/tmp/support_package")
        agent = ChatAgent(support_package_path=path)

        assert agent.support_package_path == path

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_agent_none_support_package_path(self, mock_create_mini_llm, mock_create_llm):
        """Test that agent handles None support_package_path."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent(support_package_path=None)

        assert agent.support_package_path is None


class TestChatAgentEnvelopeSummaryThreshold:
    """Test ENVELOPE_SUMMARY_THRESHOLD constant."""

    def test_threshold_is_positive(self):
        """Test that ENVELOPE_SUMMARY_THRESHOLD is a positive number."""
        assert ChatAgent.ENVELOPE_SUMMARY_THRESHOLD > 0

    def test_threshold_is_reasonable(self):
        """Test that ENVELOPE_SUMMARY_THRESHOLD is a reasonable value."""
        # Should be at least 100 chars to be useful
        assert ChatAgent.ENVELOPE_SUMMARY_THRESHOLD >= 100
        # Should not be too large (e.g., > 10000)
        assert ChatAgent.ENVELOPE_SUMMARY_THRESHOLD <= 10000


class TestChatAgentCreateSummarizedToolMessage:
    """Test the _create_summarized_tool_message method."""

    def test_small_data_returns_original_message(self):
        """Test that small data returns the original message unchanged."""
        from langchain_core.messages import ToolMessage

        agent = ChatAgent()
        original_msg = ToolMessage(content='{"key": "small"}', tool_call_id="test123")
        data = {"key": "small"}

        result = agent._create_summarized_tool_message(original_msg, "test_tool", data)

        assert result.content == original_msg.content
        assert result.tool_call_id == "test123"

    def test_large_data_creates_summarized_message(self):
        """Test that large data creates a summarized message with preview."""
        from langchain_core.messages import ToolMessage

        agent = ChatAgent()
        large_data = {"results": [{"title": f"Item {i}", "content": "x" * 200} for i in range(10)]}
        original_content = '{"results": [' + ",".join(['{"title": "test"}'] * 10) + "]}"
        original_msg = ToolMessage(content=original_content, tool_call_id="test456")

        result = agent._create_summarized_tool_message(original_msg, "knowledge_search", large_data)

        # Should be a different message
        assert result.content != original_msg.content
        # Should contain warning about large/truncated data
        assert "LARGE RESULT" in result.content or "TRUNCATED" in result.content
        # Should contain structure info with item keys shown
        assert "results: [10 items]" in result.content
        assert "each with keys" in result.content
        # Should contain expand_evidence instructions at the top
        assert "expand_evidence" in result.content
        assert "tool_key='knowledge_search'" in result.content

    def test_summarized_message_preserves_tool_call_id(self):
        """Test that summarized message preserves the tool_call_id."""
        from langchain_core.messages import ToolMessage

        agent = ChatAgent()
        large_data = {"items": ["x" * 100 for _ in range(20)]}
        original_msg = ToolMessage(content='{"large": true}', tool_call_id="preserve_me")

        result = agent._create_summarized_tool_message(original_msg, "test_tool", large_data)

        assert result.tool_call_id == "preserve_me"

    def test_summarized_message_shows_array_lengths(self):
        """Test that summarized message shows array lengths in structure."""
        from langchain_core.messages import ToolMessage

        agent = ChatAgent()
        data = {"results": [1, 2, 3, 4, 5], "metadata": {"key": "value"}, "count": 5}
        # Make it large enough to trigger summarization
        data["padding"] = "x" * 1000
        original_msg = ToolMessage(content='{"test": true}', tool_call_id="test789")

        result = agent._create_summarized_tool_message(original_msg, "test_tool", data)

        assert "results: [5 items]" in result.content
        assert "metadata: {...}" in result.content


class TestChatAgentStartupContext:
    """Test startup context injection in chat agent."""

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_includes_shared_startup_context(
        self, mock_create_mini_llm, mock_create_llm
    ):
        """Chat agent should prepend pinned/skills/tool startup context like other agents."""
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        mock_tool = MagicMock()
        mock_tool.name = "knowledge_test_skills_check"

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = [mock_tool]
        mock_tool_manager.get_toolset_generation.return_value = 3

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="final answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ) as mock_tool_manager_class,
            patch(
                "redis_sre_agent.agent.helpers.build_adapters_for_tooldefs",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.build_startup_knowledge_context",
                new=AsyncMock(return_value="Pinned documents:\n- Acronyms"),
            ) as mock_startup_context,
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Who runs AOP?",
                session_id="test-session",
                user_id="test-user",
            )

        assert response.response == "final answer"
        assert mock_tool_manager_class.called

        initial_state = fake_app.ainvoke.await_args.args[0]
        system_message = initial_state["messages"][0]
        assert "Pinned documents:" in str(system_message.content)
        assert CHAT_SYSTEM_PROMPT in str(system_message.content)
        assert initial_state["toolset_generation"] == 3

        mock_startup_context.assert_awaited_once()
        startup_kwargs = mock_startup_context.await_args.kwargs
        assert startup_kwargs["query"] == "Who runs AOP?"
        assert startup_kwargs["available_tools"] == [mock_tool]

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_preserves_missing_user_id_for_tool_manager(
        self, mock_create_mini_llm, mock_create_llm
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        prepared_memory = PreparedAgentTurnMemory(
            memory_service=MagicMock(),
            memory_context=TurnMemoryContext(
                system_prompt=None,
                user_working_memory=None,
                asset_working_memory=None,
            ),
            session_id="test-session",
            user_id=None,
            query="Who runs AOP?",
            instance_id=None,
            cluster_id=None,
            emitter=None,
        )
        prepared_memory.persist_response_fail_open = AsyncMock()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="final answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.prepare_agent_turn_memory",
                AsyncMock(return_value=prepared_memory),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ) as mock_tool_manager_class,
            patch(
                "redis_sre_agent.agent.chat_agent.build_startup_knowledge_context",
                new=AsyncMock(return_value=""),
            ),
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Who runs AOP?",
                session_id="test-session",
                user_id=None,
            )

        assert response.response == "final answer"
        assert mock_tool_manager_class.call_args.kwargs["user_id"] is None
        prepared_memory.persist_response_fail_open.assert_awaited_once_with("final answer")

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_prefers_thread_id_from_context_for_tool_manager(
        self, mock_create_mini_llm, mock_create_llm
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        prepared_memory = PreparedAgentTurnMemory(
            memory_service=MagicMock(),
            memory_context=TurnMemoryContext(
                system_prompt=None,
                user_working_memory=None,
                asset_working_memory=None,
            ),
            session_id="session-123",
            user_id="test-user",
            query="Compare targets",
            instance_id=None,
            cluster_id=None,
            emitter=None,
        )
        prepared_memory.persist_response_fail_open = AsyncMock()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="final answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.prepare_agent_turn_memory",
                AsyncMock(return_value=prepared_memory),
            ) as mock_prepare_memory,
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ) as mock_tool_manager_class,
            patch(
                "redis_sre_agent.agent.chat_agent.build_startup_knowledge_context",
                new=AsyncMock(return_value=""),
            ),
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            await agent.process_query(
                query="Compare targets",
                session_id="session-123",
                user_id="test-user",
                context={"thread_id": "thread-456"},
            )

        assert mock_tool_manager_class.call_args.kwargs["thread_id"] == "thread-456"
        assert (
            mock_prepare_memory.await_args.kwargs["context"]["turn_scope"]["thread_id"]
            == "thread-456"
        )
        assert (
            mock_prepare_memory.await_args.kwargs["context"]["turn_scope"]["session_id"]
            == "session-123"
        )

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_uses_support_package_path_from_turn_scope_context(
        self, mock_create_mini_llm, mock_create_llm
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        prepared_memory = PreparedAgentTurnMemory(
            memory_service=MagicMock(),
            memory_context=TurnMemoryContext(
                system_prompt=None,
                user_working_memory=None,
                asset_working_memory=None,
            ),
            session_id="test-session",
            user_id="test-user",
            query="Inspect package",
            instance_id=None,
            cluster_id=None,
            emitter=None,
        )
        prepared_memory.persist_response_fail_open = AsyncMock()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="final answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.prepare_agent_turn_memory",
                AsyncMock(return_value=prepared_memory),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ) as mock_tool_manager_class,
            patch(
                "redis_sre_agent.agent.chat_agent.build_startup_knowledge_context",
                new=AsyncMock(return_value=""),
            ),
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            await agent.process_query(
                query="Inspect package",
                session_id="test-session",
                user_id="test-user",
                context={"support_package_path": "/tmp/support-package.zip"},
            )

        assert mock_tool_manager_class.call_args.kwargs["support_package_path"] == Path(
            "/tmp/support-package.zip"
        )

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_includes_cluster_context(
        self, mock_create_mini_llm, mock_create_llm
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        cluster = RedisCluster(
            id="cluster-1",
            name="test-cluster",
            cluster_type=RedisClusterType.redis_enterprise,
            environment="test",
            description="Test cluster",
            admin_url="https://cluster.example.com:9443",
            admin_username="admin@redis.com",
            admin_password="secret",
        )
        agent = ChatAgent(redis_cluster=cluster)

        prepared_memory = PreparedAgentTurnMemory(
            memory_service=MagicMock(),
            memory_context=TurnMemoryContext(
                system_prompt=None,
                user_working_memory=None,
                asset_working_memory=None,
            ),
            session_id="test-session",
            user_id="test-user",
            query="Inspect cluster",
            instance_id=None,
            cluster_id=None,
            emitter=None,
        )
        prepared_memory.persist_response_fail_open = AsyncMock()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="final answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.prepare_agent_turn_memory",
                AsyncMock(return_value=prepared_memory),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.build_startup_knowledge_context",
                new=AsyncMock(return_value=""),
            ),
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            await agent.process_query(
                query="Inspect cluster",
                session_id="test-session",
                user_id="test-user",
            )

        human_message = fake_app.ainvoke.await_args.args[0]["messages"][-1].content
        assert "CLUSTER CONTEXT: This query is about Redis cluster" in human_message
        assert "Cluster Name: test-cluster" in human_message

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_uses_redis_checkpointing_and_persists_metadata(
        self, mock_create_mini_llm, mock_create_llm
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        prepared_memory = PreparedAgentTurnMemory(
            memory_service=MagicMock(),
            memory_context=TurnMemoryContext(
                system_prompt=None,
                user_working_memory=None,
                asset_working_memory=None,
            ),
            session_id="session-1",
            user_id="user-1",
            query="Who runs AOP?",
            instance_id=None,
            cluster_id=None,
            emitter=None,
        )
        prepared_memory.persist_response_fail_open = AsyncMock()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        captured: dict[str, object] = {}
        fake_checkpointer = MagicMock()

        @asynccontextmanager
        async def fake_open_graph_checkpointer(**_kwargs):
            yield fake_checkpointer

        class _FakeApp:
            async def ainvoke(self, initial_state, config=None):
                captured["config"] = config
                return {
                    "messages": [AIMessage(content="final answer")],
                    "signals_envelopes": [],
                }

        fake_workflow = MagicMock()
        fake_workflow.compile.side_effect = lambda checkpointer=None: (
            captured.update({"checkpointer": checkpointer}) or _FakeApp()
        )

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.prepare_agent_turn_memory",
                AsyncMock(return_value=prepared_memory),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.build_startup_knowledge_context",
                new=AsyncMock(return_value=""),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.open_graph_checkpointer",
                side_effect=fake_open_graph_checkpointer,
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.persist_checkpoint_metadata",
                AsyncMock(),
            ) as mock_persist_checkpoint_metadata,
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Who runs AOP?",
                session_id="session-1",
                user_id="user-1",
                context={"task_id": "task-123"},
            )

        assert response.response == "final answer"
        assert captured["checkpointer"] is fake_checkpointer
        assert captured["config"]["configurable"]["thread_id"] == "task-123"
        assert captured["config"]["configurable"]["checkpoint_ns"] == "agent_turn"
        assert mock_persist_checkpoint_metadata.await_args.kwargs["task_id"] == "task-123"
        assert mock_persist_checkpoint_metadata.await_args.kwargs["graph_thread_id"] == "task-123"
        assert (
            mock_persist_checkpoint_metadata.await_args.kwargs["checkpointer"] is fake_checkpointer
        )

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_includes_memory_prompt_and_repo_url_for_instance_scope(
        self, mock_create_mini_llm, mock_create_llm
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        instance = RedisInstance(
            id="redis-prod-checkout-cache",
            name="checkout-cache-prod",
            connection_url="redis://localhost:6379",
            environment="production",
            usage="cache",
            description="Checkout cache",
            instance_type="oss_single",
            repo_url="https://github.com/acme/checkout-service",
        )
        agent = ChatAgent(redis_instance=instance)

        prepared_memory = PreparedAgentTurnMemory(
            memory_service=MagicMock(),
            memory_context=TurnMemoryContext(
                system_prompt="Memory reminder",
                user_working_memory=None,
                asset_working_memory=None,
            ),
            session_id="test-session",
            user_id="test-user",
            query="Inspect checkout cache",
            instance_id=instance.id,
            cluster_id=None,
            emitter=None,
        )
        prepared_memory.persist_response_fail_open = AsyncMock()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="instance answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.prepare_agent_turn_memory",
                AsyncMock(return_value=prepared_memory),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.build_startup_knowledge_context",
                new=AsyncMock(return_value=""),
            ),
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Inspect checkout cache",
                session_id="test-session",
                user_id="test-user",
            )

        assert response.response == "instance answer"
        initial_messages = fake_app.ainvoke.await_args.args[0]["messages"]
        assert str(initial_messages[1].content) == "Memory reminder"
        human_message = initial_messages[-1]
        assert "INSTANCE CONTEXT" in str(human_message.content)
        assert "Repository URL: https://github.com/acme/checkout-service" in str(
            human_message.content
        )

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_skips_memory_persist_for_generic_fallback(
        self, mock_create_mini_llm, mock_create_llm
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        prepared_memory = PreparedAgentTurnMemory(
            memory_service=MagicMock(),
            memory_context=TurnMemoryContext(
                system_prompt=None,
                user_working_memory=None,
                asset_working_memory=None,
            ),
            session_id="test-session",
            user_id=None,
            query="Who runs AOP?",
            instance_id=None,
            cluster_id=None,
            emitter=None,
        )
        prepared_memory.persist_response_fail_open = AsyncMock()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.prepare_agent_turn_memory",
                AsyncMock(return_value=prepared_memory),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.build_startup_knowledge_context",
                new=AsyncMock(return_value=""),
            ),
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Who runs AOP?",
                session_id="test-session",
                user_id=None,
            )

        assert response.response == "I couldn't process that query. Please try rephrasing."
        prepared_memory.persist_response_fail_open.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_surfaces_blank_exception_types(
        self, mock_create_mini_llm, mock_create_llm
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        prepared_memory = PreparedAgentTurnMemory(
            memory_service=MagicMock(),
            memory_context=TurnMemoryContext(
                system_prompt=None,
                user_working_memory=None,
                asset_working_memory=None,
            ),
            session_id="test-session",
            user_id=None,
            query="Who runs AOP?",
            instance_id=None,
            cluster_id=None,
            emitter=None,
        )
        prepared_memory.persist_response_fail_open = AsyncMock()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1
        fake_checkpointer = MagicMock()

        @asynccontextmanager
        async def fake_open_graph_checkpointer(**_kwargs):
            yield fake_checkpointer

        class _FailingApp:
            async def ainvoke(self, *_args, **_kwargs):
                raise NotImplementedError

        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = _FailingApp()

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.prepare_agent_turn_memory",
                AsyncMock(return_value=prepared_memory),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.build_startup_knowledge_context",
                new=AsyncMock(return_value=""),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.open_graph_checkpointer",
                side_effect=fake_open_graph_checkpointer,
            ),
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Who runs AOP?",
                session_id="test-session",
                user_id=None,
            )

        assert response.response == "Error processing query: NotImplementedError"
        prepared_memory.persist_response_fail_open.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_resume_query_surfaces_blank_exception_types(
        self, mock_create_mini_llm, mock_create_llm
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1
        fake_checkpointer = MagicMock()

        @asynccontextmanager
        async def fake_open_graph_checkpointer(**_kwargs):
            yield fake_checkpointer

        class _FailingApp:
            async def ainvoke(self, *_args, **_kwargs):
                raise NotImplementedError

        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = _FailingApp()

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.open_graph_checkpointer",
                side_effect=fake_open_graph_checkpointer,
            ),
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.resume_query(
                session_id="session-1",
                user_id="user-1",
                context={"task_id": "task-123"},
                resume_payload={"decision": "approved"},
            )

        assert response.response == "Error resuming query: NotImplementedError"

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_includes_attached_target_scope_context(
        self, mock_create_mini_llm, mock_create_llm, mock_build_startup_context
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.return_value = "Pinned documents:\n- Acronyms"

        agent = ChatAgent()

        mock_tool = MagicMock()
        mock_tool.name = "knowledge_test_skills_check"

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = [mock_tool]
        mock_tool_manager.get_toolset_generation.return_value = 3

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="comparison answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        checkout = RedisInstance(
            id="redis-prod-checkout-cache",
            name="checkout-cache-prod",
            connection_url="redis://localhost:6379",
            environment="production",
            usage="cache",
            description="Checkout cache",
            instance_type="oss_single",
        )
        session = RedisInstance(
            id="redis-stage-session-cache",
            name="session-cache-stage",
            connection_url="redis://localhost:6380",
            environment="staging",
            usage="session",
            description="Session cache",
            instance_type="oss_single",
        )
        context = {
            "attached_target_handles": ["tgt_01", "tgt_02"],
            "target_bindings": [
                {
                    "target_handle": "tgt_01",
                    "target_kind": "instance",
                    "resource_id": "redis-prod-checkout-cache",
                    "display_name": "checkout-cache-prod",
                    "capabilities": ["redis", "diagnostics"],
                },
                {
                    "target_handle": "tgt_02",
                    "target_kind": "instance",
                    "resource_id": "redis-stage-session-cache",
                    "display_name": "session-cache-stage",
                    "capabilities": ["redis", "diagnostics"],
                },
            ],
        }

        async def _get_instance(instance_id: str):
            return {
                "redis-prod-checkout-cache": checkout,
                "redis-stage-session-cache": session,
            }.get(instance_id)

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ) as mock_tool_manager_class,
            patch(
                "redis_sre_agent.agent.helpers.build_adapters_for_tooldefs",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "redis_sre_agent.core.targets.get_instance_by_id",
                new=AsyncMock(side_effect=_get_instance),
            ),
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Compare these attached caches",
                session_id="test-session",
                user_id="test-user",
                context=context,
            )

        assert response.response == "comparison answer"

        initial_state = fake_app.ainvoke.await_args.args[0]
        human_message = initial_state["messages"][-1]
        assert "ATTACHED TARGET SCOPE" in str(human_message.content)
        assert "checkout-cache-prod" in str(human_message.content)
        assert "session-cache-stage" in str(human_message.content)
        assert "MULTI-TARGET REQUIREMENT" in str(human_message.content)
        assert len(mock_tool_manager_class.call_args.kwargs["initial_target_bindings"]) == 2
        assert mock_tool_manager_class.call_args.kwargs["initial_toolset_generation"] == 0

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_includes_single_attached_target_context_fallback(
        self, mock_create_mini_llm, mock_create_llm, mock_build_startup_context
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.return_value = "Pinned documents:\n- Acronyms"

        agent = ChatAgent()
        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="single target answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        instance = RedisInstance(
            id="redis-prod-checkout-cache",
            name="checkout-cache-prod",
            connection_url="redis://localhost:6379",
            environment="production",
            usage="cache",
            description="Checkout cache",
            instance_type="oss_single",
        )
        context = {
            "attached_target_handles": ["tgt_01"],
            "target_bindings": [
                {
                    "target_handle": "tgt_01",
                    "target_kind": "instance",
                    "resource_id": "redis-prod-checkout-cache",
                    "display_name": "checkout-cache-prod",
                    "capabilities": ["redis", "diagnostics"],
                }
            ],
        }

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ),
            patch(
                "redis_sre_agent.agent.helpers.build_adapters_for_tooldefs",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "redis_sre_agent.core.targets.get_instance_by_id",
                new=AsyncMock(return_value=instance),
            ),
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Inspect the attached cache",
                session_id="test-session",
                user_id="test-user",
                context=context,
            )

        assert response.response == "single target answer"
        human_message = fake_app.ainvoke.await_args.args[0]["messages"][-1]
        assert "ATTACHED TARGET SCOPE" in str(human_message.content)
        assert "Use the target-scoped tools for the attached handle above" in str(
            human_message.content
        )

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_prefers_attached_target_prompt_over_bound_instance(
        self, mock_create_mini_llm, mock_create_llm, mock_build_startup_context
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.return_value = ""

        instance = RedisInstance(
            id="redis-prod-checkout-cache",
            name="checkout-cache-prod",
            connection_url="redis://localhost:6379",
            environment="production",
            usage="cache",
            description="Checkout cache",
            instance_type="oss_single",
            repo_url="https://github.com/acme/checkout-service",
        )
        agent = ChatAgent(redis_instance=instance)

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="bound instance answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        context = {
            "attached_target_handles": ["tgt_01"],
            "target_bindings": [
                {
                    "target_handle": "tgt_01",
                    "target_kind": "instance",
                    "resource_id": "redis-prod-checkout-cache",
                    "display_name": "checkout-cache-prod",
                    "capabilities": ["redis", "diagnostics"],
                }
            ],
        }

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ) as mock_tool_manager_class,
            patch(
                "redis_sre_agent.agent.helpers.build_adapters_for_tooldefs",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.build_attached_target_scope_prompt",
                new=AsyncMock(return_value="ATTACHED TARGET SCOPE"),
            ) as mock_prompt_builder,
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Inspect the primary cache",
                session_id="test-session",
                user_id="test-user",
                context=context,
                conversation_history=[HumanMessage(content="Previous question")],
            )

        assert response.response == "bound instance answer"
        mock_prompt_builder.assert_awaited_once()
        human_message = fake_app.ainvoke.await_args.args[0]["messages"][-1]
        assert "ATTACHED TARGET SCOPE" in str(human_message.content)
        assert "INSTANCE CONTEXT" not in str(human_message.content)
        assert mock_tool_manager_class.call_args.kwargs["redis_instance"] is None
        assert mock_tool_manager_class.call_args.kwargs["redis_cluster"] is None

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_uses_prompt_fallback_for_unbound_single_attached_handle(
        self, mock_create_mini_llm, mock_create_llm, mock_build_startup_context
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.return_value = ""

        agent = ChatAgent()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="unbound attached answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ),
            patch(
                "redis_sre_agent.agent.helpers.build_adapters_for_tooldefs",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.build_attached_target_scope_prompt",
                new=AsyncMock(return_value="ATTACHED TARGET SCOPE"),
            ) as mock_prompt_builder,
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Inspect the attached target",
                session_id="test-session",
                user_id="test-user",
                context={"attached_target_handles": ["tgt_01"]},
            )

        assert response.response == "unbound attached answer"
        mock_prompt_builder.assert_awaited_once()
        human_message = fake_app.ainvoke.await_args.args[0]["messages"][-1]
        assert "ATTACHED TARGET SCOPE" in str(human_message.content)
        assert "User Query: Inspect the attached target" in str(human_message.content)

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_uses_single_binding_scope_when_prompt_builder_returns_none(
        self, mock_create_mini_llm, mock_create_llm, mock_build_startup_context
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.return_value = ""

        agent = ChatAgent()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="single binding fallback answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        context = {
            "attached_target_handles": ["tgt_01"],
            "target_bindings": [
                {
                    "target_handle": "tgt_01",
                    "target_kind": "instance",
                    "resource_id": "redis-prod-1",
                    "display_name": "Prod Cache",
                    "capabilities": ["redis"],
                }
            ],
        }

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ) as mock_tool_manager_class,
            patch(
                "redis_sre_agent.agent.helpers.build_adapters_for_tooldefs",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.build_attached_target_scope_prompt",
                new=AsyncMock(return_value=None),
            ) as mock_prompt_builder,
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Inspect the attached target",
                session_id="test-session",
                user_id="test-user",
                context=context,
            )

        assert response.response == "single binding fallback answer"
        mock_prompt_builder.assert_awaited_once()
        human_message = fake_app.ainvoke.await_args.args[0]["messages"][-1]
        assert "ATTACHED TARGET SCOPE" in str(human_message.content)
        assert "Prod Cache" in str(human_message.content)
        assert "handle=tgt_01" in str(human_message.content)
        assert "resource_id=redis-prod-1" not in str(human_message.content)
        assert mock_tool_manager_class.call_args.kwargs["redis_instance"] is None
        assert mock_tool_manager_class.call_args.kwargs["redis_cluster"] is None

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_process_query_uses_multi_binding_scope_when_prompt_builder_returns_none(
        self, mock_create_mini_llm, mock_create_llm, mock_build_startup_context
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.return_value = ""

        agent = ChatAgent()

        mock_tool_manager = MagicMock()
        mock_tool_manager.__aenter__.return_value = mock_tool_manager
        mock_tool_manager.__aexit__.return_value = None
        mock_tool_manager.get_tools.return_value = []
        mock_tool_manager.get_toolset_generation.return_value = 1

        fake_app = AsyncMock()
        fake_app.ainvoke.return_value = {
            "messages": [AIMessage(content="multi binding fallback answer")],
            "signals_envelopes": [],
        }
        fake_workflow = MagicMock()
        fake_workflow.compile.return_value = fake_app

        context = {
            "attached_target_handles": ["tgt_01", "tgt_02"],
            "target_bindings": [
                {
                    "target_handle": "tgt_01",
                    "target_kind": "instance",
                    "resource_id": "redis-prod-1",
                    "display_name": "Prod Cache",
                    "capabilities": ["redis"],
                },
                {
                    "target_handle": "tgt_02",
                    "target_kind": "instance",
                    "resource_id": "redis-prod-2",
                    "display_name": "Prod Queue",
                    "capabilities": ["redis"],
                },
            ],
        }

        with (
            patch(
                "redis_sre_agent.agent.chat_agent.ToolManager",
                return_value=mock_tool_manager,
            ),
            patch(
                "redis_sre_agent.agent.helpers.build_adapters_for_tooldefs",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.build_attached_target_scope_prompt",
                new=AsyncMock(return_value=None),
            ) as mock_prompt_builder,
            patch.object(agent, "_build_workflow", return_value=fake_workflow),
        ):
            response = await agent.process_query(
                query="Compare the attached targets",
                session_id="test-session",
                user_id="test-user",
                context=context,
            )

        assert response.response == "multi binding fallback answer"
        mock_prompt_builder.assert_awaited_once()
        human_message = fake_app.ainvoke.await_args.args[0]["messages"][-1]
        assert "ATTACHED TARGET SCOPE" in str(human_message.content)
        assert "Prod Cache" in str(human_message.content)
        assert "Prod Queue" in str(human_message.content)
        assert "MULTI-TARGET REQUIREMENT" in str(human_message.content)
        assert "User Query: Compare the attached targets" in str(human_message.content)

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_agent_node_reinjects_startup_context_for_follow_ups(
        self, mock_create_mini_llm, mock_create_llm, mock_build_startup_context
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        agent = ChatAgent()
        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_toolset_generation.return_value = 1
        workflow = agent._build_workflow(
            tool_mgr=mock_tool_mgr,
            emitter=None,
        )
        compiled = workflow.compile()

        state = {
            "messages": [
                HumanMessage(content="first question"),
                AIMessage(content="first answer"),
                HumanMessage(content="follow-up question"),
            ],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
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
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_agent_node_does_not_persist_injected_system_message(
        self, mock_create_mini_llm, mock_create_llm, mock_build_startup_context
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.return_value = "STARTUP_CONTEXT"

        agent = ChatAgent()
        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_toolset_generation.return_value = 1
        workflow = agent._build_workflow(
            tool_mgr=mock_tool_mgr,
            emitter=None,
        )
        compiled = workflow.compile()

        input_state = {
            "messages": [
                HumanMessage(content="first question"),
                AIMessage(content="first answer"),
                HumanMessage(content="follow-up question"),
            ],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
            "signals_envelopes": [],
        }

        output_state = await compiled.nodes["agent"].ainvoke(input_state)

        assert isinstance(mock_llm.ainvoke.call_args.args[0][0], SystemMessage)
        assert isinstance(output_state["messages"][0], HumanMessage)
        assert all(not isinstance(msg, SystemMessage) for msg in output_state["messages"])

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_startup_context_not_shared_between_independent_invocations(
        self, mock_create_mini_llm, mock_create_llm, mock_build_startup_context
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.side_effect = ["CTX_ONE", "CTX_TWO"]

        agent = ChatAgent()
        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_toolset_generation.return_value = 1
        workflow = agent._build_workflow(
            tool_mgr=mock_tool_mgr,
            emitter=None,
        )
        compiled = workflow.compile()

        state_one = {
            "messages": [HumanMessage(content="first question")],
            "session_id": "session-1",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
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
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_agent_node_rebuilds_prompt_on_first_step_when_cached_prompt_is_stale(
        self, mock_create_mini_llm, mock_create_llm, mock_build_startup_context
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.return_value = "FRESH_CONTEXT"

        agent = ChatAgent()
        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_toolset_generation.return_value = 1
        workflow = agent._build_workflow(
            tool_mgr=mock_tool_mgr,
            emitter=None,
        )
        compiled = workflow.compile()

        state = {
            "messages": [HumanMessage(content="new question")],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": "STALE_CONTEXT",
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state)

        sent_messages = mock_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)
        assert "FRESH_CONTEXT" in sent_messages[0].content
        assert "STALE_CONTEXT" not in sent_messages[0].content
        mock_build_startup_context.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_agent_node_reuses_initialized_prompt_without_rebuild(
        self, mock_create_mini_llm, mock_create_llm, mock_build_startup_context
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()
        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_toolset_generation.return_value = 1
        workflow = agent._build_workflow(
            tool_mgr=mock_tool_mgr,
            emitter=None,
        )
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
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(state)

        sent_messages = mock_llm.ainvoke.call_args.args[0]
        assert isinstance(sent_messages[0], SystemMessage)

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.helpers.build_adapters_for_tooldefs", new_callable=AsyncMock)
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_agent_node_rebinds_tools_when_toolset_generation_changes(
        self,
        mock_create_mini_llm,
        mock_create_llm,
        mock_build_startup_context,
        mock_build_adapters,
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok", tool_calls=[]))
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.return_value = "CTX"
        mock_build_adapters.return_value = []

        agent = ChatAgent()
        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.side_effect = [[], []]
        mock_tool_mgr.get_toolset_generation.side_effect = [1, 2]
        workflow = agent._build_workflow(tool_mgr=mock_tool_mgr, emitter=None)
        compiled = workflow.compile()

        first_state = {
            "messages": [HumanMessage(content="first question")],
            "session_id": "session-1",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
            "signals_envelopes": [],
        }
        second_state = {
            "messages": [HumanMessage(content="second question")],
            "session_id": "session-1",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
            "signals_envelopes": [],
        }

        await compiled.nodes["agent"].ainvoke(first_state)
        await compiled.nodes["agent"].ainvoke(second_state)

        assert mock_llm.bind_tools.call_count == 2

    @pytest.mark.asyncio
    @patch("redis_sre_agent.agent.helpers.build_adapters_for_tooldefs", new_callable=AsyncMock)
    @patch("redis_sre_agent.agent.chat_agent.build_startup_knowledge_context")
    @patch(
        "redis_sre_agent.agent.chat_agent.execute_tool_calls_with_gate",
        new_callable=AsyncMock,
    )
    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    async def test_tool_node_uses_agent_generation_when_toolset_changes_mid_turn(
        self,
        mock_create_mini_llm,
        mock_create_llm,
        mock_execute_tool_calls,
        mock_build_startup_context,
        mock_build_adapters,
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="calling tool",
                tool_calls=[{"id": "call-1", "name": "demo", "args": {}}],
            )
        )
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        mock_build_startup_context.return_value = "CTX"
        mock_build_adapters.return_value = []
        mock_execute_tool_calls.return_value = [
            ToolMessage(content="ok", tool_call_id="call-1", name="demo")
        ]

        agent = ChatAgent()
        mock_tool_mgr = MagicMock()
        mock_tool_mgr.get_tools.return_value = []
        mock_tool_mgr.get_toolset_generation.side_effect = [1, 2]
        workflow = agent._build_workflow(tool_mgr=mock_tool_mgr, emitter=None)
        compiled = workflow.compile()

        first_state = {
            "messages": [HumanMessage(content="first question")],
            "session_id": "session-1",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "startup_system_prompt": None,
            "signals_envelopes": [],
        }

        agent_state = await compiled.nodes["agent"].ainvoke(first_state)
        tool_state = await compiled.nodes["tools"].ainvoke(agent_state)

        assert agent_state["toolset_generation"] == 1
        mock_execute_tool_calls.assert_awaited_once()
        local_tools = mock_execute_tool_calls.await_args.kwargs["local_tools"]
        assert "expand_evidence" in local_tools
        assert callable(local_tools["expand_evidence"])
        assert mock_execute_tool_calls.await_args.kwargs["tool_manager"] is mock_tool_mgr
        assert mock_execute_tool_calls.await_args.kwargs["tool_calls"] == [
            {"id": "call-1", "name": "demo", "args": {}, "type": "tool_call"}
        ]
        local_tools = mock_execute_tool_calls.await_args.kwargs["local_tools"]
        assert list(local_tools.keys()) == ["expand_evidence"]
        assert callable(local_tools["expand_evidence"])
        assert tool_state["toolset_generation"] == 1

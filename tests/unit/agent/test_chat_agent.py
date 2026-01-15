"""Unit tests for the lightweight Chat Agent."""

from unittest.mock import MagicMock, patch

from redis_sre_agent.agent.chat_agent import (
    CHAT_SYSTEM_PROMPT,
    ChatAgent,
    ChatAgentState,
    get_chat_agent,
)
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
            mock_agent_class.assert_called_once_with(redis_instance=None)

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
            "signals_envelopes": [],
        }

        assert "messages" in state
        assert "session_id" in state
        assert "user_id" in state
        assert "current_tool_calls" in state
        assert "iteration_count" in state
        assert "max_iterations" in state
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

        # Create a mock emitter
        emitter = NullEmitter()

        # Should not raise - emitter is now accepted
        workflow = agent._build_workflow(
            tool_mgr=mock_tool_mgr,
            llm_with_tools=mock_llm,
            adapters=[],
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

        # Should not raise when emitter is None
        workflow = agent._build_workflow(
            tool_mgr=mock_tool_mgr,
            llm_with_tools=mock_llm,
            adapters=[],
            emitter=None,
        )

        assert workflow is not None


class TestChatAgentExpandEvidenceTool:
    """Test the _build_expand_evidence_tool method."""

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

        tool_def = agent._build_expand_evidence_tool(envelopes)

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

        tool_def = agent._build_expand_evidence_tool(envelopes)
        expand_fn = tool_def["func"]

        # Test retrieving unknown key
        result = expand_fn("unknown_key")
        assert result["status"] == "error"
        assert "Unknown tool_key" in result["error"]

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_expand_evidence_tool_empty_envelopes(self, mock_create_mini_llm, mock_create_llm):
        """Test expand_evidence tool with empty envelopes."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        agent = ChatAgent()

        tool_def = agent._build_expand_evidence_tool([])
        expand_fn = tool_def["func"]

        result = expand_fn("any_key")
        assert result["status"] == "error"


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

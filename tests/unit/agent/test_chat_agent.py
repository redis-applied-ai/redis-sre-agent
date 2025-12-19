"""Unit tests for the lightweight Chat Agent."""

from unittest.mock import MagicMock, patch

from redis_sre_agent.agent.chat_agent import (
    CHAT_SYSTEM_PROMPT,
    ChatAgent,
    ChatAgentState,
    get_chat_agent,
)
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.core.progress import (
    CallbackEmitter,
    NullEmitter,
)


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
    def test_agent_initializes_with_progress_callback_deprecated(self, mock_create_mini_llm, mock_create_llm):
        """Test that ChatAgent still accepts deprecated progress_callback."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        async def my_callback(msg, type):
            pass

        agent = ChatAgent(progress_callback=my_callback)

        # Should wrap callback in CallbackEmitter
        assert isinstance(agent._emitter, CallbackEmitter)

    @patch("redis_sre_agent.agent.chat_agent.create_llm")
    @patch("redis_sre_agent.agent.chat_agent.create_mini_llm")
    def test_progress_emitter_takes_precedence_over_callback(self, mock_create_mini_llm, mock_create_llm):
        """Test that progress_emitter takes precedence over progress_callback."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm

        emitter = NullEmitter()

        async def my_callback(msg, type):
            pass

        agent = ChatAgent(progress_emitter=emitter, progress_callback=my_callback)

        # Should use the emitter, not the callback
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
        assert "quick" in CHAT_SYSTEM_PROMPT.lower() or "fast" in CHAT_SYSTEM_PROMPT.lower()
        # Should mention full triage as alternative
        assert "triage" in CHAT_SYSTEM_PROMPT.lower()

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

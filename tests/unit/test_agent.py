"""Unit tests for SRE LangGraph Agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    with patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI") as mock_chat:
        mock_llm = MagicMock()
        mock_chat.return_value = mock_llm
        yield mock_llm


@pytest.fixture
def mock_sre_tasks():
    """Mock SRE tasks for testing."""
    mocks = {}
    with patch("redis_sre_agent.agent.langgraph_agent.analyze_system_metrics") as mock_analyze:
        mocks["analyze_system_metrics"] = mock_analyze
        mock_analyze.return_value = {"task_id": "test-123", "status": "completed"}

        with patch("redis_sre_agent.agent.langgraph_agent.search_runbook_knowledge") as mock_search:
            mocks["search_runbook_knowledge"] = mock_search
            mock_search.return_value = {"results": [], "results_count": 0}

            with patch("redis_sre_agent.agent.langgraph_agent.check_service_health") as mock_health:
                mocks["check_service_health"] = mock_health
                mock_health.return_value = {"overall_status": "healthy", "endpoints_checked": 1}

                with patch(
                    "redis_sre_agent.agent.langgraph_agent.ingest_sre_document"
                ) as mock_ingest:
                    mocks["ingest_sre_document"] = mock_ingest
                    mock_ingest.return_value = {"status": "ingested", "document_id": "doc-456"}

                    yield mocks


class TestSRELangGraphAgent:
    """Test cases for SRE LangGraph Agent."""

    def test_init(self, mock_settings, mock_llm):
        """Test agent initialization."""
        agent = SRELangGraphAgent()

        assert agent.settings == mock_settings
        assert agent.llm is not None
        assert agent.llm_with_tools is not None
        assert len(agent.sre_tools) == 4
        assert "analyze_system_metrics" in agent.sre_tools
        assert "search_runbook_knowledge" in agent.sre_tools
        assert "check_service_health" in agent.sre_tools
        assert "ingest_sre_document" in agent.sre_tools

    def test_tool_mapping(self, mock_settings, mock_llm):
        """Test that SRE tools are properly mapped."""
        agent = SRELangGraphAgent()

        expected_tools = [
            "analyze_system_metrics",
            "search_runbook_knowledge",
            "check_service_health",
            "ingest_sre_document",
        ]

        assert set(agent.sre_tools.keys()) == set(expected_tools)

    @pytest.mark.asyncio
    async def test_process_query_simple(self, mock_settings, mock_llm):
        """Test processing a simple query without tool calls."""
        # Mock LLM response without tool calls
        mock_response = MagicMock()
        mock_response.content = "This is a simple response to your SRE question."
        mock_response.tool_calls = None

        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.invoke = AsyncMock(return_value=mock_response)

        with patch.object(SRELangGraphAgent, "__init__", lambda self: None):
            agent = SRELangGraphAgent()
            agent.settings = mock_settings
            agent.llm = mock_llm
            agent.llm_with_tools = mock_llm_with_tools
            agent.sre_tools = {}

            # Mock the workflow and app
            mock_app = AsyncMock()
            mock_app.ainvoke = AsyncMock(
                return_value={"messages": [mock_response], "iteration_count": 1}
            )
            agent.app = mock_app

            result = await agent.process_query(
                query="What is Redis?", session_id="test-session", user_id="test-user"
            )

            assert result == "This is a simple response to your SRE question."

    @pytest.mark.asyncio
    async def test_process_query_with_error(self, mock_settings, mock_llm):
        """Test error handling in query processing."""
        with patch.object(SRELangGraphAgent, "__init__", lambda self: None):
            agent = SRELangGraphAgent()
            agent.settings = mock_settings

            # Mock app to raise exception
            mock_app = AsyncMock()
            mock_app.ainvoke = AsyncMock(side_effect=Exception("Test error"))
            agent.app = mock_app

            result = await agent.process_query(
                query="Test query", session_id="test-session", user_id="test-user"
            )

            assert "I encountered an error" in result
            assert "Test error" in result

    @pytest.mark.asyncio
    async def test_get_conversation_history(self, mock_settings, mock_llm):
        """Test retrieving conversation history."""
        with patch.object(SRELangGraphAgent, "__init__", lambda self: None):
            agent = SRELangGraphAgent()

            # Mock app state
            mock_state = MagicMock()
            mock_state.values = {
                "messages": [
                    MagicMock(content="Hello", __class__=MagicMock(__name__="HumanMessage")),
                    MagicMock(content="Hi there!", __class__=MagicMock(__name__="AIMessage")),
                ]
            }

            mock_app = AsyncMock()
            mock_app.aget_state = AsyncMock(return_value=mock_state)
            agent.app = mock_app

            # Mock message type checking
            from langchain_core.messages import AIMessage, HumanMessage

            mock_state.values["messages"][0].__class__ = HumanMessage
            mock_state.values["messages"][1].__class__ = AIMessage

            with patch("redis_sre_agent.agent.langgraph_agent.HumanMessage", HumanMessage):
                with patch("redis_sre_agent.agent.langgraph_agent.AIMessage", AIMessage):
                    history = await agent.get_conversation_history("test-session")

                    assert len(history) == 2
                    assert history[0]["role"] == "user"
                    assert history[0]["content"] == "Hello"
                    assert history[1]["role"] == "assistant"
                    assert history[1]["content"] == "Hi there!"

    def test_clear_conversation(self, mock_settings, mock_llm):
        """Test clearing conversation history."""
        with patch.object(SRELangGraphAgent, "__init__", lambda self: None):
            agent = SRELangGraphAgent()

            result = agent.clear_conversation("test-session")

            # For now, this always returns True
            assert result is True


class TestAgentSingleton:
    """Test agent singleton behavior."""

    def test_get_sre_agent_singleton(self):
        """Test that get_sre_agent returns same instance."""
        with patch("redis_sre_agent.agent.langgraph_agent.SRELangGraphAgent") as mock_agent_class:
            mock_instance = MagicMock()
            mock_agent_class.return_value = mock_instance

            # Clear any existing singleton
            import redis_sre_agent.agent.langgraph_agent

            redis_sre_agent.agent.langgraph_agent._sre_agent = None

            agent1 = get_sre_agent()
            agent2 = get_sre_agent()

            assert agent1 is agent2
            mock_agent_class.assert_called_once()


class TestAgentToolBindings:
    """Test agent tool bindings and schemas."""

    def test_tool_schemas(self, mock_settings, mock_llm):
        """Test that tool schemas are properly defined."""
        agent = SRELangGraphAgent()

        # The agent should have bound tools to the LLM
        assert hasattr(agent, "llm_with_tools")

        # Verify that bind_tools was called with proper tool definitions
        mock_llm.bind_tools.assert_called_once()

        # Get the tool definitions that were passed
        tool_definitions = mock_llm.bind_tools.call_args[0][0]

        assert len(tool_definitions) == 4

        # Check that all expected tools are defined
        tool_names = [tool["function"]["name"] for tool in tool_definitions]
        expected_names = [
            "analyze_system_metrics",
            "search_runbook_knowledge",
            "check_service_health",
            "ingest_sre_document",
        ]

        assert set(tool_names) == set(expected_names)

        # Verify tool parameters are properly structured
        for tool in tool_definitions:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]


@pytest.mark.asyncio
class TestAgentWorkflow:
    """Test the LangGraph workflow construction and execution."""

    async def test_workflow_construction(self, mock_settings, mock_llm):
        """Test that the workflow is properly constructed."""
        agent = SRELangGraphAgent()

        assert agent.workflow is not None
        assert agent.app is not None
        assert agent.memory is not None

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
        ]

        # AgentState is a TypedDict, so we can check __annotations__
        assert set(AgentState.__annotations__.keys()) == set(required_fields)

    async def test_sre_tool_call_model(self):
        """Test SREToolCall model validation."""
        from redis_sre_agent.agent.langgraph_agent import SREToolCall

        # Test valid tool call
        tool_call = SREToolCall(
            tool_name="analyze_system_metrics",
            arguments={"metric_query": "cpu_usage", "time_range": "1h"},
        )

        assert tool_call.tool_name == "analyze_system_metrics"
        assert tool_call.arguments["metric_query"] == "cpu_usage"
        assert tool_call.tool_call_id is not None  # Should be auto-generated

        # Test that tool_call_id is a valid UUID string
        import uuid

        uuid.UUID(tool_call.tool_call_id)  # Should not raise exception

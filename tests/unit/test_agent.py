"""Unit tests for SRE LangGraph Agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

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
            "instance_context",  # Added in the new implementation
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

    async def test_safety_evaluator_handles_errors_gracefully(self, mock_settings, mock_llm):
        """Test safety evaluator handles errors gracefully and returns safe fallback."""
        agent = SRELangGraphAgent()

        # Mock LLM that returns unparseable content
        mock_response = MagicMock()
        mock_response.content = "unparseable content"

        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        agent.llm = mock_llm

        result = await agent._safety_evaluate_response("test query", "test response")

        # Should return safe=False for JSON parsing errors, indicating manual review needed
        assert result["safe"] is False
        assert len(result["violations"]) > 0
        # Verify LLM was called (retry mechanism should work)
        assert mock_llm.ainvoke.call_count >= 1

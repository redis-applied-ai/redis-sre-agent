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
    with patch("redis_sre_agent.agent.langgraph_agent.analyze_system_metrics") as mock_analyze:
        mocks["analyze_system_metrics"] = mock_analyze
        mock_analyze.return_value = {"task_id": "test-123", "status": "completed"}

        with patch("redis_sre_agent.agent.langgraph_agent.search_knowledge_base") as mock_search:
            mocks["search_knowledge_base"] = mock_search
            mock_search.return_value = {"results": [], "results_count": 0}

            with patch("redis_sre_agent.agent.langgraph_agent.check_service_health") as mock_health:
                mocks["check_service_health"] = mock_health
                mock_health.return_value = {"overall_status": "healthy", "endpoints_checked": 1}

                with patch(
                    "redis_sre_agent.agent.langgraph_agent.ingest_sre_document"
                ) as mock_ingest:
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
        assert len(agent.sre_tools) == 13  # Protocol tools + knowledge tools + enterprise tools
        assert "query_instance_metrics" in agent.sre_tools
        assert "list_available_metrics" in agent.sre_tools
        assert "search_logs" in agent.sre_tools
        assert "create_incident_ticket" in agent.sre_tools
        assert "search_related_repositories" in agent.sre_tools
        assert "get_provider_status" in agent.sre_tools
        assert "search_knowledge_base" in agent.sre_tools
        assert "ingest_sre_document" in agent.sre_tools

    def test_tool_mapping(self, mock_settings, mock_llm):
        """Test that SRE tools are properly mapped."""
        agent = SRELangGraphAgent()

        expected_tools = [
            "query_instance_metrics",
            "list_available_metrics",
            "search_logs",
            "create_incident_ticket",
            "search_related_repositories",
            "get_provider_status",
            "search_knowledge_base",
            "ingest_sre_document",
            "get_all_document_fragments",
            "get_related_document_fragments",
            "get_redis_enterprise_cluster_status",
            "get_redis_enterprise_node_status",
            "get_redis_enterprise_database_status",
        ]

        assert set(agent.sre_tools.keys()) == set(expected_tools)

    @pytest.mark.asyncio
    async def test_process_query_simple(self, mock_settings, mock_llm):
        """Test processing a simple query without tool calls."""
        # Mock LLM response without tool calls
        mock_response = AIMessage(content="This is a simple response to your SRE question.")

        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.invoke = AsyncMock(return_value=mock_response)

        with patch.object(SRELangGraphAgent, "__init__", lambda self: None):
            agent = SRELangGraphAgent()
            agent.settings = mock_settings
            agent.llm = mock_llm
            agent.llm_with_tools = mock_llm_with_tools
            agent.sre_tools = {}

            # Mock the workflow and app
            mock_workflow = MagicMock()
            mock_app = AsyncMock()
            mock_app.ainvoke = AsyncMock(
                return_value={"messages": [mock_response], "iteration_count": 1}
            )
            mock_workflow.compile = MagicMock(return_value=mock_app)
            agent.workflow = mock_workflow

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

            # Mock workflow and app to raise exception
            mock_workflow = MagicMock()
            mock_app = AsyncMock()
            mock_app.ainvoke = AsyncMock(side_effect=Exception("Test error"))
            mock_workflow.compile = MagicMock(return_value=mock_app)
            agent.workflow = mock_workflow

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
        """Test that tool schemas are properly defined."""
        agent = SRELangGraphAgent()

        # The agent should have bound tools to the LLM
        assert hasattr(agent, "llm_with_tools")

        # Verify that bind_tools was called with proper tool definitions
        mock_llm.bind_tools.assert_called_once()

        # Get the tool definitions that were passed
        tool_definitions = mock_llm.bind_tools.call_args[0][0]

        assert len(tool_definitions) == 13  # Protocol + knowledge + enterprise tools

        # Check that all expected tools are defined
        tool_names = [tool["function"]["name"] for tool in tool_definitions]
        expected_names = [
            "query_instance_metrics",
            "list_available_metrics",
            "search_logs",
            "create_incident_ticket",
            "search_related_repositories",
            "get_provider_status",
            "search_knowledge_base",
            "ingest_sre_document",
            "get_all_document_fragments",
            "get_related_document_fragments",
            "get_redis_enterprise_cluster_status",
            "get_redis_enterprise_node_status",
            "get_redis_enterprise_database_status",
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
            tool_name="analyze_system_metrics",
            arguments={"metric_query": "cpu_usage", "time_range": "1h"},
        )

        assert tool_call.tool_name == "analyze_system_metrics"
        assert tool_call.arguments["metric_query"] == "cpu_usage"
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

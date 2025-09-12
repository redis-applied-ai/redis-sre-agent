"""Unit tests for Agent API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_agent():
    """Mock SRE agent for testing."""
    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(return_value="Test response from SRE agent")
    mock_agent.get_conversation_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "Test question"},
            {"role": "assistant", "content": "Test answer"},
        ]
    )
    mock_agent.clear_conversation = MagicMock(return_value=True)
    mock_agent.sre_tools = {
        "analyze_system_metrics": MagicMock(),
        "search_knowledge_base": MagicMock(),
        "check_service_health": MagicMock(),
        "ingest_sre_document": MagicMock(),
    }

    return mock_agent


class TestAgentQueryEndpoint:
    """Test /api/v1/agent/query endpoint."""

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_query_success(self, mock_get_agent, client, mock_agent):
        """Test successful query processing."""
        mock_get_agent.return_value = mock_agent

        response = client.post(
            "/api/v1/agent/query",
            json={"query": "How is Redis performing?", "user_id": "test-user"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "response" in data
        assert "session_id" in data
        assert "user_id" in data
        assert data["user_id"] == "test-user"
        assert data["response"] == "Test response from SRE agent"

        # Verify agent was called correctly
        mock_agent.process_query.assert_called_once()
        call_args = mock_agent.process_query.call_args[1]
        assert call_args["query"] == "How is Redis performing?"
        assert call_args["user_id"] == "test-user"

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_query_with_session_id(self, mock_get_agent, client, mock_agent):
        """Test query with provided session ID."""
        mock_get_agent.return_value = mock_agent

        response = client.post(
            "/api/v1/agent/query",
            json={
                "query": "Check system health",
                "user_id": "test-user",
                "session_id": "existing-session-123",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == "existing-session-123"

        # Verify agent used the provided session ID
        call_args = mock_agent.process_query.call_args[1]
        assert call_args["session_id"] == "existing-session-123"

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_query_with_max_iterations(self, mock_get_agent, client, mock_agent):
        """Test query with custom max iterations."""
        mock_get_agent.return_value = mock_agent

        response = client.post(
            "/api/v1/agent/query",
            json={
                "query": "Analyze performance metrics",
                "user_id": "test-user",
                "max_iterations": 5,
            },
        )

        assert response.status_code == 200

        # Verify max_iterations was passed to agent
        call_args = mock_agent.process_query.call_args[1]
        assert call_args["max_iterations"] == 5

    def test_query_missing_fields(self, client):
        """Test query with missing required fields."""
        # Missing user_id
        response = client.post("/api/v1/agent/query", json={"query": "Test query"})

        assert response.status_code == 422  # Validation error

    def test_query_empty_query(self, client):
        """Test query with empty query string."""
        response = client.post(
            "/api/v1/agent/query",
            json={"query": "", "user_id": "test-user"},  # Empty query
        )

        assert response.status_code == 422  # Validation error

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_query_agent_error(self, mock_get_agent, client):
        """Test handling of agent processing errors."""
        mock_agent = MagicMock()
        mock_agent.process_query = AsyncMock(side_effect=Exception("Agent processing failed"))
        mock_get_agent.return_value = mock_agent

        response = client.post(
            "/api/v1/agent/query", json={"query": "Test query", "user_id": "test-user"}
        )

        assert response.status_code == 500
        data = response.json()
        assert "Error processing query" in data["detail"]


class TestAgentChatEndpoint:
    """Test /api/v1/agent/chat endpoint."""

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_chat_success(self, mock_get_agent, client, mock_agent):
        """Test successful chat message processing."""
        mock_get_agent.return_value = mock_agent

        response = client.post(
            "/api/v1/agent/chat",
            json={
                "message": "What's the current CPU usage?",
                "session_id": "chat-session-123",
                "user_id": "test-user",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["response"] == "Test response from SRE agent"
        assert data["session_id"] == "chat-session-123"
        assert data["user_id"] == "test-user"

        # Verify agent was called with chat message
        call_args = mock_agent.process_query.call_args[1]
        assert call_args["query"] == "What's the current CPU usage?"
        assert call_args["session_id"] == "chat-session-123"

    def test_chat_missing_session_id(self, client):
        """Test chat with missing session ID."""
        response = client.post(
            "/api/v1/agent/chat", json={"message": "Test message", "user_id": "test-user"}
        )

        assert response.status_code == 422  # Validation error


class TestConversationHistoryEndpoint:
    """Test /api/v1/agent/sessions/{session_id}/history endpoint."""

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_get_history_success(self, mock_get_agent, client, mock_agent):
        """Test successful conversation history retrieval."""
        mock_get_agent.return_value = mock_agent

        response = client.get("/api/v1/agent/sessions/test-session-456/history")

        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == "test-session-456"
        assert "messages" in data
        assert "total_messages" in data
        assert data["total_messages"] == 2

        messages = data["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Test question"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Test answer"

        # Verify agent was called correctly
        mock_agent.get_conversation_history.assert_called_once_with("test-session-456")

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_get_history_empty(self, mock_get_agent, client):
        """Test getting history for session with no messages."""
        mock_agent = MagicMock()
        mock_agent.get_conversation_history = AsyncMock(return_value=[])
        mock_get_agent.return_value = mock_agent

        response = client.get("/api/v1/agent/sessions/empty-session/history")

        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == "empty-session"
        assert data["total_messages"] == 0
        assert data["messages"] == []

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_get_history_error(self, mock_get_agent, client):
        """Test error handling in history retrieval."""
        mock_agent = MagicMock()
        mock_agent.get_conversation_history = AsyncMock(
            side_effect=Exception("History retrieval failed")
        )
        mock_get_agent.return_value = mock_agent

        response = client.get("/api/v1/agent/sessions/error-session/history")

        assert response.status_code == 500
        data = response.json()
        assert "Error retrieving conversation history" in data["detail"]


class TestClearConversationEndpoint:
    """Test DELETE /api/v1/agent/sessions/{session_id} endpoint."""

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_clear_success(self, mock_get_agent, client, mock_agent):
        """Test successful conversation clearing."""
        mock_get_agent.return_value = mock_agent

        response = client.delete("/api/v1/agent/sessions/clear-session-789")

        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == "clear-session-789"
        assert data["cleared"] is True
        assert "successfully" in data["message"]

        # Verify agent clear method was called
        mock_agent.clear_conversation.assert_called_once_with("clear-session-789")

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_clear_failure(self, mock_get_agent, client):
        """Test conversation clearing failure."""
        mock_agent = MagicMock()
        mock_agent.clear_conversation = MagicMock(return_value=False)
        mock_get_agent.return_value = mock_agent

        response = client.delete("/api/v1/agent/sessions/fail-session")

        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == "fail-session"
        assert data["cleared"] is False
        assert "Failed to clear" in data["message"]


class TestAgentStatusEndpoint:
    """Test /api/v1/agent/status endpoint."""

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_status_success(self, mock_get_agent, client, mock_agent):
        """Test successful agent status check."""
        mock_get_agent.return_value = mock_agent

        response = client.get("/api/v1/agent/status")

        assert response.status_code == 200
        data = response.json()

        assert data["agent_available"] is True
        assert data["tools_registered"] == 4
        assert set(data["tool_names"]) == {
            "analyze_system_metrics",
            "search_knowledge_base",
            "check_service_health",
            "ingest_sre_document",
        }
        assert data["model"] == "gpt-4o-mini"
        assert data["status"] == "operational"
        assert "system_health" in data

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_status_agent_error(self, mock_get_agent, client):
        """Test status when agent initialization fails."""
        mock_get_agent.side_effect = Exception("Agent initialization failed")

        response = client.get("/api/v1/agent/status")

        assert response.status_code == 200  # Should not fail HTTP request
        data = response.json()

        assert data["agent_available"] is False
        assert "Agent initialization failed" in data["error"]
        assert data["status"] == "error"


class TestAgentAPIValidation:
    """Test API request validation."""

    def test_query_validation_max_iterations(self, client):
        """Test max_iterations validation."""
        # Too high
        response = client.post(
            "/api/v1/agent/query",
            json={
                "query": "Test",
                "user_id": "test-user",
                "max_iterations": 30,  # Above limit of 25
            },
        )
        assert response.status_code == 422

        # Too low
        response = client.post(
            "/api/v1/agent/query",
            json={"query": "Test", "user_id": "test-user", "max_iterations": 0},  # Below limit of 1
        )
        assert response.status_code == 422

    def test_chat_validation_empty_message(self, client):
        """Test chat message validation."""
        response = client.post(
            "/api/v1/agent/chat",
            json={
                "message": "",  # Empty message
                "session_id": "test-session",
                "user_id": "test-user",
            },
        )
        assert response.status_code == 422


class TestAgentAPIIntegration:
    """Integration tests for agent API endpoints."""

    @patch("redis_sre_agent.api.agent.get_sre_agent")
    def test_full_conversation_flow(self, mock_get_agent, client, mock_agent):
        """Test a complete conversation flow."""
        # Mock different responses for each call
        responses = [
            "Hello! I'm your SRE agent.",
            "I can help you monitor Redis performance.",
            "Is there anything specific you'd like to check?",
        ]
        mock_agent.process_query.side_effect = responses
        mock_get_agent.return_value = mock_agent

        session_id = "conversation-test-123"

        # Initial query
        response1 = client.post(
            "/api/v1/agent/query",
            json={
                "query": "Hello, I need help with Redis",
                "user_id": "test-user",
                "session_id": session_id,
            },
        )

        assert response1.status_code == 200
        assert response1.json()["response"] == responses[0]
        assert response1.json()["session_id"] == session_id

        # Follow-up chat messages
        response2 = client.post(
            "/api/v1/agent/chat",
            json={
                "message": "What can you help me with?",
                "session_id": session_id,
                "user_id": "test-user",
            },
        )

        assert response2.status_code == 200
        assert response2.json()["response"] == responses[1]

        response3 = client.post(
            "/api/v1/agent/chat",
            json={
                "message": "How do I check performance?",
                "session_id": session_id,
                "user_id": "test-user",
            },
        )

        assert response3.status_code == 200
        assert response3.json()["response"] == responses[2]

        # Verify all calls used the same session
        for call in mock_agent.process_query.call_args_list:
            assert call[1]["session_id"] == session_id
            assert call[1]["user_id"] == "test-user"

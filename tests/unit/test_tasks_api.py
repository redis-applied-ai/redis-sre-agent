"""Unit tests for tasks API endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


class TestTriageEndpoint:
    """Test the triage endpoint."""

    def test_triage_issue_error(self, client):
        """Test triage when an error occurs."""
        with patch("redis_sre_agent.api.tasks.get_redis_client") as mock_redis:
            mock_redis.side_effect = Exception("Redis connection failed")

            response = client.post(
                "/api/v1/triage",
                json={"query": "Redis issue"},
            )

            assert response.status_code == 500
            assert "Failed to triage issue" in response.json()["detail"]


class TestTaskStatusEndpoint:
    """Test the task status endpoint."""

    def test_get_task_status_error(self, client):
        """Test getting task status when an error occurs."""
        with patch("redis_sre_agent.api.tasks.get_redis_client") as mock_redis:
            mock_redis.side_effect = Exception("Redis error")

            response = client.get("/api/v1/tasks/thread-123")

            assert response.status_code == 500
            assert "Failed to get task status" in response.json()["detail"]


class TestContinueConversationEndpoint:
    """Test the continue conversation endpoint."""

    def test_continue_conversation_error(self, client):
        """Test continuing conversation when an error occurs."""
        with patch("redis_sre_agent.api.tasks.get_redis_client") as mock_redis:
            mock_redis.side_effect = Exception("Redis error")

            response = client.post(
                "/api/v1/tasks/thread-123/continue",
                json={"query": "Follow up"},
            )

            assert response.status_code == 500
            assert "Failed to continue conversation" in response.json()["detail"]


class TestDeleteTaskEndpoint:
    """Test the delete/cancel task endpoint."""

    def test_delete_task_error(self, client):
        """Test deleting task when an error occurs."""
        with patch("redis_sre_agent.api.tasks.get_redis_client") as mock_redis:
            mock_redis.side_effect = Exception("Redis error")

            response = client.delete("/api/v1/tasks/thread-123")

            assert response.status_code == 500
            assert "Failed to" in response.json()["detail"]


class TestListTasksEndpoint:
    """Test the list tasks endpoint."""

    def test_list_tasks_error(self, client):
        """Test listing tasks when an error occurs."""
        with patch("redis_sre_agent.api.tasks.get_redis_client") as mock_redis:
            mock_redis.side_effect = Exception("Redis error")

            response = client.get("/api/v1/tasks")

            assert response.status_code == 500
            assert "Failed to list tasks" in response.json()["detail"]

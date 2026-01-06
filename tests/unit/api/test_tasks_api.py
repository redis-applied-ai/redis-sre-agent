"""Unit tests for tasks API endpoints mounted under /api/v1."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


class TestTasksAPI:
    """Tests for /api/v1/tasks (create and get)."""

    def test_create_task_error(self, client):
        """POST /api/v1/tasks returns 500 when redis client creation fails."""
        with patch("redis_sre_agent.api.tasks.get_redis_client") as mock_get:
            mock_get.side_effect = Exception("Redis connection failed")
            resp = client.post("/api/v1/tasks", json={"message": "help"})
        assert resp.status_code == 500
        assert "Redis connection failed" in resp.json()["detail"]

    def test_get_task_not_found(self, client):
        """GET /api/v1/tasks/{task_id} returns 404 when TaskManager returns None."""
        mock_tm = MagicMock()
        mock_tm.get_task_state = AsyncMock(return_value=None)
        with patch("redis_sre_agent.api.tasks.TaskManager", return_value=mock_tm):
            resp = client.get("/api/v1/tasks/abc123")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Task not found"

    def test_create_task_success(self, client):
        """POST /api/v1/tasks returns 202 and task payload on success."""
        fake = {
            "task_id": "t1",
            "thread_id": "th1",
            "status": "queued",
            "message": "ok",
        }
        with (
            patch("redis_sre_agent.api.tasks.get_redis_client"),
            patch("redis_sre_agent.api.tasks.create_task", new=AsyncMock(return_value=fake)),
        ):
            resp = client.post("/api/v1/tasks", json={"message": "help"})
        assert resp.status_code == 202
        data = resp.json()
        assert data["task_id"] == "t1"
        assert data["thread_id"] == "th1"

    def test_get_task_success(self, client):
        """GET /api/v1/tasks/{task_id} returns 200 with state."""

        # Minimal TaskState-like object with metadata
        class Metadata:
            subject = "Test subject"
            created_at = "2024-01-01T00:00:00Z"
            updated_at = "2024-01-01T00:01:00Z"

        class S:
            task_id = "t1"
            thread_id = "th1"
            status = "queued"
            updates = []
            result = None
            error_message = None
            metadata = Metadata()

        mock_tm = MagicMock()
        mock_tm.get_task_state = AsyncMock(return_value=S())
        with patch("redis_sre_agent.api.tasks.TaskManager", return_value=mock_tm):
            resp = client.get("/api/v1/tasks/t1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "t1"
        assert data["thread_id"] == "th1"
        assert data["subject"] == "Test subject"
        assert data["created_at"] == "2024-01-01T00:00:00Z"
        assert data["updated_at"] == "2024-01-01T00:01:00Z"

    def test_delete_task_success(self, client):
        """DELETE /api/v1/tasks/{task_id} cancels Docket task and deletes core state."""

        with (
            patch("redis_sre_agent.api.tasks.get_redis_client") as mock_get_client,
            patch(
                "redis_sre_agent.api.tasks.delete_task_core",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch(
                "redis_sre_agent.api.tasks.get_redis_url",
                new_callable=AsyncMock,
            ) as mock_get_url,
            patch("redis_sre_agent.api.tasks.Docket") as mock_docket,
        ):
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_get_url.return_value = "redis://test"

            docket_instance = AsyncMock()
            docket_instance.__aenter__.return_value = docket_instance
            docket_instance.__aexit__.return_value = False
            mock_docket.return_value = docket_instance

            resp = client.delete("/api/v1/tasks/t1")

            assert resp.status_code == 200
            data = resp.json()
            assert data["message"] == "Task deleted successfully"
            assert data["task_id"] == "t1"
            assert "cancel_message" in data

            mock_delete.assert_awaited_once_with(task_id="t1", redis_client=mock_client)
            docket_instance.cancel.assert_awaited_once_with("t1")

    def test_delete_task_failure_returns_500(self, client):
        """If core delete fails, DELETE /tasks/{id} returns 500 with detail."""

        with (
            patch("redis_sre_agent.api.tasks.get_redis_client") as mock_get_client,
            patch(
                "redis_sre_agent.api.tasks.delete_task_core",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch(
                "redis_sre_agent.api.tasks.get_redis_url",
                new_callable=AsyncMock,
            ),
            patch("redis_sre_agent.api.tasks.Docket") as mock_docket,
        ):
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_delete.side_effect = Exception("boom")

            docket_instance = AsyncMock()
            docket_instance.__aenter__.return_value = docket_instance
            docket_instance.__aexit__.return_value = False
            mock_docket.return_value = docket_instance

            resp = client.delete("/api/v1/tasks/t1")

            assert resp.status_code == 500
            data = resp.json()
            assert "Failed to delete task t1" in data["detail"]

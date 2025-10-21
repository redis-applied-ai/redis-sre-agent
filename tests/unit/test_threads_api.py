"""Unit tests for threads API endpoints mounted under /api/v1."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


class TestThreadsAPI:
    """Tests for /api/v1/threads endpoints."""

    def test_create_thread_error(self, client):
        """POST /api/v1/threads returns 500 when redis client creation fails."""
        with patch("redis_sre_agent.api.threads.get_redis_client") as mock_get:
            mock_get.side_effect = Exception("Redis connection failed")
            resp = client.post(
                "/api/v1/threads",
                json={"user_id": "u", "session_id": "s"},
            )
        assert resp.status_code == 500
        assert "Redis connection failed" in resp.json()["detail"]

    def test_get_thread_not_found(self, client):
        """GET /api/v1/threads/{id} returns 404 when ThreadManager returns None."""
        mock_tm = MagicMock()
        mock_tm.get_thread_state = AsyncMock(return_value=None)
        with patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm):
            resp = client.get("/api/v1/threads/abc")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Thread not found"

    def test_append_messages_success(self, client):
        """POST /api/v1/threads/{id}/append-messages returns 204 on success."""
        mock_tm = MagicMock()
        mock_tm.append_messages = AsyncMock(return_value=True)
        with patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm):
            resp = client.post(
                "/api/v1/threads/t1/append-messages",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
        assert resp.status_code == 204
        assert resp.text == ""

    def test_update_thread_success(self, client):
        """PATCH /api/v1/threads/{id} returns 200 and updated true when ok."""
        # Thread state minimally used; just ensure not None
        state = MagicMock()
        state.context = {"messages": []}
        state.status = "queued"

        mock_tm = MagicMock()
        mock_tm.get_thread_state = AsyncMock(return_value=state)
        mock_tm.update_thread_context = AsyncMock(return_value=True)

        with patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm):
            resp = client.patch(
                "/api/v1/threads/t1",
                json={
                    "subject": "test subject",
                    "priority": 1,
                    "tags": ["a"],
                    "context": {"k": "v"},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("updated") is True

    def test_get_thread_success(self, client):
        """GET /api/v1/threads/{id} returns 200 with messages and metadata."""

        # Minimal ThreadState-like object
        class State:
            context = {"messages": [{"role": "user", "content": "hi"}]}
            status = "queued"
            action_items = []
            metadata = MagicMock()
            metadata.model_dump = lambda: {"user_id": "u"}

        mock_tm = MagicMock()
        mock_tm.get_thread_state = AsyncMock(return_value=State())
        with patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm):
            resp = client.get("/api/v1/threads/th1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thread_id"] == "th1"
        assert data["status"] == "queued"
        assert data["messages"] and data["messages"][0]["role"] == "user"

    def test_update_thread_not_found(self, client):
        """PATCH /api/v1/threads/{id} returns 404 when no state."""
        mock_tm = MagicMock()
        mock_tm.get_thread_state = AsyncMock(return_value=None)
        with patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm):
            resp = client.patch("/api/v1/threads/missing", json={"context": {"k": "v"}})
        assert resp.status_code == 404

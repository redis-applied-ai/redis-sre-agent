"""Unit tests for /api/v1/threads list endpoint message_count enrichment.

Ensures the endpoint computes message_count when summaries lack it.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app


def make_state_with_messages(n: int):
    class State:
        context = {"messages": [{"role": "user", "content": f"m{i}"} for i in range(n)]}
        metadata = MagicMock()

    return State()


def test_threads_list_includes_message_count():
    client = TestClient(app)
    with patch("redis_sre_agent.api.threads.ThreadManager") as tm_patch:
        tm = tm_patch.return_value
        # Summaries without message_count
        tm.list_threads = AsyncMock(
            return_value=[
                {
                    "thread_id": "t1",
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2025-01-01T00:01:00Z",
                }
            ]
        )
        # Return a state with 3 messages
        tm.get_thread = AsyncMock(return_value=make_state_with_messages(3))

        resp = client.get("/api/v1/threads")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list) and len(data) == 1
    assert data[0]["message_count"] == 3


def test_threads_list_message_count_defaults_to_zero_on_missing_state():
    client = TestClient(app)
    with patch("redis_sre_agent.api.threads.ThreadManager") as tm_patch:
        tm = tm_patch.return_value
        tm.list_threads = AsyncMock(
            return_value=[{"thread_id": "tX", "created_at": "..", "updated_at": ".."}]
        )
        tm.get_thread = AsyncMock(return_value=None)  # state not found

        resp = client.get("/api/v1/threads")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["message_count"] == 0

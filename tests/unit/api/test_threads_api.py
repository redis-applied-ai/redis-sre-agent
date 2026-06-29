"""Unit tests for threads API endpoints mounted under /api/v1."""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app
from redis_sre_agent.core.approvals import ApprovalStatus, PendingApprovalSummary
from redis_sre_agent.core.tasks import TaskStatus


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

    def test_create_thread_generates_subject_from_original_query(self, client):
        """POST /api/v1/threads derives a subject when only original_query is provided."""
        from redis_sre_agent.core.threads import Thread, ThreadMetadata

        mock_tm = MagicMock()
        mock_tm.create_thread = AsyncMock(return_value="th1")
        mock_tm.update_thread_subject = AsyncMock(return_value=True)
        mock_tm.get_thread = AsyncMock(
            return_value=Thread(thread_id="th1", context={}, metadata=ThreadMetadata())
        )

        with patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm):
            resp = client.post(
                "/api/v1/threads",
                json={"context": {"original_query": "Investigate Redis memory spike"}},
            )

        assert resp.status_code == 201
        mock_tm.update_thread_subject.assert_awaited_once_with(
            "th1", "Investigate Redis memory spike"
        )

    def test_create_thread_generates_subject_from_first_user_message(self, client):
        """POST /api/v1/threads uses the first user message when no subject is provided."""
        from redis_sre_agent.core.threads import Message, Thread, ThreadMetadata

        mock_tm = MagicMock()
        mock_tm.create_thread = AsyncMock(return_value="th1")
        mock_tm.update_thread_subject = AsyncMock(return_value=True)
        mock_tm.append_messages = AsyncMock(return_value=True)
        mock_tm.get_thread = AsyncMock(
            return_value=Thread(
                thread_id="th1",
                messages=[Message(role="user", content="Check Redis latency")],
                context={},
                metadata=ThreadMetadata(),
            )
        )

        with patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm):
            resp = client.post(
                "/api/v1/threads",
                json={"messages": [{"role": "user", "content": "Check Redis latency"}]},
            )

        assert resp.status_code == 201
        mock_tm.update_thread_subject.assert_awaited_once_with("th1", "Check Redis latency")

    def test_get_thread_not_found(self, client):
        """GET /api/v1/threads/{id} returns 404 when ThreadManager returns None."""
        mock_tm = MagicMock()
        mock_tm.get_thread = AsyncMock(return_value=None)
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

        mock_tm = MagicMock()
        mock_tm.get_thread = AsyncMock(return_value=state)
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
        from redis_sre_agent.core.threads import Message, Thread, ThreadMetadata

        # Create a proper Thread object matching the model
        mock_thread = Thread(
            thread_id="th1",
            messages=[Message(role="user", content="hi")],
            context={},
            metadata=ThreadMetadata(user_id="u"),
        )

        mock_tm = MagicMock()
        mock_tm.get_thread = AsyncMock(return_value=mock_thread)
        with patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm):
            resp = client.get("/api/v1/threads/th1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thread_id"] == "th1"
        assert data["messages"] and data["messages"][0]["role"] == "user"

    def test_get_thread_includes_pending_approval_and_resume_supported(self, client):
        """GET /api/v1/threads/{id} includes latest approval state from the newest task."""
        from redis_sre_agent.core.threads import Message, Thread, ThreadMetadata

        pending = PendingApprovalSummary(
            approval_id="approval-1",
            interrupt_id="interrupt-1",
            tool_name="redis_cloud_deadbeef_update_tags",
            summary="redis_cloud_deadbeef_update_tags on inst-1",
            requested_at="2024-01-01T00:00:00Z",
            status=ApprovalStatus.PENDING,
        )

        class TaskState:
            updates = []
            result = {
                "citation_groups": [
                    {
                        "group_key": "startup_context_loaded",
                        "label": "Startup context loaded",
                        "citations": [{"title": "Pinned Runbook"}],
                        "count": 1,
                    }
                ]
            }
            error_message = None
            status = "awaiting_approval"
            pending_approval = pending
            resume_supported = True

        mock_thread = Thread(
            thread_id="th1",
            messages=[Message(role="user", content="hi")],
            context={},
            metadata=ThreadMetadata(user_id="u"),
        )

        mock_tm = MagicMock()
        mock_tm.get_thread = AsyncMock(return_value=mock_thread)
        mock_task_manager = MagicMock()
        mock_task_manager.get_task_state = AsyncMock(return_value=TaskState())
        mock_redis = AsyncMock()
        mock_redis.zrevrange.return_value = ["task-1"]

        with (
            patch("redis_sre_agent.api.threads.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm),
            patch("redis_sre_agent.core.tasks.TaskManager", return_value=mock_task_manager),
        ):
            resp = client.get("/api/v1/threads/th1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["pending_approval"]["approval_id"] == "approval-1"
        assert data["task_id"] == "task-1"
        assert data["resume_supported"] is True
        assert data["citation_groups"][0]["group_key"] == "startup_context_loaded"
        assert data["citation_groups"][0]["citations"][0]["title"] == "Pinned Runbook"

    def test_update_thread_not_found(self, client):
        """PATCH /api/v1/threads/{id} returns 404 when no state."""
        mock_tm = MagicMock()
        mock_tm.get_thread = AsyncMock(return_value=None)
        with patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm):
            resp = client.patch("/api/v1/threads/missing", json={"context": {"k": "v"}})
        assert resp.status_code == 404

    def test_cancel_thread_tasks_cancels_all_active_tasks(self, client):
        """POST /threads/{id}/cancel cancels every active task indexed to the thread."""
        from redis_sre_agent.core.threads import Thread, ThreadMetadata

        class ActiveParentState:
            status = TaskStatus.IN_PROGRESS

        class TerminalChildState:
            status = TaskStatus.DONE

        class ActiveChildState:
            status = TaskStatus.QUEUED

        mock_thread = Thread(thread_id="th1", context={}, metadata=ThreadMetadata(user_id="u"))
        mock_tm = MagicMock()
        mock_tm.get_thread = AsyncMock(return_value=mock_thread)
        mock_task_manager = MagicMock()
        mock_task_manager.get_task_state = AsyncMock(
            side_effect=[ActiveParentState(), TerminalChildState(), ActiveChildState()]
        )
        mock_task_manager.set_pending_approval = AsyncMock()
        mock_task_manager.set_resume_supported = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.add_task_update = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.zrange.return_value = [b"parent-task", b"done-child", b"active-child"]
        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False

        with (
            patch("redis_sre_agent.api.threads.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm),
            patch("redis_sre_agent.api.threads.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.api.tasks.get_redis_url",
                new=AsyncMock(return_value="redis://test"),
            ),
            patch("redis_sre_agent.api.tasks.Docket", return_value=docket_instance),
        ):
            resp = client.post("/api/v1/threads/th1/cancel")

        assert resp.status_code == 200
        assert resp.json() == {
            "thread_id": "th1",
            "cancelled_task_ids": ["parent-task", "active-child"],
            "terminal_task_ids": ["done-child"],
            "missing_task_ids": [],
        }
        assert docket_instance.cancel.await_args_list == [
            call("parent-task"),
            call("active-child"),
        ]
        assert mock_task_manager.update_task_status.await_args_list == [
            call("parent-task", TaskStatus.CANCELLED),
            call("active-child", TaskStatus.CANCELLED),
        ]
        assert mock_task_manager.add_task_update.await_count == 2

    def test_cancel_thread_tasks_reports_terminal_and_missing_history_without_mutation(
        self, client
    ):
        """POST /threads/{id}/cancel reports historical tasks without rewriting them."""
        from redis_sre_agent.core.threads import Thread, ThreadMetadata

        class FailedState:
            status = TaskStatus.FAILED

        class CancelledState:
            status = TaskStatus.CANCELLED

        mock_thread = Thread(thread_id="th1", context={}, metadata=ThreadMetadata(user_id="u"))
        mock_tm = MagicMock()
        mock_tm.get_thread = AsyncMock(return_value=mock_thread)
        mock_task_manager = MagicMock()
        mock_task_manager.get_task_state = AsyncMock(
            side_effect=[FailedState(), CancelledState(), None]
        )
        mock_task_manager.set_pending_approval = AsyncMock()
        mock_task_manager.set_resume_supported = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.add_task_update = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.zrange.return_value = [b"failed-task", b"cancelled-task", b"missing-task"]

        with (
            patch("redis_sre_agent.api.threads.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm),
            patch("redis_sre_agent.api.threads.TaskManager", return_value=mock_task_manager),
            patch("redis_sre_agent.api.tasks.Docket") as mock_docket,
        ):
            resp = client.post("/api/v1/threads/th1/cancel")

        assert resp.status_code == 200
        assert resp.json() == {
            "thread_id": "th1",
            "cancelled_task_ids": [],
            "terminal_task_ids": ["failed-task", "cancelled-task"],
            "missing_task_ids": ["missing-task"],
        }
        mock_docket.assert_not_called()
        mock_task_manager.set_pending_approval.assert_not_awaited()
        mock_task_manager.set_resume_supported.assert_not_awaited()
        mock_task_manager.update_task_status.assert_not_awaited()
        mock_task_manager.add_task_update.assert_not_awaited()

    def test_cancel_thread_tasks_not_found(self, client):
        """POST /threads/{id}/cancel returns 404 when the thread is missing."""
        mock_tm = MagicMock()
        mock_tm.get_thread = AsyncMock(return_value=None)
        mock_redis = AsyncMock()

        with (
            patch("redis_sre_agent.api.threads.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.api.threads.ThreadManager", return_value=mock_tm),
            patch("redis_sre_agent.api.threads.TaskManager") as mock_task_manager,
        ):
            resp = client.post("/api/v1/threads/missing/cancel")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Thread not found"
        mock_redis.zrange.assert_not_called()
        mock_task_manager.assert_not_called()

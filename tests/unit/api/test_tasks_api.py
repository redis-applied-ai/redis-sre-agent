"""Unit tests for tasks API endpoints mounted under /api/v1."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app
from redis_sre_agent.core.approvals import ApprovalRecord
from redis_sre_agent.core.tasks import TaskStatus


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
        mock_tm.get_task_tool_calls = AsyncMock(return_value=None)
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

    def test_create_task_missing_thread_id_returns_500(self, client):
        """POST /api/v1/tasks returns 500 if core create_task omits thread_id."""
        fake = {
            "task_id": "t1",
            "thread_id": "",
            "status": "queued",
            "message": "ok",
        }
        with (
            patch("redis_sre_agent.api.tasks.get_redis_client"),
            patch("redis_sre_agent.api.tasks.create_task", new=AsyncMock(return_value=fake)),
            patch("redis_sre_agent.api.tasks.Docket") as mock_docket,
        ):
            resp = client.post("/api/v1/tasks", json={"message": "help"})

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Failed to create thread for task"
        mock_docket.assert_not_called()

    def test_create_task_http_exception_passthrough(self, client):
        """POST /api/v1/tasks preserves explicit HTTPException from dependencies."""
        with (
            patch("redis_sre_agent.api.tasks.get_redis_client"),
            patch(
                "redis_sre_agent.api.tasks.create_task",
                new=AsyncMock(side_effect=HTTPException(status_code=429, detail="rate limited")),
            ),
        ):
            resp = client.post("/api/v1/tasks", json={"message": "help"})

        assert resp.status_code == 429
        assert resp.json()["detail"] == "rate limited"

    def test_create_task_rejects_instance_and_cluster_together(self, client):
        """POST /api/v1/tasks returns 400 when both target IDs are provided."""
        with patch("redis_sre_agent.api.tasks.get_redis_client"):
            resp = client.post(
                "/api/v1/tasks",
                json={
                    "message": "help",
                    "context": {
                        "instance_id": "redis-prod-1",
                        "cluster_id": "cluster-prod-1",
                    },
                },
            )

        assert resp.status_code == 400
        assert "only one of instance_id or cluster_id" in resp.json()["detail"]

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
        mock_tm.get_task_tool_calls = AsyncMock(return_value=None)
        with patch("redis_sre_agent.api.tasks.TaskManager", return_value=mock_tm):
            resp = client.get("/api/v1/tasks/t1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "t1"
        assert data["thread_id"] == "th1"
        assert data["subject"] == "Test subject"
        assert data["created_at"] == "2024-01-01T00:00:00Z"
        assert data["updated_at"] == "2024-01-01T00:01:00Z"
        assert data["tool_calls"] is None

    def test_get_task_done_includes_tool_calls(self, client):
        """GET /api/v1/tasks/{task_id} returns tool_calls for completed tasks."""

        class Metadata:
            subject = "Complete task"
            created_at = "2024-01-01T00:00:00Z"
            updated_at = "2024-01-01T00:01:00Z"

        class S:
            task_id = "t1"
            thread_id = "th1"
            status = "done"
            updates = []
            result = {"response": "ok"}
            error_message = None
            metadata = Metadata()

        tool_calls = [{"name": "redis_info", "args": {"section": "memory"}, "status": "success"}]
        mock_tm = MagicMock()
        mock_tm.get_task_state = AsyncMock(return_value=S())
        mock_tm.get_task_tool_calls = AsyncMock(return_value=tool_calls)
        with patch("redis_sre_agent.api.tasks.TaskManager", return_value=mock_tm):
            resp = client.get("/api/v1/tasks/t1")

        assert resp.status_code == 200
        assert resp.json()["tool_calls"] == tool_calls

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

    def test_list_task_approvals_success(self, client):
        """GET /api/v1/tasks/{task_id}/approvals returns stored approval history."""

        class Metadata:
            subject = "Approval task"
            created_at = "2024-01-01T00:00:00Z"
            updated_at = "2024-01-01T00:01:00Z"

        class S:
            task_id = "t1"
            thread_id = "th1"
            status = TaskStatus.AWAITING_APPROVAL
            updates = []
            result = None
            error_message = None
            metadata = Metadata()

        approval = ApprovalRecord(
            approval_id="approval-1",
            task_id="t1",
            thread_id="th1",
            graph_thread_id="t1",
            interrupt_id="interrupt-1",
            graph_type="chat",
            graph_version="v1",
            tool_name="redis_cloud_deadbeef_update_tags",
            tool_args={"tag": "prod"},
            tool_args_preview={"tag": "prod"},
            action_hash="hash-1",
        )

        mock_tm = MagicMock()
        mock_tm.get_task_state = AsyncMock(return_value=S())
        with (
            patch("redis_sre_agent.api.tasks.TaskManager", return_value=mock_tm),
            patch(
                "redis_sre_agent.api.tasks.ApprovalManager",
                return_value=MagicMock(list_task_approvals=AsyncMock(return_value=[approval])),
            ),
        ):
            resp = client.get("/api/v1/tasks/t1/approvals")

        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "t1"
        assert data["approvals"][0]["approval_id"] == "approval-1"

    def test_resume_task_success_returns_updated_task(self, client):
        """POST /api/v1/tasks/{task_id}/resume returns the refreshed task state."""

        class Metadata:
            subject = "Resumed task"
            created_at = "2024-01-01T00:00:00Z"
            updated_at = "2024-01-01T00:02:00Z"

        class AwaitingApprovalState:
            task_id = "t1"
            thread_id = "th1"
            status = TaskStatus.AWAITING_APPROVAL
            updates = []
            result = None
            error_message = None
            metadata = Metadata()
            pending_approval = {"approval_id": "approval-1"}
            resume_supported = True

        class InProgressState:
            task_id = "t1"
            thread_id = "th1"
            status = TaskStatus.IN_PROGRESS
            updates = []
            result = None
            error_message = None
            metadata = Metadata()
            pending_approval = None
            resume_supported = True

        mock_tm = MagicMock()
        mock_tm.get_task_state = AsyncMock(
            side_effect=[AwaitingApprovalState(), InProgressState()]
        )
        mock_tm.get_task_tool_calls = AsyncMock(return_value=None)
        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False
        resume_task = AsyncMock()
        docket_instance.add = MagicMock(return_value=resume_task)

        with (
            patch("redis_sre_agent.api.tasks.TaskManager", return_value=mock_tm),
            patch("redis_sre_agent.api.tasks.get_redis_url", new=AsyncMock(return_value="redis://")),
            patch(
                "redis_sre_agent.api.tasks.validate_task_resume_request",
                new=AsyncMock(),
            ) as mock_validate,
            patch("redis_sre_agent.api.tasks.Docket", return_value=docket_instance),
        ):
            resp = client.post(
                "/api/v1/tasks/t1/resume",
                json={"approval_id": "approval-1", "decision": "approved"},
            )

        assert resp.status_code == 200
        assert resp.json()["task_id"] == "t1"
        assert resp.json()["status"] == TaskStatus.IN_PROGRESS.value
        mock_validate.assert_awaited_once()
        docket_instance.add.assert_called_once()
        resume_task.assert_awaited_once_with(
            task_id="t1",
            approval_id="approval-1",
            decision="approved",
            decision_by=None,
            decision_comment=None,
        )

    def test_resume_task_maps_validation_errors(self, client):
        """POST /api/v1/tasks/{task_id}/resume returns 400 for invalid resume requests."""

        class Metadata:
            subject = "Awaiting task"
            created_at = "2024-01-01T00:00:00Z"
            updated_at = "2024-01-01T00:02:00Z"

        class S:
            task_id = "t1"
            thread_id = "th1"
            status = TaskStatus.AWAITING_APPROVAL
            updates = []
            result = None
            error_message = None
            metadata = Metadata()
            pending_approval = None
            resume_supported = True

        mock_tm = MagicMock()
        mock_tm.get_task_state = AsyncMock(return_value=S())

        with (
            patch("redis_sre_agent.api.tasks.TaskManager", return_value=mock_tm),
            patch(
                "redis_sre_agent.api.tasks.validate_task_resume_request",
                new=AsyncMock(side_effect=ValueError("Approval approval-1 has expired")),
            ),
            patch("redis_sre_agent.api.tasks.Docket") as mock_docket,
        ):
            resp = client.post(
                "/api/v1/tasks/t1/resume",
                json={"approval_id": "approval-1", "decision": "approved"},
            )

        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"]
        mock_docket.assert_not_called()

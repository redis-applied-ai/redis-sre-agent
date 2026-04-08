"""Unit tests for schedules API endpoints related to runs listing.

Covers regression where thread summaries lacked a 'status' field and caused
KeyError in the runs listing code. Ensures we return 200 and valid runs.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestSchedulesRunsAPI:
    def test_list_runs_404_when_schedule_missing(self, client):
        with patch("redis_sre_agent.api.schedules._get_schedule", new=AsyncMock(return_value=None)):
            resp = client.get("/api/v1/schedules/missing/runs")
        assert resp.status_code == 404

    def test_list_runs_handles_missing_status_field(self, client):
        # Arrange: schedule exists
        with (
            patch(
                "redis_sre_agent.api.schedules._get_schedule",
                new=AsyncMock(return_value={"id": "sch1", "name": "S"}),
            ),
            patch("redis_sre_agent.api.schedules.get_redis_client") as mock_get_rc,
            patch("redis_sre_agent.api.schedules.ThreadManager") as tm_patch,
            patch("redis_sre_agent.api.schedules.TaskManager") as taskm_patch,
        ):
            # ThreadManager mocks
            tm = tm_patch.return_value
            # list_threads returns summaries WITHOUT a 'status' key
            tm.list_threads = AsyncMock(
                return_value=[
                    {
                        "thread_id": "t1",
                        "created_at": "2025-01-01T00:00:00Z",
                        "updated_at": "2025-01-01T00:05:00Z",
                        # no 'status' field here on purpose
                    }
                ]
            )
            # get_thread returns a state-like object with context referencing this schedule
            state = MagicMock()
            state.context = {"schedule_id": "sch1", "scheduled_at": "2025-01-01T00:00:00Z"}
            tm.get_thread = AsyncMock(return_value=state)

            # Redis client mock: ensure zrevrange returns empty so no task_id
            rc = AsyncMock()
            rc.zrevrange = AsyncMock(return_value=[])
            mock_get_rc.return_value = rc

            # TaskManager mock not used in this path (no tids), but safe to set
            taskm = taskm_patch.return_value
            taskm.get_task_state = AsyncMock(return_value=None)

            # Act
            resp = client.get("/api/v1/schedules/sch1/runs")

        # Assert
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list) and len(data) == 1
        run = data[0]
        assert run["thread_id"] == "t1"
        # Default when no task found
        assert run["status"] in ("queued", "pending")
        assert run["schedule_id"] == "sch1"


class TestSchedulesTriggerAPI:
    def test_trigger_schedule_now_preserves_legacy_instance_scope(self, client):
        schedule = {
            "id": "sch1",
            "name": "Nightly Check",
            "instructions": "Check memory usage",
            "redis_instance_id": "redis-prod-1",
        }
        task_callable = AsyncMock(return_value="task-123")
        docket = MagicMock()
        docket.__aenter__.return_value = docket
        docket.__aexit__.return_value = False
        docket.add.return_value = task_callable

        with (
            patch(
                "redis_sre_agent.api.schedules._get_schedule",
                new=AsyncMock(return_value=schedule),
            ),
            patch("redis_sre_agent.api.schedules.get_redis_client", return_value=AsyncMock()),
            patch("redis_sre_agent.api.schedules.ThreadManager") as tm_patch,
            patch(
                "redis_sre_agent.api.schedules.get_redis_url",
                new=AsyncMock(return_value="redis://localhost:6379/0"),
            ),
            patch("redis_sre_agent.api.schedules.Docket", return_value=docket),
        ):
            tm = tm_patch.return_value
            tm.create_thread = AsyncMock(return_value="thread-123")
            tm.set_thread_subject = AsyncMock()

            resp = client.post("/api/v1/schedules/sch1/trigger")

        assert resp.status_code == 200, resp.text
        create_kwargs = tm.create_thread.await_args.kwargs
        assert create_kwargs["user_id"] == "scheduler"
        assert create_kwargs["session_id"].startswith("manual_schedule_sch1_")
        assert create_kwargs["tags"] == ["automated", "scheduled", "manual_trigger"]
        assert create_kwargs["initial_context"]["instance_id"] == "redis-prod-1"
        assert create_kwargs["initial_context"]["manual_trigger"] is True
        assert create_kwargs["initial_context"]["schedule_id"] == "sch1"

        task_callable.assert_awaited_once()
        task_kwargs = task_callable.await_args.kwargs
        assert task_kwargs["thread_id"] == "thread-123"
        assert task_kwargs["message"] == "Check memory usage"
        assert task_kwargs["context"]["instance_id"] == "redis-prod-1"

        payload = resp.json()
        assert payload["schedule_id"] == "sch1"
        assert payload["thread_id"] == "thread-123"
        assert payload["status"] == "pending"

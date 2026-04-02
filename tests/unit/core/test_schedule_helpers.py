"""Tests for schedule MCP helpers."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.tasks import TaskMetadata, TaskState, TaskStatus


def _schedule(**overrides):
    data = {
        "id": "schedule-1",
        "name": "Nightly Check",
        "description": "Run a nightly health check",
        "interval_type": "hours",
        "interval_value": 12,
        "instructions": "Check memory usage",
        "enabled": True,
        "created_at": "2026-03-25T00:00:00+00:00",
        "updated_at": "2026-03-25T00:00:00+00:00",
        "last_run_at": None,
        "next_run_at": "2026-03-25T12:00:00+00:00",
        "redis_instance_id": "redis-prod-1",
    }
    data.update(overrides)
    return data


class TestScheduleReadHelpers:
    @pytest.mark.asyncio
    async def test_list_schedules_helper_applies_limit(self):
        from redis_sre_agent.core.schedule_helpers import list_schedules_helper

        schedules = [_schedule(id="schedule-1"), _schedule(id="schedule-2")]

        with patch(
            "redis_sre_agent.core.schedule_helpers.core_schedules.list_schedules",
            new_callable=AsyncMock,
            return_value=schedules,
        ) as mock_list:
            result = await list_schedules_helper(limit=1)

        assert result == {"schedules": [schedules[0]], "total": 2, "limit": 1}
        mock_list.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_get_schedule_helper_returns_schedule(self):
        from redis_sre_agent.core.schedule_helpers import get_schedule_helper

        with patch(
            "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
            new_callable=AsyncMock,
            return_value=_schedule(),
        ):
            result = await get_schedule_helper("schedule-1")

        assert result["id"] == "schedule-1"

    @pytest.mark.asyncio
    async def test_get_schedule_helper_returns_error_when_missing(self):
        from redis_sre_agent.core.schedule_helpers import get_schedule_helper

        with patch(
            "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await get_schedule_helper("schedule-404")

        assert result == {"error": "Schedule not found", "id": "schedule-404"}


class TestScheduleMutationHelpers:
    @pytest.mark.asyncio
    async def test_create_schedule_helper_creates_schedule(self):
        from redis_sre_agent.core.schedule_helpers import create_schedule_helper

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.store_schedule",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_store,
            patch("redis_sre_agent.core.schedule_helpers.datetime") as mock_datetime,
        ):
            mock_now = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now

            result = await create_schedule_helper(
                name="Nightly Check",
                interval_type="hours",
                interval_value=12,
                instructions="Check memory usage",
                redis_instance_id="redis-prod-1",
                description="Run a nightly health check",
                enabled=True,
            )

        assert result["status"] == "created"
        stored = mock_store.await_args.args[0]
        assert stored["name"] == "Nightly Check"
        assert stored["next_run_at"] is not None

    @pytest.mark.asyncio
    async def test_create_schedule_helper_raises_when_store_fails(self):
        from redis_sre_agent.core.schedule_helpers import create_schedule_helper

        with patch(
            "redis_sre_agent.core.schedule_helpers.core_schedules.store_schedule",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="Failed to store schedule"):
                await create_schedule_helper(
                    name="Nightly Check",
                    interval_type="hours",
                    interval_value=12,
                    instructions="Check memory usage",
                )

    @pytest.mark.asyncio
    async def test_update_schedule_helper_recalculates_next_run(self):
        from redis_sre_agent.core.schedule_helpers import update_schedule_helper

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(enabled=False, next_run_at=None),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.store_schedule",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_store,
        ):
            result = await update_schedule_helper(
                "schedule-1",
                interval_value=24,
                enabled=True,
                recalc_next_run=True,
            )

        assert result == {"id": "schedule-1", "status": "updated"}
        stored = mock_store.await_args.args[0]
        assert stored["interval_value"] == 24
        assert stored["enabled"] is True
        assert stored["next_run_at"] is not None

    @pytest.mark.asyncio
    async def test_update_schedule_helper_updates_all_optional_fields(self):
        from redis_sre_agent.core.schedule_helpers import update_schedule_helper

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.store_schedule",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_store,
        ):
            await update_schedule_helper(
                "schedule-1",
                name="Updated Name",
                description="Updated description",
                instructions="Updated instructions",
                redis_instance_id="redis-prod-2",
                interval_type="days",
                interval_value=2,
                enabled=False,
                recalc_next_run=False,
            )

        stored = mock_store.await_args.args[0]
        assert stored["name"] == "Updated Name"
        assert stored["description"] == "Updated description"
        assert stored["instructions"] == "Updated instructions"
        assert stored["redis_instance_id"] == "redis-prod-2"
        assert stored["interval_type"] == "days"
        assert stored["interval_value"] == 2
        assert stored["enabled"] is False

    @pytest.mark.asyncio
    async def test_update_schedule_helper_raises_for_missing_schedule(self):
        from redis_sre_agent.core.schedule_helpers import update_schedule_helper

        with patch(
            "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="Schedule not found"):
                await update_schedule_helper("schedule-404", name="Updated")

    @pytest.mark.asyncio
    async def test_update_schedule_helper_raises_when_store_fails(self):
        from redis_sre_agent.core.schedule_helpers import update_schedule_helper

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.store_schedule",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to store updated schedule"):
                await update_schedule_helper("schedule-1", description="Updated")

    @pytest.mark.asyncio
    async def test_enable_schedule_helper_sets_missing_next_run(self):
        from redis_sre_agent.core.schedule_helpers import enable_schedule_helper

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(enabled=False, next_run_at=None),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.store_schedule",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_store,
        ):
            result = await enable_schedule_helper("schedule-1")

        assert result == {"id": "schedule-1", "status": "enabled"}
        stored = mock_store.await_args.args[0]
        assert stored["enabled"] is True
        assert stored["next_run_at"] is not None

    @pytest.mark.asyncio
    async def test_enable_schedule_helper_raises_for_missing_schedule(self):
        from redis_sre_agent.core.schedule_helpers import enable_schedule_helper

        with patch(
            "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="Schedule not found"):
                await enable_schedule_helper("schedule-404")

    @pytest.mark.asyncio
    async def test_enable_schedule_helper_raises_when_store_fails(self):
        from redis_sre_agent.core.schedule_helpers import enable_schedule_helper

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.store_schedule",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to store enabled schedule"):
                await enable_schedule_helper("schedule-1")

    @pytest.mark.asyncio
    async def test_disable_schedule_helper_updates_schedule(self):
        from redis_sre_agent.core.schedule_helpers import disable_schedule_helper

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.store_schedule",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_store,
        ):
            result = await disable_schedule_helper("schedule-1")

        assert result == {"id": "schedule-1", "status": "disabled"}
        assert mock_store.await_args.args[0]["enabled"] is False

    @pytest.mark.asyncio
    async def test_disable_schedule_helper_raises_for_missing_schedule(self):
        from redis_sre_agent.core.schedule_helpers import disable_schedule_helper

        with patch(
            "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="Schedule not found"):
                await disable_schedule_helper("schedule-404")

    @pytest.mark.asyncio
    async def test_disable_schedule_helper_raises_when_store_fails(self):
        from redis_sre_agent.core.schedule_helpers import disable_schedule_helper

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.store_schedule",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to store disabled schedule"):
                await disable_schedule_helper("schedule-1")

    @pytest.mark.asyncio
    async def test_delete_schedule_helper_requires_confirmation(self):
        from redis_sre_agent.core.schedule_helpers import delete_schedule_helper

        result = await delete_schedule_helper("schedule-1", confirm=False)

        assert result == {
            "error": "Confirmation required",
            "id": "schedule-1",
            "status": "cancelled",
        }

    @pytest.mark.asyncio
    async def test_delete_schedule_helper_deletes_schedule(self):
        from redis_sre_agent.core.schedule_helpers import delete_schedule_helper

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.delete_schedule",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = await delete_schedule_helper("schedule-1", confirm=True)

        assert result == {"id": "schedule-1", "status": "deleted"}

    @pytest.mark.asyncio
    async def test_delete_schedule_helper_raises_for_missing_schedule(self):
        from redis_sre_agent.core.schedule_helpers import delete_schedule_helper

        with patch(
            "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="Schedule not found"):
                await delete_schedule_helper("schedule-404", confirm=True)

    @pytest.mark.asyncio
    async def test_delete_schedule_helper_raises_when_delete_fails(self):
        from redis_sre_agent.core.schedule_helpers import delete_schedule_helper

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.delete_schedule",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(RuntimeError, match="Delete failed or schedule not found"):
                await delete_schedule_helper("schedule-1", confirm=True)


class TestScheduleRunHelpers:
    def test_get_schedule_task_callable_returns_process_agent_turn(self):
        from redis_sre_agent.core.docket_tasks import process_agent_turn
        from redis_sre_agent.core.schedule_helpers import _get_schedule_task_callable

        assert _get_schedule_task_callable() is process_agent_turn

    @pytest.mark.asyncio
    async def test_run_schedule_now_helper_enqueues_run(self):
        from redis_sre_agent.core.schedule_helpers import run_schedule_now_helper

        thread_manager = AsyncMock()
        thread_manager.create_thread.return_value = "thread-1"
        thread_manager.set_thread_subject.return_value = True

        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False
        queued = AsyncMock(return_value="docket-1")
        docket_instance.add = MagicMock(return_value=queued)

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=AsyncMock(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://test",
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers._get_schedule_task_callable",
                return_value="process-agent-turn",
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.create_task",
                new_callable=AsyncMock,
                return_value={"task_id": "task-1"},
            ) as mock_create_task,
            patch("redis_sre_agent.core.schedule_helpers.Docket", return_value=docket_instance),
        ):
            result = await run_schedule_now_helper("schedule-1")

        assert result["status"] == "pending"
        assert result["thread_id"] == "thread-1"
        assert result["docket_task_id"] == "docket-1"
        assert result["task_id"] == "task-1"
        mock_create_task.assert_awaited_once()
        assert queued.await_args.kwargs["task_id"] == "task-1"
        queued.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_schedule_now_helper_returns_error_when_missing_schedule(self):
        from redis_sre_agent.core.schedule_helpers import run_schedule_now_helper

        with patch(
            "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await run_schedule_now_helper("schedule-404")

        assert result == {"error": "Schedule not found", "id": "schedule-404"}

    @pytest.mark.asyncio
    async def test_run_schedule_now_helper_handles_duplicate_submission(self):
        from redis_sre_agent.core.schedule_helpers import run_schedule_now_helper

        thread_manager = AsyncMock()
        thread_manager.create_thread.return_value = "thread-1"
        thread_manager.set_thread_subject.return_value = True

        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False
        queued = AsyncMock(side_effect=RuntimeError("duplicate key"))
        docket_instance.add = MagicMock(return_value=queued)

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=AsyncMock(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://test",
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers._get_schedule_task_callable",
                return_value="process-agent-turn",
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.create_task",
                new_callable=AsyncMock,
                return_value={"task_id": "task-1"},
            ),
            patch("redis_sre_agent.core.schedule_helpers.Docket", return_value=docket_instance),
        ):
            result = await run_schedule_now_helper("schedule-1")

        assert result["docket_task_id"] == "already_running"

    @pytest.mark.asyncio
    async def test_run_schedule_now_helper_awaits_async_docket_add_result(self):
        from redis_sre_agent.core.schedule_helpers import run_schedule_now_helper

        thread_manager = AsyncMock()
        thread_manager.create_thread.return_value = "thread-1"
        thread_manager.set_thread_subject.return_value = True

        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False
        queued = AsyncMock(return_value="docket-1")
        docket_instance.add = AsyncMock(return_value=queued)

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=AsyncMock(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://test",
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers._get_schedule_task_callable",
                return_value="process-agent-turn",
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.create_task",
                new_callable=AsyncMock,
                return_value={"task_id": "task-1"},
            ),
            patch("redis_sre_agent.core.schedule_helpers.Docket", return_value=docket_instance),
        ):
            result = await run_schedule_now_helper("schedule-1")

        assert result["docket_task_id"] == "docket-1"
        docket_instance.add.assert_awaited_once()
        queued.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_schedule_now_helper_ignores_subject_update_failure(self):
        from redis_sre_agent.core.schedule_helpers import run_schedule_now_helper

        thread_manager = AsyncMock()
        thread_manager.create_thread.return_value = "thread-1"
        thread_manager.set_thread_subject.side_effect = RuntimeError("ignore me")

        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False
        queued = AsyncMock(return_value="docket-1")
        docket_instance.add = MagicMock(return_value=queued)

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(name="", instructions="First line\nSecond line"),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=AsyncMock(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://test",
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers._get_schedule_task_callable",
                return_value="process-agent-turn",
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.create_task",
                new_callable=AsyncMock,
                return_value={"task_id": "task-1"},
            ),
            patch("redis_sre_agent.core.schedule_helpers.Docket", return_value=docket_instance),
        ):
            result = await run_schedule_now_helper("schedule-1")

        assert result["docket_task_id"] == "docket-1"

    @pytest.mark.asyncio
    async def test_run_schedule_now_helper_reraises_non_duplicate_submission_error(self):
        from redis_sre_agent.core.schedule_helpers import run_schedule_now_helper

        thread_manager = AsyncMock()
        thread_manager.create_thread.return_value = "thread-1"
        thread_manager.set_thread_subject.return_value = True

        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False
        queued = AsyncMock(side_effect=RuntimeError("boom"))
        docket_instance.add = MagicMock(return_value=queued)

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=AsyncMock(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://test",
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers._get_schedule_task_callable",
                return_value="process-agent-turn",
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.create_task",
                new_callable=AsyncMock,
                return_value={"task_id": "task-1"},
            ),
            patch("redis_sre_agent.core.schedule_helpers.Docket", return_value=docket_instance),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                await run_schedule_now_helper("schedule-1")

    @pytest.mark.asyncio
    async def test_list_schedule_runs_helper_returns_runs(self):
        from redis_sre_agent.core.schedule_helpers import list_schedule_runs_helper

        redis_client = AsyncMock()
        redis_client.zrevrange.return_value = [b"task-1"]

        thread_manager = AsyncMock()
        thread_manager.list_threads.return_value = [
            {
                "thread_id": "thread-1",
                "created_at": "2026-03-25T00:00:00+00:00",
                "updated_at": "2026-03-25T00:10:00+00:00",
                "subject": "Nightly Check",
            },
            {
                "thread_id": "thread-2",
                "created_at": "2026-03-24T00:00:00+00:00",
                "updated_at": "2026-03-24T00:10:00+00:00",
                "subject": "Other",
            },
        ]
        thread_manager.get_thread.side_effect = [
            SimpleNamespace(
                context={"schedule_id": "schedule-1", "scheduled_at": "2026-03-25T00:00:00+00:00"}
            ),
            SimpleNamespace(context={"schedule_id": "schedule-2"}),
        ]

        task_manager = AsyncMock()
        task_manager.get_task_state.return_value = TaskState(
            task_id="task-1",
            thread_id="thread-1",
            status=TaskStatus.DONE,
            metadata=TaskMetadata(
                created_at="2026-03-25T00:00:01+00:00",
                updated_at="2026-03-25T00:05:00+00:00",
            ),
        )

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=redis_client,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.TaskManager",
                return_value=task_manager,
            ),
        ):
            result = await list_schedule_runs_helper("schedule-1", limit=5)

        assert result["schedule_id"] == "schedule-1"
        assert result["total"] == 1
        assert result["runs"][0]["task_id"] == "task-1"
        assert result["runs"][0]["status"] == "done"

    @pytest.mark.asyncio
    async def test_list_schedule_runs_helper_handles_missing_task_lookup(self):
        from redis_sre_agent.core.schedule_helpers import list_schedule_runs_helper

        redis_client = AsyncMock()
        redis_client.zrevrange.side_effect = RuntimeError("ignore me")

        thread_manager = AsyncMock()
        thread_manager.list_threads.return_value = [
            {
                "thread_id": "thread-1",
                "created_at": "2026-03-25T00:00:00+00:00",
                "updated_at": "2026-03-25T00:10:00+00:00",
                "subject": None,
            }
        ]
        thread_manager.get_thread.return_value = SimpleNamespace(
            context={"schedule_id": "schedule-1"}
        )

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=redis_client,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.TaskManager",
                return_value=AsyncMock(),
            ),
        ):
            result = await list_schedule_runs_helper("schedule-1", limit=5)

        assert result["runs"][0]["task_id"] is None
        assert result["runs"][0]["status"] == "queued"
        assert result["runs"][0]["subject"] == "Scheduled Run"

    @pytest.mark.asyncio
    async def test_list_schedule_runs_helper_handles_task_fetch_error(self):
        from redis_sre_agent.core.schedule_helpers import list_schedule_runs_helper

        redis_client = AsyncMock()
        redis_client.zrevrange.return_value = [b"task-1"]

        thread_manager = AsyncMock()
        thread_manager.list_threads.return_value = [
            {
                "thread_id": "thread-1",
                "created_at": "2026-03-25T00:00:00+00:00",
                "updated_at": "2026-03-25T00:10:00+00:00",
                "subject": "Nightly Check",
            }
        ]
        thread_manager.get_thread.return_value = SimpleNamespace(
            context={"schedule_id": "schedule-1"}
        )

        task_manager = AsyncMock()
        task_manager.get_task_state.side_effect = RuntimeError("ignore me")

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=redis_client,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.TaskManager",
                return_value=task_manager,
            ),
        ):
            result = await list_schedule_runs_helper("schedule-1", limit=5)

        assert result["runs"][0]["task_id"] == "task-1"
        assert result["runs"][0]["status"] == "queued"

    @pytest.mark.asyncio
    async def test_list_schedule_runs_helper_paginates_past_first_page(self):
        from redis_sre_agent.core.schedule_helpers import list_schedule_runs_helper

        redis_client = AsyncMock()
        redis_client.zrevrange.return_value = [b"task-2"]

        thread_manager = AsyncMock()
        thread_manager.list_threads.side_effect = [
            [
                {
                    "thread_id": "thread-1",
                    "created_at": "2026-03-24T00:00:00+00:00",
                    "updated_at": "2026-03-24T00:10:00+00:00",
                    "subject": "Other",
                }
            ],
            [
                {
                    "thread_id": "thread-2",
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "updated_at": "2026-03-25T00:10:00+00:00",
                    "subject": "Nightly Check",
                }
            ],
            [],
        ]
        thread_manager.get_thread.side_effect = [
            SimpleNamespace(context={"schedule_id": "schedule-2"}),
            SimpleNamespace(context={"schedule_id": "schedule-1"}),
        ]

        task_manager = AsyncMock()
        task_manager.get_task_state.return_value = TaskState(
            task_id="task-2",
            thread_id="thread-2",
            status=TaskStatus.DONE,
            metadata=TaskMetadata(
                created_at="2026-03-25T00:00:01+00:00",
                updated_at="2026-03-25T00:05:00+00:00",
            ),
        )

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=redis_client,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.TaskManager",
                return_value=task_manager,
            ),
            patch("redis_sre_agent.core.schedule_helpers._SCHEDULE_RUNS_PAGE_SIZE", 1),
        ):
            result = await list_schedule_runs_helper("schedule-1", limit=5)

        assert result["total"] == 1
        assert result["runs"][0]["thread_id"] == "thread-2"
        assert thread_manager.list_threads.await_args_list[1].kwargs["offset"] == 1

    @pytest.mark.asyncio
    async def test_list_schedule_runs_helper_stops_once_limit_is_reached(self):
        from redis_sre_agent.core.schedule_helpers import list_schedule_runs_helper

        redis_client = AsyncMock()
        redis_client.zrevrange.return_value = [b"task-1"]

        thread_manager = AsyncMock()
        thread_manager.list_threads.side_effect = [
            [
                {
                    "thread_id": "thread-1",
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "updated_at": "2026-03-25T00:10:00+00:00",
                    "subject": "Nightly Check",
                }
            ],
            [
                {
                    "thread_id": "thread-2",
                    "created_at": "2026-03-24T00:00:00+00:00",
                    "updated_at": "2026-03-24T00:10:00+00:00",
                    "subject": "Older Check",
                }
            ],
        ]
        thread_manager.get_thread.return_value = SimpleNamespace(
            context={"schedule_id": "schedule-1"}
        )

        task_manager = AsyncMock()
        task_manager.get_task_state.return_value = TaskState(
            task_id="task-1",
            thread_id="thread-1",
            status=TaskStatus.DONE,
            metadata=TaskMetadata(
                created_at="2026-03-25T00:00:01+00:00",
                updated_at="2026-03-25T00:05:00+00:00",
            ),
        )

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=redis_client,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.TaskManager",
                return_value=task_manager,
            ),
            patch("redis_sre_agent.core.schedule_helpers._SCHEDULE_RUNS_PAGE_SIZE", 1),
        ):
            result = await list_schedule_runs_helper("schedule-1", limit=1)

        assert result["total"] == 1
        assert result["runs"][0]["thread_id"] == "thread-1"
        assert thread_manager.list_threads.await_count == 1

    @pytest.mark.asyncio
    async def test_list_schedule_runs_helper_total_matches_returned_runs(self):
        from redis_sre_agent.core.schedule_helpers import list_schedule_runs_helper

        redis_client = AsyncMock()
        redis_client.zrevrange.side_effect = [[b"task-1"], [b"task-2"]]

        thread_manager = AsyncMock()
        thread_manager.list_threads.return_value = [
            {
                "thread_id": "thread-1",
                "created_at": "2026-03-25T00:00:00+00:00",
                "updated_at": "2026-03-25T00:10:00+00:00",
                "subject": "Latest Check",
            },
            {
                "thread_id": "thread-2",
                "created_at": "2026-03-24T00:00:00+00:00",
                "updated_at": "2026-03-24T00:10:00+00:00",
                "subject": "Older Check",
            },
        ]
        thread_manager.get_thread.side_effect = [
            SimpleNamespace(
                context={"schedule_id": "schedule-1", "scheduled_at": "2026-03-25T00:00:00+00:00"}
            ),
            SimpleNamespace(
                context={"schedule_id": "schedule-1", "scheduled_at": "2026-03-24T00:00:00+00:00"}
            ),
        ]

        task_manager = AsyncMock()
        task_manager.get_task_state.side_effect = [
            TaskState(
                task_id="task-1",
                thread_id="thread-1",
                status=TaskStatus.DONE,
                metadata=TaskMetadata(
                    created_at="2026-03-25T00:00:01+00:00",
                    updated_at="2026-03-25T00:05:00+00:00",
                ),
            ),
            TaskState(
                task_id="task-2",
                thread_id="thread-2",
                status=TaskStatus.DONE,
                metadata=TaskMetadata(
                    created_at="2026-03-24T00:00:01+00:00",
                    updated_at="2026-03-24T00:05:00+00:00",
                ),
            ),
        ]

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=redis_client,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.TaskManager",
                return_value=task_manager,
            ),
        ):
            result = await list_schedule_runs_helper("schedule-1", limit=1)

        assert len(result["runs"]) == 1
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_list_schedule_runs_helper_ignores_threads_with_missing_context(self):
        from redis_sre_agent.core.schedule_helpers import list_schedule_runs_helper

        redis_client = AsyncMock()

        thread_manager = AsyncMock()
        thread_manager.list_threads.return_value = [
            {
                "thread_id": "thread-1",
                "created_at": "2026-03-25T00:00:00+00:00",
                "updated_at": "2026-03-25T00:10:00+00:00",
                "subject": "Nightly Check",
            }
        ]
        thread_manager.get_thread.return_value = SimpleNamespace(context=None)

        with (
            patch(
                "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
                new_callable=AsyncMock,
                return_value=_schedule(),
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.get_redis_client",
                return_value=redis_client,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedule_helpers.TaskManager",
                return_value=AsyncMock(),
            ),
        ):
            result = await list_schedule_runs_helper("schedule-1", limit=5)

        assert result["schedule_id"] == "schedule-1"
        assert result["runs"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_list_schedule_runs_helper_returns_error_when_missing_schedule(self):
        from redis_sre_agent.core.schedule_helpers import list_schedule_runs_helper

        with patch(
            "redis_sre_agent.core.schedule_helpers.core_schedules.get_schedule",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await list_schedule_runs_helper("schedule-404")

        assert result == {"error": "Schedule not found", "id": "schedule-404"}

    def test_normalize_task_status_handles_strings_and_enums(self):
        from redis_sre_agent.core.schedule_helpers import (
            _build_schedule_subject,
            _normalize_task_status,
        )

        assert _normalize_task_status(TaskStatus.IN_PROGRESS) == "in_progress"
        assert _normalize_task_status("done") == "done"
        assert _normalize_task_status(None) == "queued"
        assert _build_schedule_subject({"name": "", "instructions": "First line\nSecond line"}) == (
            "First line"
        )
        assert _build_schedule_subject({"name": "", "instructions": ""}) == "Scheduled Run"

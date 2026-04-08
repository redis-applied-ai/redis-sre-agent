"""Helpers for exposing schedule workflows over MCP."""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from docket import Docket

from redis_sre_agent.core import schedules as core_schedules
from redis_sre_agent.core.helper_utils import get_docket_redis_url as get_redis_url
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.tasks import TaskManager, TaskStatus, create_task
from redis_sre_agent.core.threads import ThreadManager
from redis_sre_agent.core.turn_scope import build_legacy_target_scope_adapter

_SCHEDULE_RUNS_PAGE_SIZE = 100


def _normalize_task_status(status: Any) -> str:
    if isinstance(status, TaskStatus):
        return status.value
    if status:
        return str(status)
    return TaskStatus.QUEUED.value


def _build_schedule_subject(schedule: Dict[str, Any]) -> str:
    subject = (schedule.get("name") or "").strip()
    if subject:
        return subject

    instructions = (schedule.get("instructions") or "").strip()
    if instructions:
        return instructions.splitlines()[0][:80]

    return "Scheduled Run"


def _build_manual_run_context(
    schedule_id: str, schedule: Dict[str, Any], current_time: datetime
) -> Dict[str, Any]:
    _, scope_context = build_legacy_target_scope_adapter(
        instance_id=schedule.get("redis_instance_id"),
        automation_mode="automated",
        resolution_policy=(
            "require_target" if schedule.get("redis_instance_id") else "allow_zero_scope"
        ),
    )
    context = {
        "schedule_id": schedule_id,
        "schedule_name": schedule.get("name"),
        "automated": True,
        "manual_trigger": True,
        "original_query": schedule.get("instructions"),
        "scheduled_at": current_time.isoformat(),
    }
    context.update(scope_context)
    return context


def _get_schedule_task_callable() -> Any:
    """Resolve the schedule task callable without a module import cycle."""
    from redis_sre_agent.core.docket_tasks import process_agent_turn

    return process_agent_turn


async def list_schedules_helper(limit: int = 50) -> Dict[str, Any]:
    schedules = await core_schedules.list_schedules()
    return {"schedules": schedules[:limit], "total": len(schedules), "limit": limit}


async def get_schedule_helper(schedule_id: str) -> Dict[str, Any]:
    schedule = await core_schedules.get_schedule(schedule_id)
    if not schedule:
        return {"error": "Schedule not found", "id": schedule_id}
    return schedule


async def create_schedule_helper(
    *,
    name: str,
    interval_type: str,
    interval_value: int,
    instructions: str,
    redis_instance_id: Optional[str] = None,
    description: Optional[str] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    schedule = core_schedules.Schedule(
        name=name,
        description=description,
        interval_type=interval_type.lower(),
        interval_value=interval_value,
        redis_instance_id=redis_instance_id,
        instructions=instructions,
        enabled=enabled,
    )
    schedule.next_run_at = schedule.calculate_next_run().isoformat()
    schedule.updated_at = datetime.now(timezone.utc).isoformat()

    if not await core_schedules.store_schedule(schedule.model_dump()):
        raise RuntimeError("Failed to store schedule")

    return {"id": schedule.id, "status": "created"}


async def update_schedule_helper(
    schedule_id: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    instructions: Optional[str] = None,
    redis_instance_id: Optional[str] = None,
    interval_type: Optional[str] = None,
    interval_value: Optional[int] = None,
    enabled: Optional[bool] = None,
    recalc_next_run: bool = True,
) -> Dict[str, Any]:
    current = await core_schedules.get_schedule(schedule_id)
    if not current:
        raise RuntimeError("Schedule not found")

    data = dict(current)
    if name is not None:
        data["name"] = name
    if description is not None:
        data["description"] = description
    if instructions is not None:
        data["instructions"] = instructions
    if redis_instance_id is not None:
        data["redis_instance_id"] = redis_instance_id
    if interval_type is not None:
        data["interval_type"] = interval_type.lower()
    if interval_value is not None:
        data["interval_value"] = interval_value
    if enabled is not None:
        data["enabled"] = bool(enabled)

    data["id"] = current.get("id")
    data["created_at"] = current.get("created_at")
    schedule = core_schedules.Schedule(**data)

    changed_interval = interval_type is not None or interval_value is not None
    was_disabled = not current.get("enabled", True)
    if recalc_next_run and (changed_interval or (enabled is True and was_disabled)):
        schedule.next_run_at = schedule.calculate_next_run().isoformat()

    schedule.updated_at = datetime.now(timezone.utc).isoformat()

    if not await core_schedules.store_schedule(schedule.model_dump()):
        raise RuntimeError("Failed to store updated schedule")

    return {"id": schedule.id, "status": "updated"}


async def enable_schedule_helper(schedule_id: str) -> Dict[str, Any]:
    current = await core_schedules.get_schedule(schedule_id)
    if not current:
        raise RuntimeError("Schedule not found")

    current["enabled"] = True
    schedule = core_schedules.Schedule(**current)
    if not schedule.next_run_at:
        schedule.next_run_at = schedule.calculate_next_run().isoformat()
    schedule.updated_at = datetime.now(timezone.utc).isoformat()

    if not await core_schedules.store_schedule(schedule.model_dump()):
        raise RuntimeError("Failed to store enabled schedule")

    return {"id": schedule.id, "status": "enabled"}


async def disable_schedule_helper(schedule_id: str) -> Dict[str, Any]:
    current = await core_schedules.get_schedule(schedule_id)
    if not current:
        raise RuntimeError("Schedule not found")

    current["enabled"] = False
    schedule = core_schedules.Schedule(**current)
    schedule.updated_at = datetime.now(timezone.utc).isoformat()

    if not await core_schedules.store_schedule(schedule.model_dump()):
        raise RuntimeError("Failed to store disabled schedule")

    return {"id": schedule.id, "status": "disabled"}


async def delete_schedule_helper(schedule_id: str, *, confirm: bool = False) -> Dict[str, Any]:
    if not confirm:
        return {"error": "Confirmation required", "id": schedule_id, "status": "cancelled"}

    schedule = await core_schedules.get_schedule(schedule_id)
    if not schedule:
        raise RuntimeError("Schedule not found")

    if not await core_schedules.delete_schedule(schedule_id):
        raise RuntimeError("Delete failed or schedule not found")

    return {"id": schedule_id, "status": "deleted"}


async def run_schedule_now_helper(schedule_id: str) -> Dict[str, Any]:
    schedule = await core_schedules.get_schedule(schedule_id)
    if not schedule:
        return {"error": "Schedule not found", "id": schedule_id}

    current_time = datetime.now(timezone.utc)
    run_context = _build_manual_run_context(schedule_id, schedule, current_time)

    redis_client = get_redis_client()
    thread_manager = ThreadManager(redis_client=redis_client)
    thread_id = await thread_manager.create_thread(
        user_id="scheduler",
        session_id=f"manual_schedule_{schedule_id}_{current_time.strftime('%Y%m%d_%H%M%S')}",
        initial_context=run_context,
        tags=["automated", "scheduled", "manual_trigger"],
    )
    try:
        await thread_manager.set_thread_subject(thread_id, _build_schedule_subject(schedule))
    except Exception:
        pass

    task_result = await create_task(
        message=schedule.get("instructions") or "",
        thread_id=thread_id,
        context=run_context,
        redis_client=redis_client,
    )
    task_id = str(task_result["task_id"])
    docket_task_id = None
    async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
        task_key = f"manual_schedule_{schedule_id}_{current_time.strftime('%Y%m%d_%H%M%S')}"
        try:
            task_func = docket.add(_get_schedule_task_callable(), key=task_key)
            if inspect.isawaitable(task_func):
                task_func = await task_func
            docket_task_id = await task_func(
                thread_id=thread_id,
                message=schedule.get("instructions") or "",
                context=run_context,
                task_id=task_id,
            )
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                docket_task_id = "already_running"
            else:
                raise

    return {
        "schedule_id": schedule_id,
        "status": "pending",
        "scheduled_at": current_time.isoformat(),
        "thread_id": thread_id,
        "task_id": task_id,
        "docket_task_id": str(docket_task_id) if docket_task_id is not None else None,
    }


async def list_schedule_runs_helper(schedule_id: str, limit: int = 50) -> Dict[str, Any]:
    schedule = await core_schedules.get_schedule(schedule_id)
    if not schedule:
        return {"error": "Schedule not found", "id": schedule_id}

    redis_client = get_redis_client()
    thread_manager = ThreadManager(redis_client=redis_client)
    task_manager = TaskManager(redis_client=redis_client)

    runs = []
    offset = 0

    while True:
        summaries = await thread_manager.list_threads(
            user_id="scheduler",
            limit=_SCHEDULE_RUNS_PAGE_SIZE,
            offset=offset,
        )
        if not summaries:
            break

        offset += len(summaries)
        states = await asyncio.gather(
            *(thread_manager.get_thread(summary["thread_id"]) for summary in summaries),
            return_exceptions=True,
        )

        matching_runs: list[tuple[Dict[str, Any], Dict[str, Any]]] = []
        for summary, state in zip(summaries, states):
            if isinstance(state, Exception) or not state:
                continue
            context = state.context or {}
            if context.get("schedule_id") != schedule_id:
                continue
            matching_runs.append((summary, context))

        task_id_results = await asyncio.gather(
            *(
                redis_client.zrevrange(RedisKeys.thread_tasks_index(summary["thread_id"]), 0, 0)
                for summary, _ in matching_runs
            ),
            return_exceptions=True,
        )

        task_ids: list[str | None] = []
        for task_id_result in task_id_results:
            if isinstance(task_id_result, Exception) or not task_id_result:
                task_ids.append(None)
                continue
            task_id = task_id_result[0]
            task_ids.append(task_id.decode() if isinstance(task_id, bytes) else task_id)

        task_state_results = await asyncio.gather(
            *(
                task_manager.get_task_state(task_id) if task_id else asyncio.sleep(0, result=None)
                for task_id in task_ids
            ),
            return_exceptions=True,
        )

        for (summary, context), task_id, task_state in zip(
            matching_runs, task_ids, task_state_results
        ):
            task_status = TaskStatus.QUEUED.value
            started_at = summary.get("created_at")
            completed_at = None
            error = None

            if not isinstance(task_state, Exception) and task_state:
                task_status = _normalize_task_status(task_state.status)
                started_at = task_state.metadata.created_at or started_at
                if task_status == TaskStatus.DONE.value:
                    completed_at = task_state.metadata.updated_at
                error = task_state.error_message

            runs.append(
                {
                    "thread_id": summary["thread_id"],
                    "task_id": task_id,
                    "schedule_id": schedule_id,
                    "status": task_status,
                    "scheduled_at": context.get("scheduled_at") or summary.get("created_at"),
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "created_at": summary.get("created_at"),
                    "subject": summary.get("subject") or "Scheduled Run",
                    "error": error,
                }
            )

        if len(runs) >= limit:
            break
        if len(summaries) < _SCHEDULE_RUNS_PAGE_SIZE:
            break

    runs.sort(key=lambda run: run.get("scheduled_at") or "", reverse=True)
    limited_runs = runs[:limit]
    return {
        "schedule_id": schedule_id,
        "runs": limited_runs,
        "total": len(limited_runs),
        "limit": limit,
    }

"""Helpers for exposing schedule workflows over MCP."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from docket import Docket

from redis_sre_agent.core import schedules as core_schedules
from redis_sre_agent.core.docket_tasks import get_redis_url, process_agent_turn
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.tasks import TaskManager, TaskStatus
from redis_sre_agent.core.threads import ThreadManager


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
    context = {
        "schedule_id": schedule_id,
        "schedule_name": schedule.get("name"),
        "automated": True,
        "manual_trigger": True,
        "original_query": schedule.get("instructions"),
        "scheduled_at": current_time.isoformat(),
    }
    if schedule.get("redis_instance_id"):
        context["instance_id"] = schedule["redis_instance_id"]
    return context


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

    docket_task_id = None
    async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
        task_key = f"manual_schedule_{schedule_id}_{current_time.strftime('%Y%m%d_%H%M%S')}"
        try:
            task_func = docket.add(process_agent_turn, key=task_key)
            if inspect.isawaitable(task_func):
                task_func = await task_func
            docket_task_id = await task_func(
                thread_id=thread_id,
                message=schedule.get("instructions") or "",
                context=run_context,
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
        "docket_task_id": str(docket_task_id) if docket_task_id is not None else None,
    }


async def list_schedule_runs_helper(schedule_id: str, limit: int = 50) -> Dict[str, Any]:
    schedule = await core_schedules.get_schedule(schedule_id)
    if not schedule:
        return {"error": "Schedule not found", "id": schedule_id}

    redis_client = get_redis_client()
    thread_manager = ThreadManager(redis_client=redis_client)
    task_manager = TaskManager(redis_client=redis_client)

    summaries = await thread_manager.list_threads(user_id="scheduler", limit=200)
    runs = []

    for summary in summaries:
        thread_id = summary["thread_id"]
        state = await thread_manager.get_thread(thread_id)
        if not state or state.context.get("schedule_id") != schedule_id:
            continue

        task_id = None
        task_status = TaskStatus.QUEUED.value
        started_at = summary.get("created_at")
        completed_at = None
        error = None

        try:
            task_ids = await redis_client.zrevrange(RedisKeys.thread_tasks_index(thread_id), 0, 0)
            if task_ids:
                task_id = task_ids[0]
                if isinstance(task_id, bytes):
                    task_id = task_id.decode()
        except Exception:
            task_id = None

        if task_id:
            try:
                task = await task_manager.get_task_state(task_id)
            except Exception:
                task = None
            if task:
                task_status = _normalize_task_status(task.status)
                started_at = task.metadata.created_at or started_at
                if task_status == TaskStatus.DONE.value:
                    completed_at = task.metadata.updated_at
                error = task.error_message

        runs.append(
            {
                "thread_id": thread_id,
                "task_id": task_id,
                "schedule_id": schedule_id,
                "status": task_status,
                "scheduled_at": state.context.get("scheduled_at") or summary.get("created_at"),
                "started_at": started_at,
                "completed_at": completed_at,
                "created_at": summary.get("created_at"),
                "subject": summary.get("subject") or "Scheduled Run",
                "error": error,
            }
        )

    runs.sort(key=lambda run: run.get("scheduled_at") or "", reverse=True)
    return {"schedule_id": schedule_id, "runs": runs[:limit], "total": len(runs), "limit": limit}

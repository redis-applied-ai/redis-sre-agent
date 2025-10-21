"""Domain-level helpers for task lifecycle (non-HTTP logic).

These helpers encapsulate the core behavior the API currently performs so
CLIs, demos, and other callers can invoke task functionality without
running the HTTP server.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from docket import Docket

from redis_sre_agent.core.docket_tasks import get_redis_url, process_agent_turn
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.task_state import TaskManager
from redis_sre_agent.core.thread_state import (
    ThreadManager,
    ThreadStatus,
)

logger = logging.getLogger(__name__)


async def create_task(
    *,
    message: str,
    thread_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    redis_client=None,
) -> Dict[str, Any]:
    """Create a Task and queue processing.

    If thread_id is not provided, create a new thread first. Returns both task_id and thread_id.
    """
    if redis_client is None:
        redis_client = get_redis_client()

    thread_manager = ThreadManager(redis_client=redis_client)

    # Ensure we have a thread
    created_new_thread = False
    if not thread_id:
        thread_id = await thread_manager.create_thread(
            initial_context={"messages": [], **(context or {})}
        )
        created_new_thread = True
        # Subject generation is optional here; can be done by processor turn as well
        try:
            await thread_manager.update_thread_subject(thread_id, message)
        except Exception:
            pass

    # Pre-create a per-turn task id so API can return it immediately
    tm = TaskManager(redis_client=redis_client)
    # user_id is stored on thread metadata; best-effort fetch
    state = await thread_manager.get_thread_state(thread_id)
    task_id = await tm.create_task(
        thread_id=thread_id,
        user_id=(state.metadata.user_id if state else None),
        subject=message,
    )

    # Queue processing and pass the task_id so the worker reuses it
    async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
        task_func = docket.add(process_agent_turn)
        await task_func(
            thread_id=thread_id, message=message, context=context or {}, task_id=task_id
        )
        logger.info(f"Queued agent task {task_id} for thread {thread_id}")

    # Ensure thread shows as queued now
    await thread_manager.update_thread_status(thread_id, ThreadStatus.QUEUED)
    await tm.update_task_status(task_id, ThreadStatus.QUEUED)

    return {
        "task_id": task_id,
        "thread_id": thread_id,
        "status": ThreadStatus.QUEUED,
        "message": "Task created and queued for processing"
        if not created_new_thread
        else "Thread created; task queued",
    }


async def get_task_status(*, thread_id: str, redis_client=None) -> Dict[str, Any]:
    """Return a dict representing the task status (compatible with TaskStatusResponse)."""
    if redis_client is None:
        redis_client = get_redis_client()

    thread_manager = ThreadManager(redis_client=redis_client)

    thread_state = await thread_manager.get_thread_state(thread_id)
    if not thread_state:
        raise ValueError(f"Thread {thread_id} not found")

    updates = [
        {
            "timestamp": update.timestamp,
            "message": update.message,
            "type": update.update_type,
            "metadata": update.metadata or {},
        }
        for update in thread_state.updates
    ]

    action_items = [
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "priority": item.priority,
            "category": item.category,
            "completed": item.completed,
            "due_date": item.due_date,
        }
        for item in thread_state.action_items
    ]

    metadata = {
        "created_at": thread_state.metadata.created_at,
        "updated_at": thread_state.metadata.updated_at,
        "user_id": thread_state.metadata.user_id,
        "session_id": thread_state.metadata.session_id,
        "priority": thread_state.metadata.priority,
        "tags": thread_state.metadata.tags,
        "subject": thread_state.metadata.subject,
    }

    return {
        "thread_id": thread_id,
        "status": thread_state.status,
        "updates": updates,
        "result": thread_state.result,
        "action_items": action_items,
        "error_message": thread_state.error_message,
        "metadata": metadata,
        "context": thread_state.context,
    }


async def get_task_by_id(*, task_id: str, redis_client=None) -> Dict[str, Any]:
    """Return a dict representing a single task by task_id.

    This is task-centric (not thread), using TaskManager.get_task_state.
    """
    if redis_client is None:
        redis_client = get_redis_client()

    task_manager = TaskManager(redis_client=redis_client)
    task_state = await task_manager.get_task_state(task_id)
    if not task_state:
        raise ValueError(f"Task {task_id} not found")

    updates = [
        {
            "timestamp": u.timestamp,
            "message": u.message,
            "type": u.update_type,
            "metadata": u.metadata or {},
        }
        for u in (task_state.updates or [])
    ]

    metadata = {
        "created_at": task_state.metadata.created_at,
        "updated_at": task_state.metadata.updated_at,
        "user_id": task_state.metadata.user_id,
        "subject": task_state.metadata.subject,
    }

    return {
        "task_id": task_state.task_id,
        "thread_id": task_state.thread_id,
        "status": task_state.status,
        "updates": updates,
        "result": task_state.result,
        "error_message": task_state.error_message,
        "metadata": metadata,
        "context": {},
    }


async def list_tasks(
    *,
    user_id: Optional[str] = None,
    status_filter: Optional[ThreadStatus] = None,
    show_all: bool = False,
    limit: int = 50,
    redis_client=None,
) -> List[Dict[str, Any]]:
    """List recent tasks with optional filters.

    Returns a list of dicts compatible with TaskStatusResponse.
    """
    if redis_client is None:
        redis_client = get_redis_client()

    thread_manager = ThreadManager(redis_client=redis_client)

    # Try to build instance name map for display enrichment
    _instance_name_map: Dict[str, str] = {}
    try:
        from redis_sre_agent.api.instances import get_instances_from_redis

        instances = await get_instances_from_redis()
        _instance_name_map = {inst.id: inst.name for inst in instances}
    except Exception:
        pass

    # Prefer RedisVL FT.SEARCH on tasks index
    try:
        from datetime import datetime, timezone

        from redisvl.query import FilterQuery
        from redisvl.query.filter import Tag

        from redis_sre_agent.core.redis import get_tasks_index

        index = await get_tasks_index()

        # Build filter expression
        if show_all:
            expr = Tag("user_id") == user_id if user_id else None
        else:
            if status_filter:
                expr = Tag("status") == status_filter.value
            else:
                expr = (Tag("status") == ThreadStatus.IN_PROGRESS.value) | (
                    Tag("status") == ThreadStatus.QUEUED.value
                )
            if user_id:
                expr = expr & (Tag("user_id") == user_id)

        fq = FilterQuery(
            return_fields=[
                "id",
                "status",
                "subject",
                "user_id",
                "thread_id",
                "created_at",
                "updated_at",
            ],
            filter_expression=expr,
            num_results=limit,
        ).sort_by("updated_at", asc=False)

        results = await index.query(fq)

        def _iso(ts) -> str | None:
            try:
                tsf = float(ts)
                if tsf > 0:
                    return datetime.fromtimestamp(tsf, tz=timezone.utc).isoformat()
            except Exception:
                return None
            return None

        tasks: List[Dict[str, Any]] = []
        for res in results:
            row = (
                res
                if isinstance(res, dict)
                else {
                    k: getattr(res, k, None)
                    for k in [
                        "id",
                        "status",
                        "subject",
                        "user_id",
                        "thread_id",
                        "created_at",
                        "updated_at",
                    ]
                }
            )
            redis_key = row.get("id", "")
            task_id = (
                redis_key[len("sre_tasks:") :]
                if isinstance(redis_key, str) and redis_key.startswith("sre_tasks:")
                else redis_key
            )

            created_iso = _iso(row.get("created_at"))
            updated_iso = _iso(row.get("updated_at"))

            metadata = {
                "created_at": created_iso,
                "updated_at": updated_iso,
                "user_id": row.get("user_id"),
                "session_id": None,
                "priority": 0,
                "tags": [],
                "subject": row.get("subject") or "Untitled",
            }

            tasks.append(
                {
                    "task_id": task_id,
                    "thread_id": row.get("thread_id"),
                    "status": ThreadStatus(row.get("status", ThreadStatus.QUEUED.value)),
                    "updates": [],
                    "result": None,
                    "action_items": [],
                    "error_message": None,
                    "metadata": metadata,
                    "context": {},
                }
            )

        # Enrich with thread subject
        try:
            from redis_sre_agent.core.keys import RedisKeys

            for t in tasks:
                thid = t.get("thread_id")
                if not thid:
                    continue
                subj = await redis_client.hget(RedisKeys.thread_metadata(thid), "subject")
                if isinstance(subj, bytes):
                    subj = subj.decode()
                if subj:
                    t["metadata"]["thread_subject"] = subj
        except Exception:
            pass

        return tasks
    except Exception:
        # Fallback to threads-based listing (legacy)
        statuses: Optional[List[ThreadStatus]]
        if show_all:
            statuses = None
        elif status_filter:
            statuses = [status_filter]
        else:
            statuses = [ThreadStatus.IN_PROGRESS, ThreadStatus.QUEUED]

        fetch_size = max(limit * 10, 200)
        raw_summaries = await thread_manager.list_threads(
            user_id=user_id, status_filter=None, limit=fetch_size, offset=0
        )
        if statuses is None:
            thread_summaries = raw_summaries[:limit]
        else:
            allowed = {s.value for s in statuses}
            thread_summaries = [s for s in raw_summaries if s.get("status") in allowed][:limit]

        tasks: List[Dict[str, Any]] = []
        for summary in thread_summaries:
            metadata = {
                "created_at": summary.get("created_at"),
                "updated_at": summary.get("updated_at"),
                "user_id": summary.get("user_id"),
                "session_id": None,
                "priority": summary.get("priority", 0),
                "tags": summary.get("tags", []),
                "subject": summary.get("subject", "Untitled"),
                "thread_subject": summary.get("subject", "Untitled"),
            }
            tasks.append(
                {
                    "task_id": None,
                    "thread_id": summary["thread_id"],
                    "status": ThreadStatus(summary["status"]),
                    "updates": [],
                    "result": None,
                    "action_items": [],
                    "error_message": None,
                    "metadata": metadata,
                    "context": {},
                }
            )

        return tasks

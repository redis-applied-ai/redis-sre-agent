"""Domain-level helpers for task lifecycle (non-HTTP logic).

These helpers encapsulate the core behavior the API currently performs so
CLIs, demos, and other callers can invoke task functionality without
running the HTTP server.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.thread_state import (
    ThreadManager,
    ThreadStatus,
)

logger = logging.getLogger(__name__)


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


async def list_tasks(
    *,
    user_id: Optional[str] = None,
    status_filter: Optional[ThreadStatus] = None,
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
    instance_name_map: Dict[str, str] = {}
    try:
        from redis_sre_agent.api.instances import get_instances_from_redis

        instances = await get_instances_from_redis()
        instance_name_map = {inst.id: inst.name for inst in instances}
    except Exception:
        pass

    thread_summaries = await thread_manager.list_threads(
        user_id=user_id, status_filter=status_filter, limit=limit, offset=0
    )

    tasks: List[Dict[str, Any]] = []
    for summary in thread_summaries:
        # Minimal update for list view
        updates = [
            {
                "timestamp": summary.get("updated_at", summary.get("created_at")),
                "message": summary.get("latest_message", "No updates"),
                "type": "summary",
                "metadata": {},
            }
        ]

        metadata = {
            "created_at": summary.get("created_at"),
            "updated_at": summary.get("updated_at"),
            "user_id": summary.get("user_id"),
            "session_id": None,
            "priority": summary.get("priority", 0),
            "tags": summary.get("tags", []),
            "subject": summary.get("subject", "Untitled"),
        }

        context: Dict[str, Any] = {}
        instance_id = summary.get("instance_id")
        if instance_id:
            context["instance_id"] = instance_id
            name = instance_name_map.get(instance_id)
            if name:
                context["instance_name"] = name

        # For scheduled tasks, try to get more context (e.g., original_query)
        if summary.get("user_id") == "scheduler":
            try:
                thread_state = await thread_manager.get_thread_state(summary["thread_id"])
                if thread_state:
                    for k, v in (thread_state.context or {}).items():
                        context.setdefault(k, v)
                    if (thread_state.context or {}).get("original_query"):
                        context["original_query"] = thread_state.context["original_query"]
            except Exception:
                pass

        tasks.append(
            {
                "thread_id": summary["thread_id"],
                "status": ThreadStatus(summary["status"]),
                "updates": updates,
                "result": None,
                "action_items": [],
                "error_message": None,
                "metadata": metadata,
                "context": context,
            }
        )

    return tasks

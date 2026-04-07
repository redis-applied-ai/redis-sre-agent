"""Shared helpers for direct task inspection MCP tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from redis_sre_agent.core.tasks import TaskStatus, get_task_by_id, list_tasks


def _normalize_status(status: Any) -> Optional[str]:
    """Convert task statuses into MCP-friendly strings."""
    if status is None:
        return None
    if isinstance(status, TaskStatus):
        return status.value
    return str(status)


def _normalize_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize task payloads returned by core task APIs."""
    normalized = dict(task)
    normalized["status"] = _normalize_status(task.get("status"))
    normalized["tool_calls"] = task.get("tool_calls") or []
    return normalized


def _coerce_status_filter(status: Optional[str]) -> Optional[TaskStatus]:
    """Parse an optional task status filter."""
    if status is None:
        return None
    try:
        return TaskStatus(status)
    except ValueError as exc:
        raise ValueError(f"Invalid task status filter: {status}") from exc


def _clamp_limit(limit: int) -> int:
    """Clamp list limits to a small, predictable range."""
    return max(1, min(limit, 100))


async def get_task_helper(task_id: str) -> Dict[str, Any]:
    """Return a normalized task payload."""
    task = await get_task_by_id(task_id=task_id)
    return _normalize_task(task)


async def list_tasks_helper(
    *,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    show_all: bool = False,
    limit: int = 50,
) -> Dict[str, Any]:
    """List tasks using the shared core task API."""
    normalized_limit = _clamp_limit(limit)
    status_filter = _coerce_status_filter(status)
    tasks = await list_tasks(
        user_id=user_id,
        status_filter=status_filter,
        show_all=show_all,
        limit=normalized_limit,
    )
    normalized_tasks = [_normalize_task(task) for task in tasks]
    return {
        "tasks": normalized_tasks,
        "count": len(normalized_tasks),
        "user_id": user_id,
        "status": status_filter.value if status_filter else None,
        "show_all": show_all,
        "limit": normalized_limit,
    }

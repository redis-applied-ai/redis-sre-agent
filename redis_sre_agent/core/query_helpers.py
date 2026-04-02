"""Shared helpers for the unified query MCP tool."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Dict, Optional

from docket import Docket

from redis_sre_agent.core.clusters import get_cluster_by_id
from redis_sre_agent.core.helper_utils import get_docket_redis_url as get_redis_url
from redis_sre_agent.core.instances import get_instance_by_id
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.support_package_helpers import get_support_package_manager
from redis_sre_agent.core.tasks import create_task
from redis_sre_agent.core.threads import ThreadManager

VALID_QUERY_AGENTS = {"auto", "triage", "chat", "knowledge"}


def _normalize_agent_selection(agent: Optional[str]) -> str:
    normalized = (agent or "auto").strip().lower()
    if normalized not in VALID_QUERY_AGENTS:
        valid = ", ".join(sorted(VALID_QUERY_AGENTS))
        raise ValueError(f"Invalid agent '{agent}'. Valid values: {valid}")
    return normalized


def _get_query_task_callable() -> Any:
    """Resolve the unified query task callable without a module import cycle."""
    from redis_sre_agent.core.docket_tasks import process_agent_turn

    return process_agent_turn


async def _validate_thread(thread_id: str, *, redis_client: Any) -> None:
    thread_manager = ThreadManager(redis_client=redis_client)
    thread = await thread_manager.get_thread(thread_id)
    if not thread:
        raise ValueError(f"Thread {thread_id} not found")


async def _resolve_support_package_context(support_package_id: str) -> Dict[str, str]:
    manager = get_support_package_manager()
    metadata = await manager.get_metadata(support_package_id)
    if not metadata:
        raise ValueError(f"Support package not found: {support_package_id}")

    support_package_path = await manager.extract(support_package_id)
    return {
        "support_package_id": support_package_id,
        "support_package_path": str(Path(support_package_path)),
    }


async def queue_query_task_helper(
    *,
    query: str,
    instance_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    support_package_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    agent: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create and queue a unified query task with routing/thread semantics."""
    agent_selection = _normalize_agent_selection(agent)
    if instance_id and cluster_id:
        raise ValueError("Please provide only one of instance_id or cluster_id")

    redis_client = get_redis_client()
    if thread_id:
        await _validate_thread(thread_id, redis_client=redis_client)

    if instance_id:
        instance = await get_instance_by_id(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")

    if cluster_id:
        cluster = await get_cluster_by_id(cluster_id)
        if not cluster:
            raise ValueError(f"Cluster not found: {cluster_id}")

    thread_context: Dict[str, Any] = {}
    if instance_id:
        thread_context["instance_id"] = instance_id
    if cluster_id:
        thread_context["cluster_id"] = cluster_id
    if user_id:
        thread_context["user_id"] = user_id
    if support_package_id:
        thread_context.update(await _resolve_support_package_context(support_package_id))

    turn_context = dict(thread_context)
    if agent_selection != "auto":
        turn_context["requested_agent_type"] = agent_selection

    result = await create_task(
        message=query,
        thread_id=thread_id,
        context=thread_context or None,
        redis_client=redis_client,
    )

    async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
        task_func = docket.add(_get_query_task_callable(), key=result["task_id"])
        if inspect.isawaitable(task_func):
            task_func = await task_func
        await task_func(
            thread_id=result["thread_id"],
            message=query,
            context=turn_context or None,
            task_id=result["task_id"],
        )

    return {
        "thread_id": result["thread_id"],
        "task_id": result["task_id"],
        "status": result["status"].value
        if hasattr(result["status"], "value")
        else str(result["status"]),
        "message": "Query task queued for processing",
        "agent": agent_selection,
    }

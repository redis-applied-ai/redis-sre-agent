"""Thread lifecycle helpers (non-HTTP).

Encapsulates creating, continuing, cancelling, and deleting threads so
callers (CLI, demos) can orchestrate agent work without running the API.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from docket import Docket

from redis_sre_agent.core.docket_tasks import get_redis_url, process_agent_turn
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.thread_state import ThreadManager

logger = logging.getLogger(__name__)


async def _build_initial_context(
    query: str,
    priority: int = 0,
    base_context: Optional[Dict[str, Any]] = None,
    instance_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create the initial context dict used when starting a thread.

    Optionally enrich with instance name when instance_id is provided.
    """
    initial_context: Dict[str, Any] = {
        "original_query": query,
        "priority": priority,
        "messages": [],
    }
    if base_context:
        initial_context.update(base_context)

    if instance_id:
        initial_context["instance_id"] = instance_id
        try:
            # Import locally to avoid import cycles at module import time
            from redis_sre_agent.api.instances import get_instances_from_redis

            instances = await get_instances_from_redis()
            for inst in instances:
                if inst.id == instance_id:
                    initial_context["instance_name"] = inst.name
                    break
        except Exception as e:
            logger.debug(f"Could not enrich context with instance name: {e}")

    return initial_context


async def create_thread(
    *,
    query: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    priority: int = 0,
    tags: Optional[list[str]] = None,
    instance_id: Optional[str] = None,
    redis_client=None,
) -> Dict[str, Any]:
    """Create a thread and queue the agent to process the initial query.

    Returns a dict with keys: thread_id, message, estimated_completion, context.
    """
    if redis_client is None:
        redis_client = get_redis_client()

    thread_manager = ThreadManager(redis_client=redis_client)

    # Prepare initial context
    initial_context = await _build_initial_context(
        query=query, priority=priority, base_context=context, instance_id=instance_id
    )

    # Create thread
    thread_id = await thread_manager.create_thread(
        user_id=user_id,
        session_id=session_id,
        initial_context=initial_context,
        tags=tags or [],
    )

    # Generate and update thread subject
    await thread_manager.update_thread_subject(thread_id, query)

    # Queue the agent processing task
    async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
        task_func = docket.add(process_agent_turn)
        await task_func(thread_id=thread_id, message=query, context=initial_context)
        logger.info(f"Queued agent task for thread {thread_id}")

    # No thread status; return metadata only
    return {
        "thread_id": thread_id,
        "message": "Thread created and queued for analysis",
        "estimated_completion": "2-5 minutes",
        "context": initial_context,
    }


async def continue_thread(
    *, thread_id: str, query: str, context: Optional[Dict[str, Any]] = None, redis_client=None
) -> Dict[str, Any]:
    """Queue another agent processing turn for an existing thread."""
    if redis_client is None:
        redis_client = get_redis_client()

    thread_manager = ThreadManager(redis_client=redis_client)

    thread_state = await thread_manager.get_thread_state(thread_id)
    if not thread_state:
        raise ValueError(f"Thread {thread_id} not found")

    # Threads have no status; allow continuation without status checks

    async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
        task_func = docket.add(process_agent_turn)
        await task_func(thread_id=thread_id, message=query, context=context)
        logger.info(f"Queued continuation task for thread {thread_id}")

    # No thread status; return metadata only
    return {
        "thread_id": thread_id,
        "message": "Continuation queued for processing",
        "estimated_completion": "2-5 minutes",
    }


async def cancel_thread(*, thread_id: str, redis_client=None) -> Dict[str, Any]:
    """Mark a thread as cancelled and add a cancellation update."""
    if redis_client is None:
        redis_client = get_redis_client()

    thread_manager = ThreadManager(redis_client=redis_client)
    thread_state = await thread_manager.get_thread_state(thread_id)
    if not thread_state:
        raise ValueError(f"Thread {thread_id} not found")

    # Threads have no status; perform a best-effort cancellation marker only

    await thread_manager.add_thread_update(
        thread_id, "Task cancelled by user request", "cancellation"
    )
    logger.info(f"Cancelled thread {thread_id}")
    return {"cancelled": True}


async def delete_thread(*, thread_id: str, redis_client=None) -> Dict[str, Any]:
    """Permanently delete a thread."""
    if redis_client is None:
        redis_client = get_redis_client()

    thread_manager = ThreadManager(redis_client=redis_client)

    thread_state = await thread_manager.get_thread_state(thread_id)
    if not thread_state:
        raise ValueError(f"Thread {thread_id} not found")

    success = await thread_manager.delete_thread(thread_id)
    if not success:
        raise RuntimeError(f"Failed to delete thread {thread_id}")

    logger.info(f"Deleted thread {thread_id}")
    return {"deleted": True}


# TODO: archive_thread/thread soft-delete semantics if needed.

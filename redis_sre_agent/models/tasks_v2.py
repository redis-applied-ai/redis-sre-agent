"""Task lifecycle helpers (v2).

Create a per-turn Task optionally creating a Thread first, then queue processing.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from docket import Docket

from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.task_state import TaskManager
from redis_sre_agent.core.tasks import get_redis_url, process_agent_turn
from redis_sre_agent.core.thread_state import ThreadManager, ThreadStatus

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
        thread_id=thread_id, user_id=(state.metadata.user_id if state else None)
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

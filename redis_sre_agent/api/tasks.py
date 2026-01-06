"""Task API: create task and get task by id.

Separate from legacy endpoints that returned status by thread.
"""

from __future__ import annotations

import logging

from docket import Docket
from fastapi import APIRouter, HTTPException, status

from redis_sre_agent.api.schemas import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskResponse,
)
from redis_sre_agent.core.docket_tasks import get_redis_url, process_agent_turn
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.tasks import TaskManager, create_task
from redis_sre_agent.core.tasks import delete_task as delete_task_core

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/tasks", response_model=TaskCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task_endpoint(req: TaskCreateRequest) -> TaskCreateResponse:
    try:
        redis_client = get_redis_client()
        data = await create_task(
            message=req.message,
            thread_id=req.thread_id,
            context=req.context,
            redis_client=redis_client,
        )
        task = TaskCreateResponse(**data)

        if not task.thread_id:
            logger.error("create_task returned no thread_id; refusing to queue turn")
            raise HTTPException(status_code=500, detail="Failed to create thread for task")

        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            # Use the task_id as the Docket key so we can cancel by task_id later.
            task_func = docket.add(process_agent_turn, key=task.task_id)
            await task_func(
                thread_id=task.thread_id,
                message=req.message,
                context=req.context or {},
                task_id=task.task_id,
            )

        return task
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    redis_client = get_redis_client()
    task_manager = TaskManager(redis_client=redis_client)
    state = await task_manager.get_task_state(task_id)

    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskResponse(
        task_id=state.task_id,
        thread_id=state.thread_id,
        status=state.status,
        updates=[u.model_dump() for u in state.updates],
        result=state.result,
        error_message=state.error_message,
        subject=state.metadata.subject if state.metadata else None,
        created_at=state.metadata.created_at if state.metadata else None,
        updated_at=state.metadata.updated_at if state.metadata else None,
    )


@router.delete("/tasks/{task_id}", status_code=status.HTTP_200_OK)
async def delete_task(task_id: str):
    """Delete a single task by ID.

    This performs two actions:

    1. Best-effort cancellation of the corresponding Docket task using the
       task_id as the Docket key.
    2. Core Redis cleanup via core.tasks.delete_task (does not depend on Docket).
    """

    redis_client = get_redis_client()

    # Best-effort: attempt to cancel any in-flight Docket task for this id.
    try:
        cancel_msg = ""
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            try:
                await docket.cancel(task_id)
            except Exception as e:  # pragma: no cover - defensive logging
                cancel_msg = f"Failed to cancel Docket task {task_id}: {e}"
                logger.warning("Failed to cancel Docket task %s: %s", task_id, e)
    except Exception as e:  # pragma: no cover - defensive logging
        cancel_msg = f"Failed to initialize Docket for cancel of {task_id}: {e}"
        logger.warning("Failed to initialize Docket for cancel of %s: %s", task_id, e)

    try:
        await delete_task_core(task_id=task_id, redis_client=redis_client)
    except Exception as e:
        logger.error("Failed to delete task %s: %s", task_id, e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete task {task_id}: {e}",
        ) from e

    return {
        "message": "Task deleted successfully",
        "task_id": task_id,
        "cancel_message": cancel_msg if cancel_msg else "",
    }

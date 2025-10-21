"""Task API: create task and get task by id.

Separate from legacy endpoints that returned status by thread.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

import redis_sre_agent.models.tasks as task_models
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.task_state import TaskManager
from redis_sre_agent.schemas.tasks import TaskCreateRequest, TaskCreateResponse, TaskResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Alias the model-layer create_task so tests can patch redis_sre_agent.api.tasks_api.create_task
create_task = task_models.create_task


@router.post("/tasks", response_model=TaskCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task_endpoint(req: TaskCreateRequest) -> TaskCreateResponse:
    try:
        rc = get_redis_client()
        data = await create_task(
            message=req.message, thread_id=req.thread_id, context=req.context, redis_client=rc
        )
        return TaskCreateResponse(**data)
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    rc = get_redis_client()
    tm = TaskManager(redis_client=rc)
    state = await tm.get_task_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")
    # Convert to response
    return TaskResponse(
        task_id=state.task_id,
        thread_id=state.thread_id,
        status=state.status,
        updates=[u.model_dump() for u in state.updates],
        result=state.result,
        error_message=state.error_message,
    )

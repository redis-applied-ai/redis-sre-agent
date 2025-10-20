"""Task management API endpoints."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.thread_state import (
    ThreadStatus,
)
from redis_sre_agent.models.tasks import (
    get_task_status as get_task_status_model,
)
from redis_sre_agent.models.tasks import (
    list_tasks as list_tasks_model,
)
from redis_sre_agent.models.threads import (
    cancel_thread,
    continue_thread,
    create_thread,
    delete_thread,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class TriageRequest(BaseModel):
    """Request model for triage endpoint."""

    query: str = Field(..., description="User query or issue description")
    user_id: Optional[str] = Field(None, description="User identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    priority: int = Field(0, description="Priority level (0=normal, 1=high, 2=critical)")
    tags: Optional[List[str]] = Field(None, description="Tags for categorization")
    instance_id: Optional[str] = Field(None, description="Redis instance ID for context")


class TriageResponse(BaseModel):
    """Response model for triage endpoint."""

    thread_id: str = Field(..., description="Thread identifier for tracking")
    status: ThreadStatus = Field(..., description="Current thread status")
    message: str = Field(..., description="Status message")
    estimated_completion: Optional[str] = Field(None, description="Estimated completion time")


class TaskStatusResponse(BaseModel):
    """Response model for task status endpoint."""

    thread_id: str = Field(..., description="Thread identifier")
    status: ThreadStatus = Field(..., description="Current status")
    updates: List[Dict[str, Any]] = Field(..., description="Progress updates")
    result: Optional[Dict[str, Any]] = Field(None, description="Final result if completed")
    action_items: List[Dict[str, Any]] = Field(default_factory=list, description="Action items")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Thread metadata")
    context: Dict[str, Any] = Field(default_factory=dict, description="Thread context")


@router.post(
    "/triage",
    response_model=TriageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit issue for SRE analysis",
    description="Submit an SRE issue or query for analysis. Returns a thread_id for tracking progress.",
)
async def triage_issue(request: TriageRequest) -> TriageResponse:
    """
    Triage endpoint - submit an issue and get a thread_id for tracking.

    This endpoint immediately returns a thread_id and queues the agent processing
    as a background Docket task. Clients should poll the status endpoint to
    get updates and results.
    """
    try:
        logger.info(f"Triaging issue for user {request.user_id}: {request.query[:100]}...")

        # Keep this call here so tests that patch api.tasks.get_redis_client still work
        redis_client = get_redis_client()

        data = await create_thread(
            query=request.query,
            user_id=request.user_id,
            session_id=request.session_id,
            context=request.context,
            priority=request.priority,
            tags=request.tags or [],
            instance_id=request.instance_id,
            redis_client=redis_client,
        )

        return TriageResponse(
            thread_id=data["thread_id"],
            status=data["status"],
            message=data["message"],
            estimated_completion=data.get("estimated_completion"),
        )

    except Exception as e:
        logger.error(f"Triage failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to triage issue: {str(e)}",
        )


@router.get(
    "/tasks/{thread_id}",
    response_model=TaskStatusResponse,
    summary="Get task status and results",
    description="Get the current status, progress updates, and results for a thread.",
)
async def get_task_status(thread_id: str) -> TaskStatusResponse:
    """
    Get task status and results.

    Returns current status, all progress updates, and final results if completed.
    Clients should poll this endpoint to track progress.
    """
    try:
        # Keep this call here so tests that patch api.tasks.get_redis_client still work
        redis_client = get_redis_client()

        data = await get_task_status_model(thread_id=thread_id, redis_client=redis_client)
        return TaskStatusResponse(**data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task status for {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task status: {str(e)}",
        )


@router.post(
    "/tasks/{thread_id}/continue",
    response_model=TriageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Continue conversation in thread",
    description="Add another message to an existing thread conversation.",
)
async def continue_conversation(thread_id: str, request: TriageRequest) -> TriageResponse:
    """
    Continue an existing conversation thread.

    Adds a new message to the thread and queues another agent processing turn.
    """
    try:
        # Keep this call here so tests that patch api.tasks.get_redis_client still work
        redis_client = get_redis_client()

        data = await continue_thread(
            thread_id=thread_id,
            query=request.query,
            context=request.context,
            redis_client=redis_client,
        )
        return TriageResponse(
            thread_id=data["thread_id"],
            status=data["status"],
            message=data["message"],
            estimated_completion=data.get("estimated_completion"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to continue conversation {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to continue conversation: {str(e)}",
        )


@router.delete(
    "/tasks/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel or delete task",
    description="Cancel a queued or in-progress task, or delete a completed task.",
)
async def cancel_task(thread_id: str, delete: bool = False):
    """
    Cancel or delete a task.

    If delete=True, permanently deletes the thread data.
    Otherwise, marks the thread as cancelled and attempts to stop processing.
    """
    try:
        # Keep this call here so tests that patch api.tasks.get_redis_client still work
        redis_client = get_redis_client()

        if delete:
            await delete_thread(thread_id=thread_id, redis_client=redis_client)
        else:
            await cancel_thread(thread_id=thread_id, redis_client=redis_client)
        # 204 No Content on success
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to {'delete' if delete else 'cancel'} task {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to {'delete' if delete else 'cancel'} task: {str(e)}",
        )


@router.get(
    "/tasks",
    response_model=List[TaskStatusResponse],
    summary="List tasks",
    description="List recent tasks (limited to last 50 for performance).",
)
async def list_tasks(
    user_id: Optional[str] = None, status_filter: Optional[ThreadStatus] = None, limit: int = 50
) -> List[TaskStatusResponse]:
    """
    List recent tasks with proper indexing and filtering.
    """
    try:
        logger.info(
            f"List tasks requested (user_id={user_id}, status={status_filter}, limit={limit})"
        )
        # Keep this call here so tests that patch api.tasks.get_redis_client still work
        redis_client = get_redis_client()

        items = await list_tasks_model(
            user_id=user_id, status_filter=status_filter, limit=limit, redis_client=redis_client
        )
        tasks = [TaskStatusResponse(**item) for item in items]
        logger.info(f"Returning {len(tasks)} tasks")
        return tasks

    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tasks: {str(e)}",
        )

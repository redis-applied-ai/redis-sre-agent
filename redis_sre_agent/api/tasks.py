"""Task management API endpoints."""

import logging
from typing import Any, Dict, List, Optional

from docket import Docket
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from redis_sre_agent.core.tasks import get_redis_url, process_agent_turn
from redis_sre_agent.core.thread_state import (
    ThreadStatus,
    get_thread_manager,
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

        # Create thread
        thread_manager = get_thread_manager()

        # Prepare initial context
        initial_context = {
            "original_query": request.query,
            "priority": request.priority,
            "messages": [],
        }
        if request.instance_id:
            initial_context["instance_id"] = request.instance_id
        if request.context:
            initial_context.update(request.context)

        # Create thread
        thread_id = await thread_manager.create_thread(
            user_id=request.user_id,
            session_id=request.session_id,
            initial_context=initial_context,
            tags=request.tags or [],
        )

        # Add initial update
        await thread_manager.add_thread_update(
            thread_id,
            f"Issue received: {request.query[:100]}{'...' if len(request.query) > 100 else ''}",
            "triage",
        )

        # Generate and update thread subject
        await thread_manager.update_thread_subject(thread_id, request.query)

        # Queue the agent processing task
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            # Submit the task to process this turn
            task_func = docket.add(process_agent_turn)
            await task_func(
                thread_id=thread_id,
                message=request.query,
                context=initial_context
            )

            logger.info(f"Queued agent task for thread {thread_id}")

        # Update status to queued
        await thread_manager.update_thread_status(thread_id, ThreadStatus.QUEUED)
        await thread_manager.add_thread_update(thread_id, "Task queued for processing", "queued")

        return TriageResponse(
            thread_id=thread_id,
            status=ThreadStatus.QUEUED,
            message="Issue has been triaged and queued for analysis",
            estimated_completion="2-5 minutes",
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
        thread_manager = get_thread_manager()

        # Get thread state
        thread_state = await thread_manager.get_thread_state(thread_id)
        if not thread_state:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread {thread_id} not found"
            )

        # Convert updates to dict format
        updates = [
            {
                "timestamp": update.timestamp,
                "message": update.message,
                "type": update.update_type,
                "metadata": update.metadata or {},
            }
            for update in thread_state.updates
        ]

        # Convert action items to dict format
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

        # Prepare metadata
        metadata = {
            "created_at": thread_state.metadata.created_at,
            "updated_at": thread_state.metadata.updated_at,
            "user_id": thread_state.metadata.user_id,
            "session_id": thread_state.metadata.session_id,
            "priority": thread_state.metadata.priority,
            "tags": thread_state.metadata.tags,
            "subject": thread_state.metadata.subject,
        }

        return TaskStatusResponse(
            thread_id=thread_id,
            status=thread_state.status,
            updates=updates,
            result=thread_state.result,
            action_items=action_items,
            error_message=thread_state.error_message,
            metadata=metadata,
            context=thread_state.context,
        )

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
        thread_manager = get_thread_manager()

        # Check if thread exists
        thread_state = await thread_manager.get_thread_state(thread_id)
        if not thread_state:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread {thread_id} not found"
            )

        # Check if thread is in a valid state for continuation
        if thread_state.status in [ThreadStatus.IN_PROGRESS, ThreadStatus.QUEUED]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Thread {thread_id} is currently {thread_state.status.value}. Wait for completion before continuing.",
            )

        # Add continuation update
        await thread_manager.add_thread_update(
            thread_id,
            f"Continuing conversation: {request.query[:100]}{'...' if len(request.query) > 100 else ''}",
            "continuation",
        )

        # Queue another agent processing task
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            task_func = docket.add(process_agent_turn)
            await task_func(
                thread_id=thread_id,
                message=request.query,
                context=request.context
            )

            logger.info(f"Queued continuation task for thread {thread_id}")

        # Update status to queued
        await thread_manager.update_thread_status(thread_id, ThreadStatus.QUEUED)
        await thread_manager.add_thread_update(
            thread_id, "Conversation continuation queued", "queued"
        )

        return TriageResponse(
            thread_id=thread_id,
            status=ThreadStatus.QUEUED,
            message="Conversation continuation queued for processing",
            estimated_completion="2-5 minutes",
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
    summary="Cancel task",
    description="Cancel a queued or in-progress task.",
)
async def cancel_task(thread_id: str):
    """
    Cancel a task.

    Marks the thread as cancelled and attempts to stop processing.
    """
    try:
        thread_manager = get_thread_manager()

        # Check if thread exists
        thread_state = await thread_manager.get_thread_state(thread_id)
        if not thread_state:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Thread {thread_id} not found"
            )

        # Check if thread can be cancelled
        if thread_state.status in [ThreadStatus.DONE, ThreadStatus.FAILED, ThreadStatus.CANCELLED]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Thread {thread_id} is already {thread_state.status.value} and cannot be cancelled",
            )

        # Mark as cancelled
        await thread_manager.update_thread_status(thread_id, ThreadStatus.CANCELLED)
        await thread_manager.add_thread_update(
            thread_id, "Task cancelled by user request", "cancellation"
        )

        logger.info(f"Cancelled thread {thread_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel task {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel task: {str(e)}",
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

        thread_manager = get_thread_manager()

        # Get thread summaries
        thread_summaries = await thread_manager.list_threads(
            user_id=user_id,
            status_filter=status_filter,
            limit=limit,
            offset=0,
        )

        # Convert to TaskStatusResponse format
        tasks = []
        for summary in thread_summaries:
            # Create minimal updates list for listing
            updates = [
                {
                    "timestamp": summary.get("updated_at", summary.get("created_at")),
                    "message": summary.get("latest_message", "No updates"),
                    "type": "summary",
                    "metadata": {},
                }
            ]

            # Create metadata
            metadata = {
                "created_at": summary.get("created_at"),
                "updated_at": summary.get("updated_at"),
                "user_id": summary.get("user_id"),
                "session_id": None,  # Not stored in summary
                "priority": summary.get("priority", 0),
                "tags": summary.get("tags", []),
                "subject": summary.get("subject", "Untitled"),
            }

            task_response = TaskStatusResponse(
                thread_id=summary["thread_id"],
                status=ThreadStatus(summary["status"]),
                updates=updates,
                result=None,  # Not included in listing for performance
                action_items=[],  # Not included in listing for performance
                error_message=None,  # Not included in listing for performance
                metadata=metadata,
            )

            tasks.append(task_response)

        logger.info(f"Returning {len(tasks)} tasks")
        return tasks

    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tasks: {str(e)}",
        )

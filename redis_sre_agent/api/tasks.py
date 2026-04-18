"""Task API: create task and get task by id.

Separate from legacy endpoints that returned status by thread.
"""

from __future__ import annotations

import logging

from docket import Docket
from fastapi import APIRouter, HTTPException, status

from redis_sre_agent.api.schemas import (
    TaskApprovalListResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskResponse,
    TaskResumeRequest,
)
from redis_sre_agent.core.approvals import ApprovalManager
from redis_sre_agent.core.docket_tasks import (
    get_redis_url,
    process_agent_turn,
    resume_task_after_approval,
    validate_task_resume_request,
)
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.tasks import TaskManager, TaskStatus, create_task
from redis_sre_agent.core.tasks import delete_task as delete_task_core
from redis_sre_agent.core.tasks import TaskStatus
from redis_sre_agent.mcp_server.task_contract import (
    cancel_background_task,
    submit_background_task_call,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _build_task_response(task_id: str, task_manager: TaskManager) -> TaskResponse:
    state = await task_manager.get_task_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    tool_calls = await task_manager.get_task_tool_calls(state)

    return TaskResponse(
        task_id=state.task_id,
        thread_id=state.thread_id,
        status=state.status,
        updates=[u.model_dump() for u in state.updates],
        result=state.result,
        tool_calls=tool_calls,
        error_message=state.error_message,
        pending_approval=getattr(state, "pending_approval", None),
        resume_supported=bool(getattr(state, "resume_supported", False)),
        subject=state.metadata.subject if state.metadata else None,
        created_at=state.metadata.created_at if state.metadata else None,
        updated_at=state.metadata.updated_at if state.metadata else None,
    )


async def _enqueue_resume_task(
    *,
    docket: Docket,
    task_id: str,
    approval_id: str,
    decision,
    decision_by: str | None,
    decision_comment: str | None,
):
    """Schedule the resume worker using Docket's returned scheduler callable."""

    decision_value = decision.value if hasattr(decision, "value") else decision
    schedule_resume = docket.add(resume_task_after_approval, key=task_id)
    return await schedule_resume(
        task_id=task_id,
        approval_id=approval_id,
        decision=decision_value,
        decision_by=decision_by,
        decision_comment=decision_comment,
    )


@router.post("/tasks", response_model=TaskCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task_endpoint(req: TaskCreateRequest) -> TaskCreateResponse:
    context = dict(req.context or {})
    if req.user_id:
        context.setdefault("user_id", req.user_id)
    if context.get("instance_id") and context.get("cluster_id"):
        raise HTTPException(
            status_code=400,
            detail="Please provide only one of instance_id or cluster_id in context",
        )

    try:
        redis_client = get_redis_client()
        data = await create_task(
            message=req.message,
            thread_id=req.thread_id,
            user_id=req.user_id,
            context=context,
            redis_client=redis_client,
        )
        task = TaskCreateResponse(**data)

        if not task.thread_id:
            logger.error("create_task returned no thread_id; refusing to queue turn")
            raise HTTPException(status_code=500, detail="Failed to create thread for task")

        execution = await submit_background_task_call(
            processor=process_agent_turn,
            key=task.task_id,
            processor_kwargs={
                "thread_id": task.thread_id,
                "message": req.message,
                "context": context,
                "task_id": task.task_id,
            },
        )
        if execution["mode"] == "inline":
            task.status = TaskStatus.DONE
            task.message = "Task completed inline during runtime execution"

        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    redis_client = get_redis_client()
    task_manager = TaskManager(redis_client=redis_client)
    return await _build_task_response(task_id, task_manager)


@router.get("/tasks/{task_id}/approvals", response_model=TaskApprovalListResponse)
async def list_task_approvals(task_id: str) -> TaskApprovalListResponse:
    redis_client = get_redis_client()
    task_manager = TaskManager(redis_client=redis_client)
    state = await task_manager.get_task_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    approvals = await ApprovalManager(redis_client=redis_client).list_task_approvals(task_id)
    return TaskApprovalListResponse(task_id=task_id, approvals=approvals)


@router.post("/tasks/{task_id}/resume", response_model=TaskResponse)
async def resume_task(task_id: str, req: TaskResumeRequest) -> TaskResponse:
    redis_client = get_redis_client()
    task_manager = TaskManager(redis_client=redis_client)
    state = await task_manager.get_task_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    if state.status != TaskStatus.AWAITING_APPROVAL:
        return await _build_task_response(task_id, task_manager)

    resume_requested = False
    pending_approval = getattr(state, "pending_approval", None)
    try:
        await validate_task_resume_request(
            task_id=task_id,
            approval_id=req.approval_id,
            decision=req.decision,
            decision_by=req.decision_by,
            decision_comment=req.decision_comment,
            redis_client=redis_client,
        )
        await task_manager.set_pending_approval(task_id, None)
        await task_manager.update_task_status(task_id, TaskStatus.IN_PROGRESS)
        resume_requested = True
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            await _enqueue_resume_task(
                docket=docket,
                task_id=task_id,
                approval_id=req.approval_id,
                decision=req.decision,
                decision_by=req.decision_by,
                decision_comment=req.decision_comment,
            )
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    except Exception:
        if resume_requested:
            await task_manager.set_pending_approval(task_id, pending_approval)
            await task_manager.update_task_status(task_id, TaskStatus.AWAITING_APPROVAL)
        raise

    return await _build_task_response(task_id, task_manager)


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
    cancel_msg = ""
    try:
        try:
            cancel_result = await cancel_background_task(task_id=task_id)
            cancel_msg = str(cancel_result.get("message") or "")
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

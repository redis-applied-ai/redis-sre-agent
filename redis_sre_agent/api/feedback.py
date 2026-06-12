"""Feedback API endpoints for submitting and retrieving task feedback."""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status

from redis_sre_agent.api.schemas import FeedbackRecord, FeedbackSubmitRequest, FeedbackView
from redis_sre_agent.core.feedback import TaskNotFoundError
from redis_sre_agent.core.feedback import get_feedback_view as core_get_feedback_view
from redis_sre_agent.core.feedback import list_feedback_views as core_list_feedback_views
from redis_sre_agent.core.feedback import submit_feedback as core_submit_feedback
from redis_sre_agent.core.tasks import TaskStatus

router = APIRouter(prefix="/api/v1/tasks", tags=["feedback"])

# Second router for the collection endpoint at /api/v1/feedback.
# Kept separate from `router` so the prefix doesn't have to be /api/v1/tasks.
list_router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])

# Valid status values derived from the TaskStatus enum — used in Query validation.
_VALID_STATUSES = {s.value for s in TaskStatus}


@router.post(
    "/{task_id}/feedback",
    response_model=FeedbackRecord,
    status_code=http_status.HTTP_200_OK,
)
async def submit_task_feedback(task_id: str, body: FeedbackSubmitRequest) -> FeedbackRecord:
    """Submit or update feedback for a task.

    Pydantic validation errors (invalid verdict, comment too long) propagate
    as 422 via default FastAPI behaviour — do not catch them here.
    """
    try:
        return await core_submit_feedback(task_id, body.verdict, body.comment)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{task_id}/feedback",
    response_model=FeedbackView,
    status_code=http_status.HTTP_200_OK,
)
async def get_task_feedback(task_id: str) -> FeedbackView:
    """Retrieve the joined feedback view for a task, or 404 when absent.

    Returns a FeedbackView with both `feedback` and `task` keys.
    The POST endpoint above still returns a bare FeedbackRecord (AC-17).
    """
    try:
        view = await core_get_feedback_view(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if view is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No feedback found for task {task_id}",
        )
    return view


@list_router.get("")
async def list_feedback(
    since: Optional[str] = Query(None, pattern=r"^(\d+)([smhd])$"),
    verdict: Optional[Literal["up", "down", "withdrawn"]] = Query(None),
    # `status` validated manually: FastAPI/Pydantic rejects unknown values → 422
    # with loc=["query","status"], which matches AC-9.
    status: Optional[str] = Query(None),
    # limit is clamped via ge/le: values outside [1,500] return 422 (not silently
    # clamped), so callers get an explicit error rather than a surprising truncation.
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """List feedback views with optional filters.

    Filters:
    - since: time window in the form Ns/Nm/Nh/Nd (e.g. 24h, 30m).
    - verdict: up | down | withdrawn.
    - status: any TaskStatus value; unknown values return 422.
    - limit: 1–500 (default 50). Values outside that range return 422.
    """
    if status is not None and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "type": "literal_error",
                    "loc": ["query", "status"],
                    "msg": f"Input should be one of {sorted(_VALID_STATUSES)}",
                    "input": status,
                }
            ],
        )

    views = await core_list_feedback_views(since=since, verdict=verdict, status=status, limit=limit)
    return {"items": [v.model_dump(mode="json") for v in views], "count": len(views)}

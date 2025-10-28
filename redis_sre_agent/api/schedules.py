"""Schedule management API endpoints for automated agent runs."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..core.schedule_storage import (
    delete_schedule as delete_schedule_from_redis,
)
from ..core.schedule_storage import (
    get_schedule as get_schedule_from_redis,
)
from ..core.schedule_storage import (
    list_schedules as list_schedules_from_redis,
)
from ..core.schedule_storage import (
    store_schedule,
)
from ..core.schedules import Schedule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/schedules", tags=["schedules"])

# Global storage for schedules (DEPRECATED - now using Redis)
_schedules: Dict[str, Dict] = {}
_scheduled_tasks: Dict[str, Dict] = {}
_scheduled_runs: Dict[str, Dict] = {}  # Keep for API compatibility


class CreateScheduleRequest(BaseModel):
    """Request model for creating a schedule."""

    name: str = Field(..., description="Human-readable schedule name")
    description: Optional[str] = Field(None, description="Schedule description")
    interval_type: str = Field(..., description="Interval type: minutes, hours, days, weeks")
    interval_value: int = Field(..., ge=1, description="Interval value (e.g., 30 for '30 minutes')")
    redis_instance_id: Optional[str] = Field(
        None, description="Redis instance ID to use (optional)"
    )
    instructions: str = Field(..., description="Instructions for the agent to execute")
    enabled: bool = Field(True, description="Whether the schedule is active")


class UpdateScheduleRequest(BaseModel):
    """Request model for updating a schedule."""

    name: Optional[str] = Field(None, description="Human-readable schedule name")
    description: Optional[str] = Field(None, description="Schedule description")
    interval_type: Optional[str] = Field(
        None, description="Interval type: minutes, hours, days, weeks"
    )
    interval_value: Optional[int] = Field(None, ge=1, description="Interval value")
    redis_instance_id: Optional[str] = Field(
        None, description="Redis instance ID to use (optional)"
    )
    instructions: Optional[str] = Field(None, description="Instructions for the agent to execute")
    enabled: Optional[bool] = Field(None, description="Whether the schedule is active")


class ScheduledTask(BaseModel):
    """Model for a scheduled task instance."""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique task ID")
    schedule_id: str = Field(..., description="ID of the parent schedule")
    scheduled_at: str = Field(..., description="When this task is scheduled to run")
    status: str = Field("pending", description="Task status: pending, submitted, completed, failed")
    triage_task_id: Optional[str] = Field(None, description="ID of the submitted triage task")
    submitted_at: Optional[str] = Field(None, description="When the task was submitted to Docket")
    error: Optional[str] = Field(None, description="Error message if task failed")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ScheduledRun(BaseModel):
    """Model for a scheduled run instance (legacy - keeping for API compatibility).

    Extended to include thread_id and task_id for richer linkage and status reporting.
    """

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique run ID")
    schedule_id: str = Field(..., description="ID of the parent schedule")
    # New fields (optional for backward compatibility)
    thread_id: Optional[str] = Field(None, description="ID of the thread created for this run")
    task_id: Optional[str] = Field(None, description="ID of the per-turn task for this run")

    status: str = Field("pending", description="Run status based on Task status")
    scheduled_at: str = Field(..., description="When this run was scheduled for")
    started_at: Optional[str] = Field(None, description="When the run actually started")
    completed_at: Optional[str] = Field(None, description="When the run completed")
    triage_task_id: Optional[str] = Field(
        None, description="ID of the created triage task (thread)"
    )
    error: Optional[str] = Field(None, description="Error message if run failed")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@router.get("/", response_model=List[Schedule])
async def list_schedules():
    """List all schedules."""
    try:
        schedule_data_list = await list_schedules_from_redis()
        schedules = []
        for schedule_data in schedule_data_list:
            schedules.append(Schedule(**schedule_data))
        return schedules
    except Exception as e:
        logger.error(f"Failed to list schedules: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list schedules: {str(e)}",
        )


@router.post("/", response_model=Schedule)
async def create_schedule(request: CreateScheduleRequest):
    """Create a new schedule."""
    try:
        # Validate interval type
        if request.interval_type not in ["minutes", "hours", "days", "weeks"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid interval_type. Must be one of: minutes, hours, days, weeks",
            )

        # Create schedule
        schedule = Schedule(
            name=request.name,
            description=request.description,
            interval_type=request.interval_type,
            interval_value=request.interval_value,
            redis_instance_id=request.redis_instance_id,
            instructions=request.instructions,
            enabled=request.enabled,
        )

        # Calculate next run time
        next_run = schedule.calculate_next_run()
        schedule.next_run_at = next_run.isoformat()

        # Store schedule in Redis
        schedule_data = schedule.dict()
        success = await store_schedule(schedule_data)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store schedule in Redis",
            )

        logger.info(f"Created schedule: {schedule.name} ({schedule.id})")
        return schedule

    except Exception as e:
        logger.error(f"Failed to create schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create schedule: {str(e)}",
        )


@router.get("/{schedule_id}", response_model=Schedule)
async def get_schedule(schedule_id: str):
    """Get a specific schedule."""
    try:
        schedule_data = await get_schedule_from_redis(schedule_id)
        if not schedule_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Schedule {schedule_id} not found"
            )

        return Schedule(**schedule_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get schedule {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get schedule: {str(e)}",
        )


@router.put("/{schedule_id}", response_model=Schedule)
async def update_schedule(schedule_id: str, request: UpdateScheduleRequest):
    """Update a schedule."""
    try:
        # Get existing schedule from Redis
        schedule_data = await get_schedule_from_redis(schedule_id)
        if not schedule_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Schedule {schedule_id} not found"
            )

        # Merge provided fields
        update_data = request.dict(exclude_unset=True)
        if update_data:
            schedule_data.update(update_data)

        # Rehydrate to model for consistent types and timestamp handling
        schedule = Schedule(**schedule_data)
        schedule.updated_at = datetime.now(timezone.utc).isoformat()

        # Recalculate next run if interval changed
        if "interval_type" in update_data or "interval_value" in update_data:
            next_run = schedule.calculate_next_run()
            schedule.next_run_at = next_run.isoformat()

        # Persist updated schedule
        success = await store_schedule(schedule.dict())
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update schedule in Redis",
            )

        logger.info(f"Updated schedule: {schedule_id}")
        return schedule

    except Exception as e:
        logger.error(f"Failed to update schedule {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update schedule: {str(e)}",
        )


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete a schedule."""
    try:
        # Get schedule name before deletion
        schedule_data = await get_schedule_from_redis(schedule_id)
        if not schedule_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Schedule {schedule_id} not found"
            )

        schedule_name = schedule_data["name"]

        # Delete from Redis
        success = await delete_schedule_from_redis(schedule_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete schedule from Redis",
            )

        logger.info(f"Deleted schedule: {schedule_name} ({schedule_id})")
        return {"message": f"Schedule '{schedule_name}' deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete schedule {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete schedule: {str(e)}",
        )


@router.get("/{schedule_id}/runs", response_model=List[ScheduledRun])
async def list_schedule_runs(schedule_id: str):
    """List runs for a specific schedule."""
    try:
        # Check if schedule exists in Redis
        schedule_data = await get_schedule_from_redis(schedule_id)
        if not schedule_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Schedule {schedule_id} not found"
            )

        # Get all threads created by the scheduler
        from ..core.redis import get_redis_client
        from ..core.thread_state import ThreadManager

        redis_client = get_redis_client()
        thread_manager = ThreadManager(redis_client=redis_client)

        # Get all scheduler threads (user_id="scheduler")
        all_scheduler_threads = await thread_manager.list_threads(
            user_id="scheduler",
            limit=200,  # Get more threads to find all runs for this schedule
        )

        # Filter threads that belong to this specific schedule
        schedule_threads = []
        for thread_summary in all_scheduler_threads:
            # Get the full thread state to access context
            thread_state = await thread_manager.get_thread_state(thread_summary["thread_id"])
            if thread_state and thread_state.context.get("schedule_id") == schedule_id:
                schedule_threads.append(
                    {
                        "thread_id": thread_summary["thread_id"],
                        "status": thread_summary["status"],
                        "created_at": thread_summary["created_at"],
                        "updated_at": thread_summary["updated_at"],
                        "context": thread_state.context,
                        "subject": thread_summary.get("subject", "Scheduled Run"),
                    }
                )

        # Convert to ScheduledRun format (derive Task status and IDs)
        from ..core.keys import RedisKeys
        from ..core.task_state import TaskManager

        runs = []
        task_manager = TaskManager(redis_client=redis_client)

        for thread in schedule_threads:
            thread_id = thread["thread_id"]

            # Defaults
            task_id: Optional[str] = None
            task_status = "queued"
            started_at = thread["created_at"]
            completed_at = None
            error_msg = None

            # Find latest per-turn task for this thread
            try:
                zkey = RedisKeys.thread_tasks_index(thread_id)
                tids = await redis_client.zrevrange(zkey, 0, 0)
                if tids:
                    tid0 = tids[0]
                    if isinstance(tid0, bytes):
                        tid0 = tid0.decode()
                    task_id = tid0
            except Exception:
                task_id = None

            if task_id:
                try:
                    tstate = await task_manager.get_task_state(task_id)
                except Exception:
                    tstate = None
                if tstate:
                    status_obj = getattr(tstate, "status", None)
                    if status_obj is not None:
                        task_status = getattr(status_obj, "value", str(status_obj))
                    md = getattr(tstate, "metadata", None)
                    if md is not None:
                        started_at = md.created_at or started_at
                        if task_status == "done":
                            completed_at = md.updated_at
                    error_msg = getattr(tstate, "error_message", None)

            scheduled_at = thread["context"].get("scheduled_at", thread["created_at"])

            run = ScheduledRun(
                id=thread_id,  # Use thread_id as run id
                schedule_id=schedule_id,
                thread_id=thread_id,
                task_id=task_id,
                status=task_status,
                scheduled_at=scheduled_at,
                started_at=started_at,
                completed_at=completed_at,
                triage_task_id=thread_id,  # Legacy link to the thread for viewing
                created_at=thread["created_at"],
                error=error_msg,
            )
            runs.append(run)

        # Sort by scheduled_at descending (most recent first)
        runs.sort(key=lambda x: x.scheduled_at, reverse=True)
        return runs

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list runs for schedule {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list schedule runs: {str(e)}",
        )


@router.post("/{schedule_id}/trigger", response_model=ScheduledRun)
async def trigger_schedule_now(schedule_id: str):
    """Manually trigger a schedule to run immediately."""
    try:
        # Check if schedule exists in Redis
        schedule_data = await get_schedule_from_redis(schedule_id)
        if not schedule_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Schedule {schedule_id} not found"
            )

        # For manual triggers, directly create and submit the agent task
        # This preserves the original schedule timing and avoids scheduler interference
        current_time = datetime.now(timezone.utc)

        logger.info(f"Manually triggering schedule {schedule_id} to run immediately")

        # Create thread for the manual run
        from ..core.redis import get_redis_client
        from ..core.thread_state import ThreadManager

        redis_client = get_redis_client()
        thread_manager = ThreadManager(redis_client=redis_client)

        # Prepare context for the manual run
        run_context = {
            "schedule_id": schedule_id,
            "schedule_name": schedule_data["name"],
            "automated": True,
            "manual_trigger": True,  # Mark as manual trigger
            "original_query": schedule_data["instructions"],
            "scheduled_at": current_time.isoformat(),
        }

        if schedule_data.get("redis_instance_id"):
            run_context["instance_id"] = schedule_data["redis_instance_id"]

        # Create thread for the manual run
        thread_id = await thread_manager.create_thread(
            user_id="scheduler",
            session_id=f"manual_schedule_{schedule_id}_{current_time.strftime('%Y%m%d_%H%M%S')}",
            initial_context=run_context,
            tags=["automated", "scheduled", "manual_trigger"],
        )

        # Submit the agent task directly
        from docket import Docket

        from ..core.docket_tasks import get_redis_url, process_agent_turn

        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            # Use a deduplication key for the manual trigger
            task_key = f"manual_schedule_{schedule_id}_{current_time.strftime('%Y%m%d_%H%M%S')}"

            try:
                # Submit task to run immediately (no 'when' parameter)
                task_func = docket.add(process_agent_turn, key=task_key)
                agent_task_id = await task_func(
                    thread_id=thread_id, message=schedule_data["instructions"], context=run_context
                )
                logger.info(
                    f"Submitted manual agent task {agent_task_id} for schedule {schedule_id} with key {task_key}"
                )
            except Exception as e:
                # If the task was already triggered (duplicate key), this is expected
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    logger.info(
                        f"Manual agent task for schedule {schedule_id} already submitted with key {task_key}"
                    )
                    agent_task_id = "already_running"
                else:
                    logger.error(f"Failed to submit manual agent task: {e}")
                    raise e

        # Create a synthetic run record for the response (thread_id known; task_id will be created by worker)
        run = ScheduledRun(
            schedule_id=schedule_id,
            scheduled_at=current_time.isoformat(),
            status="pending",
            thread_id=thread_id,
            task_id=None,
        )

        logger.info(f"Manually triggered schedule {schedule_id}")
        return run

    except Exception as e:
        logger.error(f"Failed to trigger schedule {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger schedule: {str(e)}",
        )


# Internal functions for the scheduler task


def create_scheduled_tasks_for_next_hour() -> List[ScheduledTask]:
    """Create scheduled tasks for all enabled schedules for the next hour."""
    now = datetime.now(timezone.utc)
    end_time = now + timedelta(hours=1)
    created_tasks = []

    for schedule_data in _schedules.values():
        if not schedule_data["enabled"]:
            continue

        schedule = Schedule(**schedule_data)

        # Calculate all run times for this schedule in the next hour
        current_time = now
        while current_time <= end_time:
            # Calculate next run time from current_time
            if schedule.interval_type == "minutes":
                next_run = current_time + timedelta(minutes=schedule.interval_value)
            elif schedule.interval_type == "hours":
                next_run = current_time + timedelta(hours=schedule.interval_value)
            elif schedule.interval_type == "days":
                next_run = current_time + timedelta(days=schedule.interval_value)
            elif schedule.interval_type == "weeks":
                next_run = current_time + timedelta(weeks=schedule.interval_value)
            else:
                break

            if next_run > end_time:
                break

            # Check if a task already exists for this time (within 1 minute tolerance)
            task_exists = False
            for existing_task_data in _scheduled_tasks.values():
                if existing_task_data["schedule_id"] == schedule.id:
                    existing_time = datetime.fromisoformat(
                        existing_task_data["scheduled_at"].replace("Z", "+00:00")
                    )
                    if abs((existing_time - next_run).total_seconds()) < 60:
                        task_exists = True
                        break

            if not task_exists:
                # Create new scheduled task
                task = ScheduledTask(
                    schedule_id=schedule.id, scheduled_at=next_run.isoformat(), status="pending"
                )
                _scheduled_tasks[task.id] = task.dict()
                created_tasks.append(task)

            current_time = next_run

    return created_tasks


def get_pending_scheduled_tasks() -> List[ScheduledTask]:
    """Get all pending scheduled tasks that should be submitted to Docket."""
    pending_tasks = []

    for task_data in _scheduled_tasks.values():
        if task_data["status"] == "pending":
            pending_tasks.append(ScheduledTask(**task_data))

    return pending_tasks


def mark_task_as_submitted(task_id: str, triage_task_id: str):
    """Mark a scheduled task as submitted to Docket."""
    if task_id in _scheduled_tasks:
        _scheduled_tasks[task_id]["status"] = "submitted"
        _scheduled_tasks[task_id]["triage_task_id"] = triage_task_id
        _scheduled_tasks[task_id]["submitted_at"] = datetime.now(timezone.utc).isoformat()


def mark_task_as_failed(task_id: str, error: str):
    """Mark a scheduled task as failed."""
    if task_id in _scheduled_tasks:
        _scheduled_tasks[task_id]["status"] = "failed"
        _scheduled_tasks[task_id]["error"] = error


def mark_task_as_completed(task_id: str):
    """Mark a scheduled task as completed."""
    if task_id in _scheduled_tasks:
        _scheduled_tasks[task_id]["status"] = "completed"


# Legacy functions for API compatibility
def get_due_scheduled_runs() -> List[ScheduledRun]:
    """Get all scheduled runs that are due to execute (legacy)."""
    # Convert scheduled tasks to scheduled runs for API compatibility
    runs = []
    for task_data in _scheduled_tasks.values():
        if task_data["status"] in ["submitted", "completed"]:
            run = ScheduledRun(
                id=task_data["id"],
                schedule_id=task_data["schedule_id"],
                scheduled_at=task_data["scheduled_at"],
                status="running" if task_data["status"] == "submitted" else task_data["status"],
                triage_task_id=task_data.get("triage_task_id"),
                started_at=task_data.get("submitted_at"),
                completed_at=task_data.get("submitted_at")
                if task_data["status"] == "completed"
                else None,
                error=task_data.get("error"),
            )
            runs.append(run)

    return runs


def mark_run_as_running(run_id: str, triage_task_id: str):
    """Mark a scheduled run as running (legacy)."""
    mark_task_as_submitted(run_id, triage_task_id)


def mark_run_as_completed(run_id: str):
    """Mark a scheduled run as completed (legacy)."""
    mark_task_as_completed(run_id)


def mark_run_as_failed(run_id: str, error: str):
    """Mark a scheduled run as failed (legacy)."""
    mark_task_as_failed(run_id, error)


@router.post("/trigger-scheduler")
async def trigger_scheduler():
    """Manually trigger the scheduler task for testing."""
    try:
        from docket import Docket

        from ..core.docket_tasks import get_redis_url, scheduler_task

        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            # Use a deduplication key based on current time to prevent multiple manual triggers
            current_time = datetime.now(timezone.utc)
            scheduler_key = f"scheduler_task_manual_{current_time.strftime('%Y%m%d_%H%M%S')}"

            try:
                task_func = docket.add(scheduler_task, key=scheduler_key)
                task_id = await task_func()
                logger.info(
                    f"Manually triggered scheduler task with ID: {task_id} and key: {scheduler_key}"
                )

                return {
                    "status": "success",
                    "message": "Scheduler task triggered successfully",
                    "task_id": str(task_id),
                    "scheduler_key": scheduler_key,
                    "timestamp": current_time.isoformat(),
                }
            except Exception as e:
                # If the task was already triggered (duplicate key), return success but note it
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    return {
                        "status": "success",
                        "message": "Scheduler task already running - no duplicate created",
                        "scheduler_key": scheduler_key,
                        "timestamp": current_time.isoformat(),
                    }
                else:
                    raise e

    except Exception as e:
        logger.error(f"Failed to trigger scheduler task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger scheduler: {str(e)}")

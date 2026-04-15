"""Schedule management API endpoints for automated agent runs."""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status

from ..core.docket_tasks import scheduler_task
from ..core.keys import RedisKeys
from ..core.redis import get_redis_client
from ..core.schedule_helpers import run_schedule_now_helper
from ..core.schedules import (
    Schedule,
    store_schedule,
)
from ..core.schedules import (
    delete_schedule as _delete_schedule,
)
from ..core.schedules import (
    get_schedule as _get_schedule,
)
from ..core.schedules import (
    list_schedules as _list_schedules,
)
from ..core.tasks import TaskManager
from ..core.threads import ThreadManager
from ..mcp_server.task_contract import submit_background_task_call
from .schemas import (
    CreateScheduleRequest,
    ScheduledRun,
    UpdateScheduleRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/schedules", tags=["schedules"])


@router.get("/", response_model=List[Schedule])
async def list_schedules():
    """List all schedules."""
    try:
        schedule_data_list = await _list_schedules()
        schedules = []
        for schedule_data in schedule_data_list:
            schedules.append(Schedule(**schedule_data))
        return schedules
    except Exception as e:
        logger.exception(f"Failed to list schedules: {e}")
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
        schedule_data = schedule.model_dump()
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
        schedule_data = await _get_schedule(schedule_id)
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
        schedule_data = await _get_schedule(schedule_id)
        if not schedule_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Schedule {schedule_id} not found"
            )

        # Merge provided fields
        update_data = request.model_dump(exclude_unset=True)
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
        schedule_data = await _get_schedule(schedule_id)
        if not schedule_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Schedule {schedule_id} not found"
            )

        schedule_name = schedule_data["name"]

        # Delete from Redis
        success = await _delete_schedule(schedule_id)
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
        schedule_data = await _get_schedule(schedule_id)
        if not schedule_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Schedule {schedule_id} not found"
            )

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
            thread_state = await thread_manager.get_thread(thread_summary["thread_id"])
            if thread_state and thread_state.context.get("schedule_id") == schedule_id:
                schedule_threads.append(
                    {
                        "thread_id": thread_summary["thread_id"],
                        # Status will be derived from the per-turn task below
                        "created_at": thread_summary["created_at"],
                        "updated_at": thread_summary["updated_at"],
                        "context": thread_state.context,
                        "subject": thread_summary.get("subject", "Scheduled Run"),
                    }
                )

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
                    task = await task_manager.get_task_state(task_id)
                except Exception:
                    task = None
                if task:
                    task_status = task.status
                    metadata = task.metadata
                    started_at = metadata.created_at or started_at
                    if task_status == "done":
                        completed_at = metadata.updated_at
                    error_msg = task.error_message

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
        result = await run_schedule_now_helper(schedule_id)
        if result.get("error") == "Schedule not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Schedule {schedule_id} not found"
            )
        run = ScheduledRun(
            schedule_id=schedule_id,
            scheduled_at=result["scheduled_at"],
            status=result["status"],
            thread_id=result.get("thread_id"),
            task_id=result.get("task_id"),
        )

        logger.info(f"Manually triggered schedule {schedule_id}")
        return run

    except Exception as e:
        logger.error(f"Failed to trigger schedule {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger schedule: {str(e)}",
        )


@router.post("/trigger-scheduler")
async def trigger_scheduler():
    """Manually trigger the scheduler task for testing."""
    try:
        current_time = datetime.now(timezone.utc)
        scheduler_key = f"scheduler_task_manual_{current_time.strftime('%Y%m%d_%H%M%S')}"

        try:
            execution = await submit_background_task_call(
                processor=scheduler_task,
                key=scheduler_key,
                processor_kwargs={},
            )
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                return {
                    "status": "success",
                    "message": "Scheduler task already running - no duplicate created",
                    "scheduler_key": scheduler_key,
                    "timestamp": current_time.isoformat(),
                }
            raise e

        payload = {
            "status": "success",
            "scheduler_key": scheduler_key,
            "timestamp": current_time.isoformat(),
        }
        if execution["mode"] == "inline":
            payload.update(
                {
                    "message": "Scheduler task executed inline during runtime execution",
                    "result": execution["result"],
                }
            )
            return payload

        payload.update(
            {
                "message": "Scheduler task triggered successfully",
                "task_id": str(execution["result"]),
            }
        )
        return payload

    except Exception as e:
        logger.error(f"Failed to trigger scheduler task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger scheduler: {str(e)}")

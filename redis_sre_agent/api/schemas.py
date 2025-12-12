"""API schema models for request/response validation."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from redis_sre_agent.core.tasks import TaskStatus


# Schedule schemas
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


# Task schemas
class TaskCreateRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class TaskCreateResponse(BaseModel):
    task_id: str
    thread_id: str
    status: TaskStatus = TaskStatus.QUEUED
    message: str = Field("Task accepted", description="Human-friendly status message")


class TaskResponse(BaseModel):
    task_id: str
    thread_id: str
    status: TaskStatus
    updates: List[Dict[str, Any]] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    subject: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# Thread schemas
class Message(BaseModel):
    role: Optional[str] = Field("user", description="Message role: user|assistant|system")
    content: str
    metadata: Optional[Dict[str, Any]] = None


class ThreadCreateRequest(BaseModel):
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    priority: int = 0
    tags: List[str] = Field(default_factory=list)
    subject: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    messages: Optional[List[Message]] = None


class ThreadUpdateRequest(BaseModel):
    subject: Optional[str] = None
    priority: Optional[int] = None
    tags: Optional[List[str]] = None
    context: Optional[Dict[str, Any]] = None


class ThreadAppendMessagesRequest(BaseModel):
    messages: List[Message]


class ThreadResponse(BaseModel):
    """Response model for thread data.

    Updates, result, and error_message are fetched from the latest task
    associated with this thread to support real-time UI updates.
    """

    thread_id: str
    user_id: Optional[str] = None
    priority: int = 0
    tags: List[str] = Field(default_factory=list)
    subject: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    messages: List[Message] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Task-level fields for real-time updates
    updates: List[Dict[str, Any]] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    status: Optional[str] = None

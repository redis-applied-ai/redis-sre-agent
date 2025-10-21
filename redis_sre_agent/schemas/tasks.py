from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from redis_sre_agent.core.thread_state import ThreadStatus


class TaskCreateRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class TaskCreateResponse(BaseModel):
    task_id: str
    thread_id: str
    status: ThreadStatus = ThreadStatus.QUEUED
    message: str = Field("Task accepted", description="Human-friendly status message")


class TaskResponse(BaseModel):
    task_id: str
    thread_id: str
    status: ThreadStatus
    updates: List[Dict[str, Any]] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

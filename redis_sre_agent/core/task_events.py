"""Typed task stream events for WebSocket/stream updates.

Layer: core (domain). No API dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .tasks import TaskUpdate


class TaskStreamEvent(BaseModel):
    """Base event emitted to Redis Streams for task/thread updates.

    Required fields are explicit; additional fields are allowed and preserved
    so existing top-level keys (e.g., status, message) remain unchanged.
    """

    model_config = ConfigDict(extra="allow")

    thread_id: str
    update_type: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InitialStateEvent(TaskStreamEvent):
    """Initial snapshot event sent upon WebSocket connection.

    Updates, result, and error_message come from the latest Task, not the Thread.
    """

    updates: List[TaskUpdate] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

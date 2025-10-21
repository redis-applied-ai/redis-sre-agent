from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from redis_sre_agent.core.thread_state import ThreadStatus


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
    # Minimal updatable fields for now
    subject: Optional[str] = None
    priority: Optional[int] = None
    tags: Optional[List[str]] = None
    context: Optional[Dict[str, Any]] = None


class ThreadAppendMessagesRequest(BaseModel):
    messages: List[Message]


class ThreadResponse(BaseModel):
    thread_id: str
    status: ThreadStatus
    messages: List[Message] = Field(default_factory=list)
    action_items: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)

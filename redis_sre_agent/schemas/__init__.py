"""Pydantic schemas for API requests/responses.

Organizes BaseModel classes separately from domain logic in models/ and core/.
"""

from .tasks import (
    TaskCreateRequest as TaskCreateRequest,
    TaskCreateResponse as TaskCreateResponse,
    TaskResponse as TaskResponse,
)
from .threads import (
    Message as Message,
    ThreadAppendMessagesRequest as ThreadAppendMessagesRequest,
    ThreadCreateRequest as ThreadCreateRequest,
    ThreadResponse as ThreadResponse,
    ThreadUpdateRequest as ThreadUpdateRequest,
)

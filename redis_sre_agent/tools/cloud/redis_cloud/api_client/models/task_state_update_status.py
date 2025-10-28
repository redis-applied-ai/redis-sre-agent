from enum import Enum


class TaskStateUpdateStatus(str, Enum):
    INITIALIZED = "initialized"
    PROCESSING_COMPLETED = "processing-completed"
    PROCESSING_ERROR = "processing-error"
    PROCESSING_IN_PROGRESS = "processing-in-progress"
    RECEIVED = "received"

    def __str__(self) -> str:
        return str(self.value)

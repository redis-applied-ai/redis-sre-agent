from enum import Enum


class BdbVersionUpgradeStatusUpgradeStatus(str, Enum):
    DONE = "done"
    FAILED = "failed"
    IN_PROGRESS = "in-progress"
    IN_PROGRESS_RECOVERY_PENDING = "in-progress-recovery-pending"

    def __str__(self) -> str:
        return str(self.value)

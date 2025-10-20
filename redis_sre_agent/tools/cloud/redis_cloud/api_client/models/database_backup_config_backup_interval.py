from enum import Enum


class DatabaseBackupConfigBackupInterval(str, Enum):
    EVERY_12_HOURS = "EVERY_12_HOURS"
    EVERY_1_HOURS = "EVERY_1_HOURS"
    EVERY_24_HOURS = "EVERY_24_HOURS"
    EVERY_2_HOURS = "EVERY_2_HOURS"
    EVERY_4_HOURS = "EVERY_4_HOURS"
    EVERY_6_HOURS = "EVERY_6_HOURS"

    def __str__(self) -> str:
        return str(self.value)

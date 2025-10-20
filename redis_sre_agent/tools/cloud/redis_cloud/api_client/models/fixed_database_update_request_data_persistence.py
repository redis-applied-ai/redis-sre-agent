from enum import Enum


class FixedDatabaseUpdateRequestDataPersistence(str, Enum):
    AOF_EVERY_1_SECOND = "aof-every-1-second"
    AOF_EVERY_WRITE = "aof-every-write"
    NONE = "none"
    SNAPSHOT_EVERY_12_HOURS = "snapshot-every-12-hours"
    SNAPSHOT_EVERY_1_HOUR = "snapshot-every-1-hour"
    SNAPSHOT_EVERY_6_HOURS = "snapshot-every-6-hours"

    def __str__(self) -> str:
        return str(self.value)

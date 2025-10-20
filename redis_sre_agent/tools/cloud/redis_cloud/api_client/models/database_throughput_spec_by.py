from enum import Enum


class DatabaseThroughputSpecBy(str, Enum):
    NUMBER_OF_SHARDS = "number-of-shards"
    OPERATIONS_PER_SECOND = "operations-per-second"

    def __str__(self) -> str:
        return str(self.value)

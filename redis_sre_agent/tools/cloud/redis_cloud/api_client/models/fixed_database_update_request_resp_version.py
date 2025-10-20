from enum import Enum


class FixedDatabaseUpdateRequestRespVersion(str, Enum):
    RESP2 = "resp2"
    RESP3 = "resp3"

    def __str__(self) -> str:
        return str(self.value)

from enum import Enum


class FixedDatabaseCreateRequestProtocol(str, Enum):
    MEMCACHED = "memcached"
    REDIS = "redis"
    STACK = "stack"

    def __str__(self) -> str:
        return str(self.value)

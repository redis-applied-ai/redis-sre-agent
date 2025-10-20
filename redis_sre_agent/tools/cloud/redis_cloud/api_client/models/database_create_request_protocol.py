from enum import Enum


class DatabaseCreateRequestProtocol(str, Enum):
    MEMCACHED = "memcached"
    REDIS = "redis"

    def __str__(self) -> str:
        return str(self.value)

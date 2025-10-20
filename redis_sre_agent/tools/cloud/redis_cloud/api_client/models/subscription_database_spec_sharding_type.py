from enum import Enum


class SubscriptionDatabaseSpecShardingType(str, Enum):
    CUSTOM_REGEX_RULES = "custom-regex-rules"
    DEFAULT_REGEX_RULES = "default-regex-rules"
    REDIS_OSS_HASHING = "redis-oss-hashing"

    def __str__(self) -> str:
        return str(self.value)

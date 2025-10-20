from enum import Enum


class SubscriptionSpecProvider(str, Enum):
    AWS = "AWS"
    GCP = "GCP"

    def __str__(self) -> str:
        return str(self.value)

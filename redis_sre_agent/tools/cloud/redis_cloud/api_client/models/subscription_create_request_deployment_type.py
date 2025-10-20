from enum import Enum


class SubscriptionCreateRequestDeploymentType(str, Enum):
    ACTIVE_ACTIVE = "active-active"
    SINGLE_REGION = "single-region"

    def __str__(self) -> str:
        return str(self.value)

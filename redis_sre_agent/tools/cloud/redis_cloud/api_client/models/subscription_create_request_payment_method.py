from enum import Enum


class SubscriptionCreateRequestPaymentMethod(str, Enum):
    CREDIT_CARD = "credit-card"
    MARKETPLACE = "marketplace"

    def __str__(self) -> str:
        return str(self.value)

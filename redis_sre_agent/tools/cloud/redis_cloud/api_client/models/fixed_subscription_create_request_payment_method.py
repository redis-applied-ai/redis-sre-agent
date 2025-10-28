from enum import Enum


class FixedSubscriptionCreateRequestPaymentMethod(str, Enum):
    CREDIT_CARD = "credit-card"
    MARKETPLACE = "marketplace"

    def __str__(self) -> str:
        return str(self.value)

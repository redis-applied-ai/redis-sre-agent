from enum import Enum


class SubscriptionCreateRequestPersistentStorageEncryptionType(str, Enum):
    CLOUD_PROVIDER_MANAGED_KEY = "cloud-provider-managed-key"
    CUSTOMER_MANAGED_KEY = "customer-managed-key"

    def __str__(self) -> str:
        return str(self.value)

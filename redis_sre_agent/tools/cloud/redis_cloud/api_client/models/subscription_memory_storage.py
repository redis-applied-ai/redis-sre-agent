from enum import Enum


class SubscriptionMemoryStorage(str, Enum):
    RAM = "ram"
    RAM_AND_FLASH = "ram-and-flash"

    def __str__(self) -> str:
        return str(self.value)

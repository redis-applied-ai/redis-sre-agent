from enum import Enum


class CustomerManagedKeyPropertiesDeletionGracePeriod(str, Enum):
    ALERTS_ONLY = "alerts-only"
    IMMEDIATE = "immediate"
    VALUE_2 = "15-minutes"
    VALUE_3 = "30-minutes"
    VALUE_4 = "1-hour"
    VALUE_5 = "4-hours"
    VALUE_6 = "8-hours"
    VALUE_7 = "12-hours"
    VALUE_8 = "24-hours"

    def __str__(self) -> str:
        return str(self.value)

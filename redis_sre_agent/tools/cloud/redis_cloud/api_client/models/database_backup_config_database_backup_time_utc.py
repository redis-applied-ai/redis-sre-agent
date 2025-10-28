from enum import Enum


class DatabaseBackupConfigDatabaseBackupTimeUTC(str, Enum):
    HOUR_EIGHT = "HOUR_EIGHT"
    HOUR_ELEVEN = "HOUR_ELEVEN"
    HOUR_FIVE = "HOUR_FIVE"
    HOUR_FOUR = "HOUR_FOUR"
    HOUR_NINE = "HOUR_NINE"
    HOUR_ONE = "HOUR_ONE"
    HOUR_SEVEN = "HOUR_SEVEN"
    HOUR_SIX = "HOUR_SIX"
    HOUR_TEN = "HOUR_TEN"
    HOUR_THREE = "HOUR_THREE"
    HOUR_TWELVE = "HOUR_TWELVE"
    HOUR_TWO = "HOUR_TWO"

    def __str__(self) -> str:
        return str(self.value)

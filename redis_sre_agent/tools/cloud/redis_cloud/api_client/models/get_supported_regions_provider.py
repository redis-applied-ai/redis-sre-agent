from enum import Enum


class GetSupportedRegionsProvider(str, Enum):
    AWS = "AWS"
    GCP = "GCP"

    def __str__(self) -> str:
        return str(self.value)

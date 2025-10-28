from enum import Enum


class CloudAccountCreateRequestProvider(str, Enum):
    AWS = "AWS"
    GCP = "GCP"

    def __str__(self) -> str:
        return str(self.value)

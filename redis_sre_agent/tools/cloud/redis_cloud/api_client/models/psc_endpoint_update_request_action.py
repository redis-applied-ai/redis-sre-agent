from enum import Enum


class PscEndpointUpdateRequestAction(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"

    def __str__(self) -> str:
        return str(self.value)

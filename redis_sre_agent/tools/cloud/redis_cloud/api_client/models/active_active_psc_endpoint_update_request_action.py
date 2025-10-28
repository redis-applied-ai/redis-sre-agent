from enum import Enum


class ActiveActivePscEndpointUpdateRequestAction(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"

    def __str__(self) -> str:
        return str(self.value)

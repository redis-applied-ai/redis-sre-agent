from enum import Enum


class AccountUserUpdateRequestRole(str, Enum):
    BILLING_ADMIN = "Billing Admin"
    LOGS_VIEWER_API_USE_ONLY = "Logs Viewer (API use only)"
    MANAGER = "Manager"
    MEMBER = "Member"
    OWNER = "Owner"
    VIEWER = "Viewer"

    def __str__(self) -> str:
        return str(self.value)

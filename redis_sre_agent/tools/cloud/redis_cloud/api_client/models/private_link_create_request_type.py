from enum import Enum


class PrivateLinkCreateRequestType(str, Enum):
    AWS_ACCOUNT = "aws_account"
    IAM_ROLE = "iam_role"
    IAM_USER = "iam_user"
    ORGANIZATION = "organization"
    ORGANIZATION_UNIT = "organization_unit"
    SERVICE_PRINCIPAL = "service_principal"

    def __str__(self) -> str:
        return str(self.value)

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.customer_managed_key_access_details_required_key_policy_statements import (
        CustomerManagedKeyAccessDetailsRequiredKeyPolicyStatements,
    )


T = TypeVar("T", bound="CustomerManagedKeyAccessDetails")


@_attrs_define
class CustomerManagedKeyAccessDetails:
    """Configuration regarding customer managed persistent storage encryption

    Attributes:
        redis_service_account (Union[Unset, str]):
        google_predefined_roles (Union[Unset, list[str]]):
        google_custom_permissions (Union[Unset, list[str]]):
        redis_iam_role (Union[Unset, str]):
        required_key_policy_statements (Union[Unset, CustomerManagedKeyAccessDetailsRequiredKeyPolicyStatements]):
        deletion_grace_period_options (Union[Unset, list[str]]):
    """

    redis_service_account: Union[Unset, str] = UNSET
    google_predefined_roles: Union[Unset, list[str]] = UNSET
    google_custom_permissions: Union[Unset, list[str]] = UNSET
    redis_iam_role: Union[Unset, str] = UNSET
    required_key_policy_statements: Union[Unset, "CustomerManagedKeyAccessDetailsRequiredKeyPolicyStatements"] = UNSET
    deletion_grace_period_options: Union[Unset, list[str]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        redis_service_account = self.redis_service_account

        google_predefined_roles: Union[Unset, list[str]] = UNSET
        if not isinstance(self.google_predefined_roles, Unset):
            google_predefined_roles = self.google_predefined_roles

        google_custom_permissions: Union[Unset, list[str]] = UNSET
        if not isinstance(self.google_custom_permissions, Unset):
            google_custom_permissions = self.google_custom_permissions

        redis_iam_role = self.redis_iam_role

        required_key_policy_statements: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.required_key_policy_statements, Unset):
            required_key_policy_statements = self.required_key_policy_statements.to_dict()

        deletion_grace_period_options: Union[Unset, list[str]] = UNSET
        if not isinstance(self.deletion_grace_period_options, Unset):
            deletion_grace_period_options = self.deletion_grace_period_options

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if redis_service_account is not UNSET:
            field_dict["redisServiceAccount"] = redis_service_account
        if google_predefined_roles is not UNSET:
            field_dict["googlePredefinedRoles"] = google_predefined_roles
        if google_custom_permissions is not UNSET:
            field_dict["googleCustomPermissions"] = google_custom_permissions
        if redis_iam_role is not UNSET:
            field_dict["redisIamRole"] = redis_iam_role
        if required_key_policy_statements is not UNSET:
            field_dict["requiredKeyPolicyStatements"] = required_key_policy_statements
        if deletion_grace_period_options is not UNSET:
            field_dict["deletionGracePeriodOptions"] = deletion_grace_period_options

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.customer_managed_key_access_details_required_key_policy_statements import (
            CustomerManagedKeyAccessDetailsRequiredKeyPolicyStatements,
        )

        d = dict(src_dict)
        redis_service_account = d.pop("redisServiceAccount", UNSET)

        google_predefined_roles = cast(list[str], d.pop("googlePredefinedRoles", UNSET))

        google_custom_permissions = cast(list[str], d.pop("googleCustomPermissions", UNSET))

        redis_iam_role = d.pop("redisIamRole", UNSET)

        _required_key_policy_statements = d.pop("requiredKeyPolicyStatements", UNSET)
        required_key_policy_statements: Union[Unset, CustomerManagedKeyAccessDetailsRequiredKeyPolicyStatements]
        if isinstance(_required_key_policy_statements, Unset):
            required_key_policy_statements = UNSET
        else:
            required_key_policy_statements = CustomerManagedKeyAccessDetailsRequiredKeyPolicyStatements.from_dict(
                _required_key_policy_statements
            )

        deletion_grace_period_options = cast(list[str], d.pop("deletionGracePeriodOptions", UNSET))

        customer_managed_key_access_details = cls(
            redis_service_account=redis_service_account,
            google_predefined_roles=google_predefined_roles,
            google_custom_permissions=google_custom_permissions,
            redis_iam_role=redis_iam_role,
            required_key_policy_statements=required_key_policy_statements,
            deletion_grace_period_options=deletion_grace_period_options,
        )

        customer_managed_key_access_details.additional_properties = d
        return customer_managed_key_access_details

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties

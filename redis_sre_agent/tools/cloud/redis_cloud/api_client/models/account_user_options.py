from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AccountUserOptions")


@_attrs_define
class AccountUserOptions:
    """RedisLabs User options information

    Attributes:
        billing (Union[Unset, bool]):
        email_alerts (Union[Unset, bool]):
        operational_emails (Union[Unset, bool]):
        mfa_enabled (Union[Unset, bool]):
    """

    billing: Union[Unset, bool] = UNSET
    email_alerts: Union[Unset, bool] = UNSET
    operational_emails: Union[Unset, bool] = UNSET
    mfa_enabled: Union[Unset, bool] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        billing = self.billing

        email_alerts = self.email_alerts

        operational_emails = self.operational_emails

        mfa_enabled = self.mfa_enabled

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if billing is not UNSET:
            field_dict["billing"] = billing
        if email_alerts is not UNSET:
            field_dict["emailAlerts"] = email_alerts
        if operational_emails is not UNSET:
            field_dict["operationalEmails"] = operational_emails
        if mfa_enabled is not UNSET:
            field_dict["mfaEnabled"] = mfa_enabled

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        billing = d.pop("billing", UNSET)

        email_alerts = d.pop("emailAlerts", UNSET)

        operational_emails = d.pop("operationalEmails", UNSET)

        mfa_enabled = d.pop("mfaEnabled", UNSET)

        account_user_options = cls(
            billing=billing,
            email_alerts=email_alerts,
            operational_emails=operational_emails,
            mfa_enabled=mfa_enabled,
        )

        account_user_options.additional_properties = d
        return account_user_options

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

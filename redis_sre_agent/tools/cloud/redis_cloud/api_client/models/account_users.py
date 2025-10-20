from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AccountUsers")


@_attrs_define
class AccountUsers:
    """RedisLabs list of users in current account

    Example:
        {'account': 1001, 'users': [{'id': 60192, 'name': "Clifford O'neill", 'email': 'clifford.mail@gmail.com',
            'role': 'Viewer', 'userType': 'Local', 'hasApiKey': False, 'options': {'billing': False, 'emailAlerts': False,
            'operationalEmails': False, 'mfaEnabled': False}}]}

    Attributes:
        account (Union[Unset, int]):
    """

    account: Union[Unset, int] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        account = self.account

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if account is not UNSET:
            field_dict["account"] = account

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        account = d.pop("account", UNSET)

        account_users = cls(
            account=account,
        )

        account_users.additional_properties = d
        return account_users

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

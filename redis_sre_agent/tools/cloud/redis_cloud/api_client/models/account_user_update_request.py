from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.account_user_update_request_role import AccountUserUpdateRequestRole
from ..types import UNSET, Unset

T = TypeVar("T", bound="AccountUserUpdateRequest")


@_attrs_define
class AccountUserUpdateRequest:
    """User update request

    Attributes:
        name (str): The account user's name. Example: My new user name.
        user_id (Union[Unset, int]):
        role (Union[Unset, AccountUserUpdateRequestRole]): Changes the account user's role. See [Team management
            roles](https://redis.io/docs/latest/operate/rc/security/access-control/access-management/#team-management-roles)
            to learn about available account roles.
        command_type (Union[Unset, str]):
    """

    name: str
    user_id: Union[Unset, int] = UNSET
    role: Union[Unset, AccountUserUpdateRequestRole] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        user_id = self.user_id

        role: Union[Unset, str] = UNSET
        if not isinstance(self.role, Unset):
            role = self.role.value

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
            }
        )
        if user_id is not UNSET:
            field_dict["userId"] = user_id
        if role is not UNSET:
            field_dict["role"] = role
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        user_id = d.pop("userId", UNSET)

        _role = d.pop("role", UNSET)
        role: Union[Unset, AccountUserUpdateRequestRole]
        if isinstance(_role, Unset):
            role = UNSET
        else:
            role = AccountUserUpdateRequestRole(_role)

        command_type = d.pop("commandType", UNSET)

        account_user_update_request = cls(
            name=name,
            user_id=user_id,
            role=role,
            command_type=command_type,
        )

        account_user_update_request.additional_properties = d
        return account_user_update_request

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

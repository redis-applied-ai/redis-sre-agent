from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AclUserUpdateRequest")


@_attrs_define
class AclUserUpdateRequest:
    """ACL user update request

    Attributes:
        user_id (Union[Unset, int]):
        role (Union[Unset, str]): Optional. Changes the ACL role assigned to the user. Use GET '/acl/roles' to get a
            list of database access roles. Example: ACL-role-example.
        password (Union[Unset, str]): Optional. Changes the user's database password. Example: ab123AB$%^.
        command_type (Union[Unset, str]):
    """

    user_id: Union[Unset, int] = UNSET
    role: Union[Unset, str] = UNSET
    password: Union[Unset, str] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        user_id = self.user_id

        role = self.role

        password = self.password

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if user_id is not UNSET:
            field_dict["userId"] = user_id
        if role is not UNSET:
            field_dict["role"] = role
        if password is not UNSET:
            field_dict["password"] = password
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        user_id = d.pop("userId", UNSET)

        role = d.pop("role", UNSET)

        password = d.pop("password", UNSET)

        command_type = d.pop("commandType", UNSET)

        acl_user_update_request = cls(
            user_id=user_id,
            role=role,
            password=password,
            command_type=command_type,
        )

        acl_user_update_request.additional_properties = d
        return acl_user_update_request

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

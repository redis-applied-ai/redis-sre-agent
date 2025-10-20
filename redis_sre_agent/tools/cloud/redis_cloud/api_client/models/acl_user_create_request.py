from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AclUserCreateRequest")


@_attrs_define
class AclUserCreateRequest:
    """ACL user create request

    Attributes:
        name (str): Access control user name. Example: ACL-user-example.
        role (str): Name of the database access role to assign to this user. Use GET '/acl/roles' to get a list of
            database access roles. Example: ACL-role-example.
        password (str): The database password for this user. Example: ab123AB$%^.
        command_type (Union[Unset, str]):
    """

    name: str
    role: str
    password: str
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        role = self.role

        password = self.password

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "role": role,
                "password": password,
            }
        )
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        role = d.pop("role")

        password = d.pop("password")

        command_type = d.pop("commandType", UNSET)

        acl_user_create_request = cls(
            name=name,
            role=role,
            password=password,
            command_type=command_type,
        )

        acl_user_create_request.additional_properties = d
        return acl_user_create_request

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

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.acl_user_links_item import ACLUserLinksItem


T = TypeVar("T", bound="ACLUser")


@_attrs_define
class ACLUser:
    """Redis ACL user information

    Example:
        {'id': 1, 'name': 'abc', 'role': 'role-name', 'status': 'active'}

    Attributes:
        id (Union[Unset, int]):
        name (Union[Unset, str]):
        role (Union[Unset, str]):
        status (Union[Unset, str]):
        links (Union[Unset, list['ACLUserLinksItem']]):
    """

    id: Union[Unset, int] = UNSET
    name: Union[Unset, str] = UNSET
    role: Union[Unset, str] = UNSET
    status: Union[Unset, str] = UNSET
    links: Union[Unset, list["ACLUserLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        role = self.role

        status = self.status

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if name is not UNSET:
            field_dict["name"] = name
        if role is not UNSET:
            field_dict["role"] = role
        if status is not UNSET:
            field_dict["status"] = status
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.acl_user_links_item import ACLUserLinksItem

        d = dict(src_dict)
        id = d.pop("id", UNSET)

        name = d.pop("name", UNSET)

        role = d.pop("role", UNSET)

        status = d.pop("status", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = ACLUserLinksItem.from_dict(links_item_data)

            links.append(links_item)

        acl_user = cls(
            id=id,
            name=name,
            role=role,
            status=status,
            links=links,
        )

        acl_user.additional_properties = d
        return acl_user

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

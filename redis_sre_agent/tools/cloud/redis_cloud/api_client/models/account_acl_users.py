from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.account_acl_users_links_item import AccountACLUsersLinksItem


T = TypeVar("T", bound="AccountACLUsers")


@_attrs_define
class AccountACLUsers:
    """Redis list of ACL users in current account

    Example:
        {'accountId': 1001, 'users': [{'id': 1, 'name': 'user', 'role': 'role-name', 'status': 'active', 'links': []}]}

    Attributes:
        account_id (Union[Unset, int]):
        links (Union[Unset, list['AccountACLUsersLinksItem']]):
    """

    account_id: Union[Unset, int] = UNSET
    links: Union[Unset, list["AccountACLUsersLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        account_id = self.account_id

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if account_id is not UNSET:
            field_dict["accountId"] = account_id
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.account_acl_users_links_item import AccountACLUsersLinksItem

        d = dict(src_dict)
        account_id = d.pop("accountId", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = AccountACLUsersLinksItem.from_dict(links_item_data)

            links.append(links_item)

        account_acl_users = cls(
            account_id=account_id,
            links=links,
        )

        account_acl_users.additional_properties = d
        return account_acl_users

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

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.root_account_links_item import RootAccountLinksItem


T = TypeVar("T", bound="RootAccount")


@_attrs_define
class RootAccount:
    """
    Example:
        {'account': {'id': 1001, 'name': 'Redis', 'createdTimestamp': '2018-12-23T15:15:31Z', 'updatedTimestamp':
            '2022-10-12T10:54:10Z', 'pocStatus': 'inactive', 'marketplaceStatus': 'active', 'key': {'name': 'capi-api-key-
            name', 'accountId': 1001, 'accountName': 'Redis', 'allowedSourceIps': ['0.0.0.0/0'], 'createdTimestamp':
            '2022-05-11T12:05:47Z', 'owner': {'name': 'CAPI user', 'email': 'capi.user@redis.com'}, 'userAccountId': 1,
            'httpSourceIp': '79.0.0.173'}}}

    Attributes:
        links (Union[Unset, list['RootAccountLinksItem']]):
    """

    links: Union[Unset, list["RootAccountLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.root_account_links_item import RootAccountLinksItem

        d = dict(src_dict)
        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = RootAccountLinksItem.from_dict(links_item_data)

            links.append(links_item)

        root_account = cls(
            links=links,
        )

        root_account.additional_properties = d
        return root_account

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

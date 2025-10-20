from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.cloud_accounts_links_item import CloudAccountsLinksItem


T = TypeVar("T", bound="CloudAccounts")


@_attrs_define
class CloudAccounts:
    """RedisLabs Cloud Accounts information

    Example:
        {'accountId': 40131, 'cloudAccounts': [{'id': 1, 'name': 'Redis Internal Resources', 'provider': 'AWS',
            'status': 'active', 'links': []}, {'id': 2, 'name': 'CAPI User ', 'provider': 'AWS', 'status': 'active',
            'accessKeyId': 'A***A', 'links': []}, {'id': 3, 'name': 'API Cloud account', 'provider': 'AWS', 'status':
            'active', 'accessKeyId': 'A***4', 'links': []}], 'links': [{'rel': 'self', 'href': 'https://api-
            cloudapi.qa.redislabs.com/v1/cloud-accounts', 'type': 'GET'}]}

    Attributes:
        account_id (Union[Unset, int]):
        links (Union[Unset, list['CloudAccountsLinksItem']]):
    """

    account_id: Union[Unset, int] = UNSET
    links: Union[Unset, list["CloudAccountsLinksItem"]] = UNSET
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
        from ..models.cloud_accounts_links_item import CloudAccountsLinksItem

        d = dict(src_dict)
        account_id = d.pop("accountId", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = CloudAccountsLinksItem.from_dict(links_item_data)

            links.append(links_item)

        cloud_accounts = cls(
            account_id=account_id,
            links=links,
        )

        cloud_accounts.additional_properties = d
        return cloud_accounts

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

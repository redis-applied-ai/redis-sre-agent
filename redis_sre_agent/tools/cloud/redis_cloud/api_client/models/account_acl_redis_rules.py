from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.account_acl_redis_rules_links_item import AccountACLRedisRulesLinksItem


T = TypeVar("T", bound="AccountACLRedisRules")


@_attrs_define
class AccountACLRedisRules:
    """Redis list of ACL redis rules in current account

    Example:
        {'accountId': 1001, 'redisRules': [{'id': 7, 'name': 'Full-Access', 'acl': '+@all  ~*', 'isDefault': True,
            'status': 'active'}, {'id': 8, 'name': 'Read-Write', 'acl': '+@all -@dangerous ~*', 'isDefault': True, 'status':
            'active'}, {'id': 9, 'name': 'Read-Only', 'acl': '+@read ~*', 'isDefault': True, 'status': 'active'}]}

    Attributes:
        account_id (Union[Unset, int]):
        links (Union[Unset, list['AccountACLRedisRulesLinksItem']]):
    """

    account_id: Union[Unset, int] = UNSET
    links: Union[Unset, list["AccountACLRedisRulesLinksItem"]] = UNSET
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
        from ..models.account_acl_redis_rules_links_item import AccountACLRedisRulesLinksItem

        d = dict(src_dict)
        account_id = d.pop("accountId", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = AccountACLRedisRulesLinksItem.from_dict(links_item_data)

            links.append(links_item)

        account_acl_redis_rules = cls(
            account_id=account_id,
            links=links,
        )

        account_acl_redis_rules.additional_properties = d
        return account_acl_redis_rules

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

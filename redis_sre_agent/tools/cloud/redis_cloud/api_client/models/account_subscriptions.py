from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.account_subscriptions_links_item import AccountSubscriptionsLinksItem


T = TypeVar("T", bound="AccountSubscriptions")


@_attrs_define
class AccountSubscriptions:
    """RedisLabs list of subscriptions in current account

    Example:
        {'accountId': 1001, 'subscriptions': [{'id': 1206, 'name': 'subscription name', 'status': 'active',
            'deploymentType': 'single-region', 'paymentMethodId': 123, 'memoryStorage': 'ram', 'numberOfDatabases': 6,
            'paymentMethodType': 'credit-card', 'storageEncryption': False, 'subscriptionPricing': [{'type': 'Shards',
            'typeDetails': 'high-throughput', 'quantity': 7, 'quantityMeasurement': 'shards', 'pricePerUnit': 0.124,
            'priceCurrency': 'USD', 'pricePeriod': 'hour'}], 'cloudDetails': [{'provider': 'AWS', 'cloudAccountId': 1666,
            'totalSizeInGb': 0.0272, 'regions': [{'region': 'us-east-1', 'networking': [{'deploymentCIDR': '10.0.0.0/24',
            'subnetId': 'subnet-009ce004ed90da8a6'}], 'preferredAvailabilityZones': ['us-east-1a'],
            'multipleAvailabilityZones': False}], 'links': []}], 'links': []}]}

    Attributes:
        account_id (Union[Unset, int]):
        links (Union[Unset, list['AccountSubscriptionsLinksItem']]):
    """

    account_id: Union[Unset, int] = UNSET
    links: Union[Unset, list["AccountSubscriptionsLinksItem"]] = UNSET
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
        from ..models.account_subscriptions_links_item import AccountSubscriptionsLinksItem

        d = dict(src_dict)
        account_id = d.pop("accountId", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = AccountSubscriptionsLinksItem.from_dict(links_item_data)

            links.append(links_item)

        account_subscriptions = cls(
            account_id=account_id,
            links=links,
        )

        account_subscriptions.additional_properties = d
        return account_subscriptions

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

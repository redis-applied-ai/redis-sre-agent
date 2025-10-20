from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.active_active_subscription_regions_links_item import ActiveActiveSubscriptionRegionsLinksItem


T = TypeVar("T", bound="ActiveActiveSubscriptionRegions")


@_attrs_define
class ActiveActiveSubscriptionRegions:
    """List of active-active subscription regions

    Example:
        {'subscriptionId': 126, 'regions': [{'regionId': 1, 'region': 'us-east-1', 'deploymentCidr': '10.0.0.0/24',
            'vpcId': 'vpc-0bf863584c46321e4', 'databases': [{'databaseId': 862, 'databaseName': 'Bdb',
            'readOperationsPerSecond': 500, 'writeOperationsPerSecond': 500, 'respVersion': 'resp3', 'links': []},
            {'databaseId': 864, 'databaseName': 'Bdb2', 'readOperationsPerSecond': 1000, 'writeOperationsPerSecond': 1000,
            'respVersion': 'resp3', 'links': []}], 'links': []}, {'regionId': 4, 'region': 'eu-west-1', 'deploymentCidr':
            '10.0.1.0/24', 'vpcId': 'vpc-0108fb753063ecf8b', 'databases': [{'databaseId': 862, 'databaseName': 'Bdb',
            'readOperationsPerSecond': 500, 'writeOperationsPerSecond': 500, 'respVersion': 'resp3', 'links': []},
            {'databaseId': 864, 'databaseName': 'Bdb2', 'readOperationsPerSecond': 1000, 'writeOperationsPerSecond': 1000,
            'respVersion': 'resp3', 'links': []}], 'links': []}], 'links': [{'rel': 'self', 'href': 'https://api-
            cloudapi.qa.redislabs.com/v1/subscriptions/133876/regions', 'type': 'GET'}]}

    Attributes:
        subscription_id (Union[Unset, int]):
        links (Union[Unset, list['ActiveActiveSubscriptionRegionsLinksItem']]):
    """

    subscription_id: Union[Unset, int] = UNSET
    links: Union[Unset, list["ActiveActiveSubscriptionRegionsLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.active_active_subscription_regions_links_item import ActiveActiveSubscriptionRegionsLinksItem

        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = ActiveActiveSubscriptionRegionsLinksItem.from_dict(links_item_data)

            links.append(links_item)

        active_active_subscription_regions = cls(
            subscription_id=subscription_id,
            links=links,
        )

        active_active_subscription_regions.additional_properties = d
        return active_active_subscription_regions

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

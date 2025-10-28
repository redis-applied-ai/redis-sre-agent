from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.fixed_subscriptions_plans_links_item import FixedSubscriptionsPlansLinksItem


T = TypeVar("T", bound="FixedSubscriptionsPlans")


@_attrs_define
class FixedSubscriptionsPlans:
    """Redis list of Essentials subscriptions plans

    Example:
        {'plans': [{'id': 98183, 'name': 'Multi-AZ 5GB', 'size': 5, 'sizeMeasurementUnit': 'GB', 'provider': 'AWS',
            'region': 'us-east-1', 'regionId': 1, 'price': 100, 'priceCurrency': 'USD', 'pricePeriod': 'Month',
            'maximumDatabases': 1, 'availability': 'Multi-zone', 'connections': 'unlimited', 'cidrAllowRules': 16,
            'supportDataPersistence': True, 'supportInstantAndDailyBackups': True, 'supportReplication': True,
            'supportClustering': False, 'supportSsl': True, 'supportedAlerts': ['datasets-size', 'latency', 'throughput-
            lower-than', 'throughput-higher-than'], 'customerSupport': 'Standard', 'links': []}, {'id': 98181, 'name':
            'Multi-AZ 1GB', 'size': 1, 'sizeMeasurementUnit': 'GB', 'provider': 'AWS', 'region': 'us-east-1', 'regionId': 1,
            'price': 22, 'priceCurrency': 'USD', 'pricePeriod': 'Month', 'maximumDatabases': 1, 'availability': 'Multi-
            zone', 'connections': '1024', 'cidrAllowRules': 8, 'supportDataPersistence': True,
            'supportInstantAndDailyBackups': True, 'supportReplication': True, 'supportClustering': False, 'supportSsl':
            True, 'supportedAlerts': ['datasets-size', 'throughput-higher-than', 'throughput-lower-than', 'latency',
            'connections-limit'], 'customerSupport': 'Standard', 'links': []}], 'links': [{'rel': 'self', 'href':
            'http://localhost:8081/v1/fixed/plans?cloud_provider=AWS', 'type': 'GET'}]}

    Attributes:
        links (Union[Unset, list['FixedSubscriptionsPlansLinksItem']]):
    """

    links: Union[Unset, list["FixedSubscriptionsPlansLinksItem"]] = UNSET
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
        from ..models.fixed_subscriptions_plans_links_item import FixedSubscriptionsPlansLinksItem

        d = dict(src_dict)
        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = FixedSubscriptionsPlansLinksItem.from_dict(links_item_data)

            links.append(links_item)

        fixed_subscriptions_plans = cls(
            links=links,
        )

        fixed_subscriptions_plans.additional_properties = d
        return fixed_subscriptions_plans

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

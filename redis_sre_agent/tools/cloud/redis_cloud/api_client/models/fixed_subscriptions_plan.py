from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.fixed_subscriptions_plan_links_item import FixedSubscriptionsPlanLinksItem


T = TypeVar("T", bound="FixedSubscriptionsPlan")


@_attrs_define
class FixedSubscriptionsPlan:
    """Redis Essentials subscription plan information

    Example:
        {'id': 98273, 'name': 'Cache 5GB', 'size': 5, 'sizeMeasurementUnit': 'GB', 'provider': 'AWS', 'region': 'eu-
            west-1', 'regionId': 4, 'price': 77, 'priceCurrency': 'USD', 'pricePeriod': 'Month', 'maximumDatabases': 1,
            'availability': 'No replication', 'connections': 'unlimited', 'cidrAllowRules': 4, 'supportDataPersistence':
            True, 'supportInstantAndDailyBackups': True, 'supportReplication': False, 'supportClustering': True,
            'supportSsl': False, 'supportedAlerts': ['throughput-higher-than'], 'customerSupport': 'Standard', 'links':
            [{'rel': 'self', 'href': 'http://localhost:8081/v1/fixed/plans/16583', 'type': 'GET'}]}

    Attributes:
        id (Union[Unset, int]):
        name (Union[Unset, str]):
        size (Union[Unset, float]):
        dataset_size (Union[Unset, float]):
        size_measurement_unit (Union[Unset, str]):
        provider (Union[Unset, str]):
        region (Union[Unset, str]):
        region_id (Union[Unset, int]):
        price (Union[Unset, int]):
        price_currency (Union[Unset, str]):
        price_period (Union[Unset, str]):
        maximum_databases (Union[Unset, int]):
        maximum_throughput (Union[Unset, int]):
        maximum_bandwidth_gb (Union[Unset, int]):
        availability (Union[Unset, str]):
        connections (Union[Unset, str]):
        cidr_allow_rules (Union[Unset, int]):
        support_data_persistence (Union[Unset, bool]):
        redis_flex (Union[Unset, bool]):
        support_instant_and_daily_backups (Union[Unset, bool]):
        support_replication (Union[Unset, bool]):
        support_clustering (Union[Unset, bool]):
        support_ssl (Union[Unset, bool]):
        customer_support (Union[Unset, str]):
        links (Union[Unset, list['FixedSubscriptionsPlanLinksItem']]):
    """

    id: Union[Unset, int] = UNSET
    name: Union[Unset, str] = UNSET
    size: Union[Unset, float] = UNSET
    dataset_size: Union[Unset, float] = UNSET
    size_measurement_unit: Union[Unset, str] = UNSET
    provider: Union[Unset, str] = UNSET
    region: Union[Unset, str] = UNSET
    region_id: Union[Unset, int] = UNSET
    price: Union[Unset, int] = UNSET
    price_currency: Union[Unset, str] = UNSET
    price_period: Union[Unset, str] = UNSET
    maximum_databases: Union[Unset, int] = UNSET
    maximum_throughput: Union[Unset, int] = UNSET
    maximum_bandwidth_gb: Union[Unset, int] = UNSET
    availability: Union[Unset, str] = UNSET
    connections: Union[Unset, str] = UNSET
    cidr_allow_rules: Union[Unset, int] = UNSET
    support_data_persistence: Union[Unset, bool] = UNSET
    redis_flex: Union[Unset, bool] = UNSET
    support_instant_and_daily_backups: Union[Unset, bool] = UNSET
    support_replication: Union[Unset, bool] = UNSET
    support_clustering: Union[Unset, bool] = UNSET
    support_ssl: Union[Unset, bool] = UNSET
    customer_support: Union[Unset, str] = UNSET
    links: Union[Unset, list["FixedSubscriptionsPlanLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        size = self.size

        dataset_size = self.dataset_size

        size_measurement_unit = self.size_measurement_unit

        provider = self.provider

        region = self.region

        region_id = self.region_id

        price = self.price

        price_currency = self.price_currency

        price_period = self.price_period

        maximum_databases = self.maximum_databases

        maximum_throughput = self.maximum_throughput

        maximum_bandwidth_gb = self.maximum_bandwidth_gb

        availability = self.availability

        connections = self.connections

        cidr_allow_rules = self.cidr_allow_rules

        support_data_persistence = self.support_data_persistence

        redis_flex = self.redis_flex

        support_instant_and_daily_backups = self.support_instant_and_daily_backups

        support_replication = self.support_replication

        support_clustering = self.support_clustering

        support_ssl = self.support_ssl

        customer_support = self.customer_support

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
        if size is not UNSET:
            field_dict["size"] = size
        if dataset_size is not UNSET:
            field_dict["datasetSize"] = dataset_size
        if size_measurement_unit is not UNSET:
            field_dict["sizeMeasurementUnit"] = size_measurement_unit
        if provider is not UNSET:
            field_dict["provider"] = provider
        if region is not UNSET:
            field_dict["region"] = region
        if region_id is not UNSET:
            field_dict["regionId"] = region_id
        if price is not UNSET:
            field_dict["price"] = price
        if price_currency is not UNSET:
            field_dict["priceCurrency"] = price_currency
        if price_period is not UNSET:
            field_dict["pricePeriod"] = price_period
        if maximum_databases is not UNSET:
            field_dict["maximumDatabases"] = maximum_databases
        if maximum_throughput is not UNSET:
            field_dict["maximumThroughput"] = maximum_throughput
        if maximum_bandwidth_gb is not UNSET:
            field_dict["maximumBandwidthGB"] = maximum_bandwidth_gb
        if availability is not UNSET:
            field_dict["availability"] = availability
        if connections is not UNSET:
            field_dict["connections"] = connections
        if cidr_allow_rules is not UNSET:
            field_dict["cidrAllowRules"] = cidr_allow_rules
        if support_data_persistence is not UNSET:
            field_dict["supportDataPersistence"] = support_data_persistence
        if redis_flex is not UNSET:
            field_dict["redisFlex"] = redis_flex
        if support_instant_and_daily_backups is not UNSET:
            field_dict["supportInstantAndDailyBackups"] = support_instant_and_daily_backups
        if support_replication is not UNSET:
            field_dict["supportReplication"] = support_replication
        if support_clustering is not UNSET:
            field_dict["supportClustering"] = support_clustering
        if support_ssl is not UNSET:
            field_dict["supportSsl"] = support_ssl
        if customer_support is not UNSET:
            field_dict["customerSupport"] = customer_support
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.fixed_subscriptions_plan_links_item import FixedSubscriptionsPlanLinksItem

        d = dict(src_dict)
        id = d.pop("id", UNSET)

        name = d.pop("name", UNSET)

        size = d.pop("size", UNSET)

        dataset_size = d.pop("datasetSize", UNSET)

        size_measurement_unit = d.pop("sizeMeasurementUnit", UNSET)

        provider = d.pop("provider", UNSET)

        region = d.pop("region", UNSET)

        region_id = d.pop("regionId", UNSET)

        price = d.pop("price", UNSET)

        price_currency = d.pop("priceCurrency", UNSET)

        price_period = d.pop("pricePeriod", UNSET)

        maximum_databases = d.pop("maximumDatabases", UNSET)

        maximum_throughput = d.pop("maximumThroughput", UNSET)

        maximum_bandwidth_gb = d.pop("maximumBandwidthGB", UNSET)

        availability = d.pop("availability", UNSET)

        connections = d.pop("connections", UNSET)

        cidr_allow_rules = d.pop("cidrAllowRules", UNSET)

        support_data_persistence = d.pop("supportDataPersistence", UNSET)

        redis_flex = d.pop("redisFlex", UNSET)

        support_instant_and_daily_backups = d.pop("supportInstantAndDailyBackups", UNSET)

        support_replication = d.pop("supportReplication", UNSET)

        support_clustering = d.pop("supportClustering", UNSET)

        support_ssl = d.pop("supportSsl", UNSET)

        customer_support = d.pop("customerSupport", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = FixedSubscriptionsPlanLinksItem.from_dict(links_item_data)

            links.append(links_item)

        fixed_subscriptions_plan = cls(
            id=id,
            name=name,
            size=size,
            dataset_size=dataset_size,
            size_measurement_unit=size_measurement_unit,
            provider=provider,
            region=region,
            region_id=region_id,
            price=price,
            price_currency=price_currency,
            price_period=price_period,
            maximum_databases=maximum_databases,
            maximum_throughput=maximum_throughput,
            maximum_bandwidth_gb=maximum_bandwidth_gb,
            availability=availability,
            connections=connections,
            cidr_allow_rules=cidr_allow_rules,
            support_data_persistence=support_data_persistence,
            redis_flex=redis_flex,
            support_instant_and_daily_backups=support_instant_and_daily_backups,
            support_replication=support_replication,
            support_clustering=support_clustering,
            support_ssl=support_ssl,
            customer_support=customer_support,
            links=links,
        )

        fixed_subscriptions_plan.additional_properties = d
        return fixed_subscriptions_plan

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

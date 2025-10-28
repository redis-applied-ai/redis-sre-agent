import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.fixed_subscription_links_item import FixedSubscriptionLinksItem


T = TypeVar("T", bound="FixedSubscription")


@_attrs_define
class FixedSubscription:
    """Redis Essentials Subscription information

    Example:
        {'id': 151367, 'name': 'fixed-sub-2', 'status': 'active', 'paymentMethodId': 8241, 'paymentMethodType': 'credit-
            card', 'planId': 98276, 'planName': 'Standard 1GB', 'size': 1, 'sizeMeasurementUnit': 'GB', 'provider': 'AWS',
            'region': 'us-west-1', 'price': 22, 'pricePeriod': 'Month', 'priceCurrency': 'USD', 'maximumDatabases': 1,
            'availability': 'Single-zone', 'connections': '1024', 'cidrAllowRules': 8, 'supportDataPersistence': True,
            'supportInstantAndDailyBackups': True, 'supportReplication': True, 'customerSupport': 'Standard',
            'creationDate': '2022-11-21T20:02:21+02:00', 'supportClustering': False, 'links': [{'rel': 'self', 'href':
            'http://localhost:8081/v1/fixed/subscriptions/151367', 'type': 'GET'}]}

    Attributes:
        id (Union[Unset, int]):
        name (Union[Unset, str]):
        status (Union[Unset, str]):
        payment_method_id (Union[Unset, int]):
        payment_method_type (Union[Unset, str]):
        plan_id (Union[Unset, int]):
        plan_name (Union[Unset, str]):
        plan_type (Union[Unset, str]):
        size (Union[Unset, float]):
        size_measurement_unit (Union[Unset, str]):
        provider (Union[Unset, str]):
        region (Union[Unset, str]):
        price (Union[Unset, int]):
        price_period (Union[Unset, str]):
        price_currency (Union[Unset, str]):
        maximum_databases (Union[Unset, int]):
        availability (Union[Unset, str]):
        connections (Union[Unset, str]):
        cidr_allow_rules (Union[Unset, int]):
        support_data_persistence (Union[Unset, bool]):
        support_instant_and_daily_backups (Union[Unset, bool]):
        support_replication (Union[Unset, bool]):
        support_clustering (Union[Unset, bool]):
        customer_support (Union[Unset, str]):
        creation_date (Union[Unset, datetime.datetime]):
        links (Union[Unset, list['FixedSubscriptionLinksItem']]):
        database_status (Union[Unset, str]):
    """

    id: Union[Unset, int] = UNSET
    name: Union[Unset, str] = UNSET
    status: Union[Unset, str] = UNSET
    payment_method_id: Union[Unset, int] = UNSET
    payment_method_type: Union[Unset, str] = UNSET
    plan_id: Union[Unset, int] = UNSET
    plan_name: Union[Unset, str] = UNSET
    plan_type: Union[Unset, str] = UNSET
    size: Union[Unset, float] = UNSET
    size_measurement_unit: Union[Unset, str] = UNSET
    provider: Union[Unset, str] = UNSET
    region: Union[Unset, str] = UNSET
    price: Union[Unset, int] = UNSET
    price_period: Union[Unset, str] = UNSET
    price_currency: Union[Unset, str] = UNSET
    maximum_databases: Union[Unset, int] = UNSET
    availability: Union[Unset, str] = UNSET
    connections: Union[Unset, str] = UNSET
    cidr_allow_rules: Union[Unset, int] = UNSET
    support_data_persistence: Union[Unset, bool] = UNSET
    support_instant_and_daily_backups: Union[Unset, bool] = UNSET
    support_replication: Union[Unset, bool] = UNSET
    support_clustering: Union[Unset, bool] = UNSET
    customer_support: Union[Unset, str] = UNSET
    creation_date: Union[Unset, datetime.datetime] = UNSET
    links: Union[Unset, list["FixedSubscriptionLinksItem"]] = UNSET
    database_status: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        status = self.status

        payment_method_id = self.payment_method_id

        payment_method_type = self.payment_method_type

        plan_id = self.plan_id

        plan_name = self.plan_name

        plan_type = self.plan_type

        size = self.size

        size_measurement_unit = self.size_measurement_unit

        provider = self.provider

        region = self.region

        price = self.price

        price_period = self.price_period

        price_currency = self.price_currency

        maximum_databases = self.maximum_databases

        availability = self.availability

        connections = self.connections

        cidr_allow_rules = self.cidr_allow_rules

        support_data_persistence = self.support_data_persistence

        support_instant_and_daily_backups = self.support_instant_and_daily_backups

        support_replication = self.support_replication

        support_clustering = self.support_clustering

        customer_support = self.customer_support

        creation_date: Union[Unset, str] = UNSET
        if not isinstance(self.creation_date, Unset):
            creation_date = self.creation_date.isoformat()

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        database_status = self.database_status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if name is not UNSET:
            field_dict["name"] = name
        if status is not UNSET:
            field_dict["status"] = status
        if payment_method_id is not UNSET:
            field_dict["paymentMethodId"] = payment_method_id
        if payment_method_type is not UNSET:
            field_dict["paymentMethodType"] = payment_method_type
        if plan_id is not UNSET:
            field_dict["planId"] = plan_id
        if plan_name is not UNSET:
            field_dict["planName"] = plan_name
        if plan_type is not UNSET:
            field_dict["planType"] = plan_type
        if size is not UNSET:
            field_dict["size"] = size
        if size_measurement_unit is not UNSET:
            field_dict["sizeMeasurementUnit"] = size_measurement_unit
        if provider is not UNSET:
            field_dict["provider"] = provider
        if region is not UNSET:
            field_dict["region"] = region
        if price is not UNSET:
            field_dict["price"] = price
        if price_period is not UNSET:
            field_dict["pricePeriod"] = price_period
        if price_currency is not UNSET:
            field_dict["priceCurrency"] = price_currency
        if maximum_databases is not UNSET:
            field_dict["maximumDatabases"] = maximum_databases
        if availability is not UNSET:
            field_dict["availability"] = availability
        if connections is not UNSET:
            field_dict["connections"] = connections
        if cidr_allow_rules is not UNSET:
            field_dict["cidrAllowRules"] = cidr_allow_rules
        if support_data_persistence is not UNSET:
            field_dict["supportDataPersistence"] = support_data_persistence
        if support_instant_and_daily_backups is not UNSET:
            field_dict["supportInstantAndDailyBackups"] = support_instant_and_daily_backups
        if support_replication is not UNSET:
            field_dict["supportReplication"] = support_replication
        if support_clustering is not UNSET:
            field_dict["supportClustering"] = support_clustering
        if customer_support is not UNSET:
            field_dict["customerSupport"] = customer_support
        if creation_date is not UNSET:
            field_dict["creationDate"] = creation_date
        if links is not UNSET:
            field_dict["links"] = links
        if database_status is not UNSET:
            field_dict["databaseStatus"] = database_status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.fixed_subscription_links_item import FixedSubscriptionLinksItem

        d = dict(src_dict)
        id = d.pop("id", UNSET)

        name = d.pop("name", UNSET)

        status = d.pop("status", UNSET)

        payment_method_id = d.pop("paymentMethodId", UNSET)

        payment_method_type = d.pop("paymentMethodType", UNSET)

        plan_id = d.pop("planId", UNSET)

        plan_name = d.pop("planName", UNSET)

        plan_type = d.pop("planType", UNSET)

        size = d.pop("size", UNSET)

        size_measurement_unit = d.pop("sizeMeasurementUnit", UNSET)

        provider = d.pop("provider", UNSET)

        region = d.pop("region", UNSET)

        price = d.pop("price", UNSET)

        price_period = d.pop("pricePeriod", UNSET)

        price_currency = d.pop("priceCurrency", UNSET)

        maximum_databases = d.pop("maximumDatabases", UNSET)

        availability = d.pop("availability", UNSET)

        connections = d.pop("connections", UNSET)

        cidr_allow_rules = d.pop("cidrAllowRules", UNSET)

        support_data_persistence = d.pop("supportDataPersistence", UNSET)

        support_instant_and_daily_backups = d.pop("supportInstantAndDailyBackups", UNSET)

        support_replication = d.pop("supportReplication", UNSET)

        support_clustering = d.pop("supportClustering", UNSET)

        customer_support = d.pop("customerSupport", UNSET)

        _creation_date = d.pop("creationDate", UNSET)
        creation_date: Union[Unset, datetime.datetime]
        if isinstance(_creation_date, Unset):
            creation_date = UNSET
        else:
            creation_date = isoparse(_creation_date)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = FixedSubscriptionLinksItem.from_dict(links_item_data)

            links.append(links_item)

        database_status = d.pop("databaseStatus", UNSET)

        fixed_subscription = cls(
            id=id,
            name=name,
            status=status,
            payment_method_id=payment_method_id,
            payment_method_type=payment_method_type,
            plan_id=plan_id,
            plan_name=plan_name,
            plan_type=plan_type,
            size=size,
            size_measurement_unit=size_measurement_unit,
            provider=provider,
            region=region,
            price=price,
            price_period=price_period,
            price_currency=price_currency,
            maximum_databases=maximum_databases,
            availability=availability,
            connections=connections,
            cidr_allow_rules=cidr_allow_rules,
            support_data_persistence=support_data_persistence,
            support_instant_and_daily_backups=support_instant_and_daily_backups,
            support_replication=support_replication,
            support_clustering=support_clustering,
            customer_support=customer_support,
            creation_date=creation_date,
            links=links,
            database_status=database_status,
        )

        fixed_subscription.additional_properties = d
        return fixed_subscription

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

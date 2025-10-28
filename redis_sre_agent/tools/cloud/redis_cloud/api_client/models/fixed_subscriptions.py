from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.fixed_subscriptions_links_item import FixedSubscriptionsLinksItem


T = TypeVar("T", bound="FixedSubscriptions")


@_attrs_define
class FixedSubscriptions:
    """Redis list of Essentials subscriptions in current account

    Example:
        {'accountId': 40131, 'subscriptions': [{'id': 151367, 'name': 'fixed-1', 'status': 'active', 'paymentMethodId':
            8241, 'paymentMethodType': 'credit-card', 'planId': 98276, 'planName': 'Standard 1GB', 'size': 1,
            'sizeMeasurementUnit': 'GB', 'provider': 'AWS', 'region': 'us-west-1', 'price': 22, 'pricePeriod': 'Month',
            'priceCurrency': 'USD', 'maximumDatabases': 1, 'availability': 'Single-zone', 'connections': '1024',
            'cidrAllowRules': 8, 'supportDataPersistence': True, 'supportInstantAndDailyBackups': True,
            'supportReplication': True, 'supportClustering': False, 'customerSupport': 'Standard', 'creationDate':
            '2022-11-21T20:02:21+02:00', 'links': []}, {'id': 120416, 'name': 'subscription-name', 'status': 'active',
            'paymentMethodId': 123, 'paymentMethodType': 'credit-card', 'planId': 123, 'planName': 'Standard 30MB',
            'planType': 'pay-as-you-go', 'size': 30, 'sizeMeasurementUnit': 'MB', 'provider': 'AWS', 'region': 'us-east-1',
            'price': 0, 'pricePeriod': 'Month', 'priceCurrency': 'USD', 'maximumDatabases': 1, 'availability': 'no-
            replication', 'connections': 30, 'cidrAllowRules': 1, 'supportDataPersistence': False,
            'supportInstantAndDailyBackups': False, 'supportReplication': False, 'supportClustering': False,
            'customerSupport': 'basic', 'creationDate': '20-Nov-2022', 'links': []}], 'links': [{'rel': 'self', 'href':
            'http://localhost:8081/v1/fixed/subscriptions', 'type': 'GET'}]}

    Attributes:
        account_id (Union[Unset, int]):
        links (Union[Unset, list['FixedSubscriptionsLinksItem']]):
    """

    account_id: Union[Unset, int] = UNSET
    links: Union[Unset, list["FixedSubscriptionsLinksItem"]] = UNSET
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
        from ..models.fixed_subscriptions_links_item import FixedSubscriptionsLinksItem

        d = dict(src_dict)
        account_id = d.pop("accountId", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = FixedSubscriptionsLinksItem.from_dict(links_item_data)

            links.append(links_item)

        fixed_subscriptions = cls(
            account_id=account_id,
            links=links,
        )

        fixed_subscriptions.additional_properties = d
        return fixed_subscriptions

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

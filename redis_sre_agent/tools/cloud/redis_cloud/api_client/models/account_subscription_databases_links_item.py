from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.account_subscription_databases_links_item_additional_property import (
        AccountSubscriptionDatabasesLinksItemAdditionalProperty,
    )


T = TypeVar("T", bound="AccountSubscriptionDatabasesLinksItem")


@_attrs_define
class AccountSubscriptionDatabasesLinksItem:
    """ """

    additional_properties: dict[str, "AccountSubscriptionDatabasesLinksItemAdditionalProperty"] = _attrs_field(
        init=False, factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.to_dict()

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.account_subscription_databases_links_item_additional_property import (
            AccountSubscriptionDatabasesLinksItemAdditionalProperty,
        )

        d = dict(src_dict)
        account_subscription_databases_links_item = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = AccountSubscriptionDatabasesLinksItemAdditionalProperty.from_dict(prop_dict)

            additional_properties[prop_name] = additional_property

        account_subscription_databases_links_item.additional_properties = additional_properties
        return account_subscription_databases_links_item

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> "AccountSubscriptionDatabasesLinksItemAdditionalProperty":
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: "AccountSubscriptionDatabasesLinksItemAdditionalProperty") -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.subscription_pricing import SubscriptionPricing


T = TypeVar("T", bound="SubscriptionPricings")


@_attrs_define
class SubscriptionPricings:
    """
    Attributes:
        pricing (Union[Unset, list['SubscriptionPricing']]):
    """

    pricing: Union[Unset, list["SubscriptionPricing"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        pricing: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.pricing, Unset):
            pricing = []
            for pricing_item_data in self.pricing:
                pricing_item = pricing_item_data.to_dict()
                pricing.append(pricing_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if pricing is not UNSET:
            field_dict["pricing"] = pricing

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.subscription_pricing import SubscriptionPricing

        d = dict(src_dict)
        pricing = []
        _pricing = d.pop("pricing", UNSET)
        for pricing_item_data in _pricing or []:
            pricing_item = SubscriptionPricing.from_dict(pricing_item_data)

            pricing.append(pricing_item)

        subscription_pricings = cls(
            pricing=pricing,
        )

        subscription_pricings.additional_properties = d
        return subscription_pricings

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

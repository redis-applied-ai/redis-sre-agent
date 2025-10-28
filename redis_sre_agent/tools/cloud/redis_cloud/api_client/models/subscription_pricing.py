from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SubscriptionPricing")


@_attrs_define
class SubscriptionPricing:
    """
    Attributes:
        type_ (Union[Unset, str]):
        type_details (Union[Unset, str]):
        quantity (Union[Unset, int]):
        quantity_measurement (Union[Unset, str]):
        price_per_unit (Union[Unset, float]):
        price_currency (Union[Unset, str]):
        price_period (Union[Unset, str]):
        region (Union[Unset, str]):
    """

    type_: Union[Unset, str] = UNSET
    type_details: Union[Unset, str] = UNSET
    quantity: Union[Unset, int] = UNSET
    quantity_measurement: Union[Unset, str] = UNSET
    price_per_unit: Union[Unset, float] = UNSET
    price_currency: Union[Unset, str] = UNSET
    price_period: Union[Unset, str] = UNSET
    region: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        type_details = self.type_details

        quantity = self.quantity

        quantity_measurement = self.quantity_measurement

        price_per_unit = self.price_per_unit

        price_currency = self.price_currency

        price_period = self.price_period

        region = self.region

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if type_ is not UNSET:
            field_dict["type"] = type_
        if type_details is not UNSET:
            field_dict["typeDetails"] = type_details
        if quantity is not UNSET:
            field_dict["quantity"] = quantity
        if quantity_measurement is not UNSET:
            field_dict["quantityMeasurement"] = quantity_measurement
        if price_per_unit is not UNSET:
            field_dict["pricePerUnit"] = price_per_unit
        if price_currency is not UNSET:
            field_dict["priceCurrency"] = price_currency
        if price_period is not UNSET:
            field_dict["pricePeriod"] = price_period
        if region is not UNSET:
            field_dict["region"] = region

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        type_ = d.pop("type", UNSET)

        type_details = d.pop("typeDetails", UNSET)

        quantity = d.pop("quantity", UNSET)

        quantity_measurement = d.pop("quantityMeasurement", UNSET)

        price_per_unit = d.pop("pricePerUnit", UNSET)

        price_currency = d.pop("priceCurrency", UNSET)

        price_period = d.pop("pricePeriod", UNSET)

        region = d.pop("region", UNSET)

        subscription_pricing = cls(
            type_=type_,
            type_details=type_details,
            quantity=quantity,
            quantity_measurement=quantity_measurement,
            price_per_unit=price_per_unit,
            price_currency=price_currency,
            price_period=price_period,
            region=region,
        )

        subscription_pricing.additional_properties = d
        return subscription_pricing

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

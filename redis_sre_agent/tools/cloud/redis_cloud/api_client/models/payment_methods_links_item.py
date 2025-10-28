from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.payment_methods_links_item_additional_property import PaymentMethodsLinksItemAdditionalProperty


T = TypeVar("T", bound="PaymentMethodsLinksItem")


@_attrs_define
class PaymentMethodsLinksItem:
    """ """

    additional_properties: dict[str, "PaymentMethodsLinksItemAdditionalProperty"] = _attrs_field(
        init=False, factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.to_dict()

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.payment_methods_links_item_additional_property import PaymentMethodsLinksItemAdditionalProperty

        d = dict(src_dict)
        payment_methods_links_item = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = PaymentMethodsLinksItemAdditionalProperty.from_dict(prop_dict)

            additional_properties[prop_name] = additional_property

        payment_methods_links_item.additional_properties = additional_properties
        return payment_methods_links_item

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> "PaymentMethodsLinksItemAdditionalProperty":
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: "PaymentMethodsLinksItemAdditionalProperty") -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.payment_methods_links_item import PaymentMethodsLinksItem


T = TypeVar("T", bound="PaymentMethods")


@_attrs_define
class PaymentMethods:
    """RedisLabs Account payment methods

    Example:
        {'accountId': 1001, 'paymentMethods': [{'id': 2, 'type': 'Visa', 'creditCardEndsWith': '9349', 'nameOnCard':
            'CAPI User', 'expirationMonth': 2, 'expirationYear': 2026, 'links': []}]}

    Attributes:
        account_id (Union[Unset, int]):
        links (Union[Unset, list['PaymentMethodsLinksItem']]):
    """

    account_id: Union[Unset, int] = UNSET
    links: Union[Unset, list["PaymentMethodsLinksItem"]] = UNSET
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
        from ..models.payment_methods_links_item import PaymentMethodsLinksItem

        d = dict(src_dict)
        account_id = d.pop("accountId", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = PaymentMethodsLinksItem.from_dict(links_item_data)

            links.append(links_item)

        payment_methods = cls(
            account_id=account_id,
            links=links,
        )

        payment_methods.additional_properties = d
        return payment_methods

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

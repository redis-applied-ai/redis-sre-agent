from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.subscription_update_request_payment_method import SubscriptionUpdateRequestPaymentMethod
from ..types import UNSET, Unset

T = TypeVar("T", bound="SubscriptionUpdateRequest")


@_attrs_define
class SubscriptionUpdateRequest:
    """Subscription update request message

    Attributes:
        subscription_id (Union[Unset, int]):
        name (Union[Unset, str]): Optional. Updated subscription name. Example: My new subscription name.
        payment_method_id (Union[Unset, int]): Optional. The payment method ID you'd like to use for this subscription.
            Must be a valid payment method ID for this account. Use GET /payment-methods to get all payment methods for your
            account. This value is optional if ‘paymentMethod’ is ‘marketplace’, but required if 'paymentMethod' is 'credit-
            card'.
        payment_method (Union[Unset, SubscriptionUpdateRequestPaymentMethod]): Optional. The payment method for the
            subscription. If set to ‘credit-card’ , ‘paymentMethodId’ must be defined.
        command_type (Union[Unset, str]):
    """

    subscription_id: Union[Unset, int] = UNSET
    name: Union[Unset, str] = UNSET
    payment_method_id: Union[Unset, int] = UNSET
    payment_method: Union[Unset, SubscriptionUpdateRequestPaymentMethod] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        name = self.name

        payment_method_id = self.payment_method_id

        payment_method: Union[Unset, str] = UNSET
        if not isinstance(self.payment_method, Unset):
            payment_method = self.payment_method.value

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if name is not UNSET:
            field_dict["name"] = name
        if payment_method_id is not UNSET:
            field_dict["paymentMethodId"] = payment_method_id
        if payment_method is not UNSET:
            field_dict["paymentMethod"] = payment_method
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId", UNSET)

        name = d.pop("name", UNSET)

        payment_method_id = d.pop("paymentMethodId", UNSET)

        _payment_method = d.pop("paymentMethod", UNSET)
        payment_method: Union[Unset, SubscriptionUpdateRequestPaymentMethod]
        if isinstance(_payment_method, Unset):
            payment_method = UNSET
        else:
            payment_method = SubscriptionUpdateRequestPaymentMethod(_payment_method)

        command_type = d.pop("commandType", UNSET)

        subscription_update_request = cls(
            subscription_id=subscription_id,
            name=name,
            payment_method_id=payment_method_id,
            payment_method=payment_method,
            command_type=command_type,
        )

        subscription_update_request.additional_properties = d
        return subscription_update_request

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

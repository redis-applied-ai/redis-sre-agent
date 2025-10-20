from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.fixed_subscription_update_request_payment_method import FixedSubscriptionUpdateRequestPaymentMethod
from ..types import UNSET, Unset

T = TypeVar("T", bound="FixedSubscriptionUpdateRequest")


@_attrs_define
class FixedSubscriptionUpdateRequest:
    """Essentials subscription update request

    Attributes:
        subscription_id (Union[Unset, int]):
        name (Union[Unset, str]): Optional. Updated subscription name. Example: My new subscription.
        plan_id (Union[Unset, int]): Optional. An Essentials plan ID. The plan describes the dataset size, cloud
            provider and region, and available database configuration options. Use GET
            /fixed/plans/subscriptions/{subscriptionId} to get a list of compatible options for the specified subscription.
        payment_method (Union[Unset, FixedSubscriptionUpdateRequestPaymentMethod]): Optional. The payment method for the
            subscription. If set to ‘credit-card’ , ‘paymentMethodId’ must be defined.
        payment_method_id (Union[Unset, int]): Optional. The payment method ID you'd like to use for this subscription.
            Must be a valid payment method ID for this account. Use GET /payment-methods to get a list of payment methods
            for your account. This value is optional if ‘paymentMethod’ is ‘marketplace’, but required if 'paymentMethod' is
            'credit-card'.
        command_type (Union[Unset, str]):
    """

    subscription_id: Union[Unset, int] = UNSET
    name: Union[Unset, str] = UNSET
    plan_id: Union[Unset, int] = UNSET
    payment_method: Union[Unset, FixedSubscriptionUpdateRequestPaymentMethod] = UNSET
    payment_method_id: Union[Unset, int] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        name = self.name

        plan_id = self.plan_id

        payment_method: Union[Unset, str] = UNSET
        if not isinstance(self.payment_method, Unset):
            payment_method = self.payment_method.value

        payment_method_id = self.payment_method_id

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if name is not UNSET:
            field_dict["name"] = name
        if plan_id is not UNSET:
            field_dict["planId"] = plan_id
        if payment_method is not UNSET:
            field_dict["paymentMethod"] = payment_method
        if payment_method_id is not UNSET:
            field_dict["paymentMethodId"] = payment_method_id
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId", UNSET)

        name = d.pop("name", UNSET)

        plan_id = d.pop("planId", UNSET)

        _payment_method = d.pop("paymentMethod", UNSET)
        payment_method: Union[Unset, FixedSubscriptionUpdateRequestPaymentMethod]
        if isinstance(_payment_method, Unset):
            payment_method = UNSET
        else:
            payment_method = FixedSubscriptionUpdateRequestPaymentMethod(_payment_method)

        payment_method_id = d.pop("paymentMethodId", UNSET)

        command_type = d.pop("commandType", UNSET)

        fixed_subscription_update_request = cls(
            subscription_id=subscription_id,
            name=name,
            plan_id=plan_id,
            payment_method=payment_method,
            payment_method_id=payment_method_id,
            command_type=command_type,
        )

        fixed_subscription_update_request.additional_properties = d
        return fixed_subscription_update_request

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

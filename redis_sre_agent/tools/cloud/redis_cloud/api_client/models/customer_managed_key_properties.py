from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.customer_managed_key_properties_deletion_grace_period import (
    CustomerManagedKeyPropertiesDeletionGracePeriod,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.customer_managed_key import CustomerManagedKey


T = TypeVar("T", bound="CustomerManagedKeyProperties")


@_attrs_define
class CustomerManagedKeyProperties:
    """Optional. Contains information about the keys used for each region. Can be used only with external cloud account

    Attributes:
        customer_managed_keys (list['CustomerManagedKey']): The customer managed keys (CMK) to use for this
            subscription. If is active-active subscription, must set a key for each region.
        deletion_grace_period (Union[Unset, CustomerManagedKeyPropertiesDeletionGracePeriod]): Optional. The grace
            period for deleting the subscription. If not set, will default to immediate deletion grace period. Example:
            alerts-only.
    """

    customer_managed_keys: list["CustomerManagedKey"]
    deletion_grace_period: Union[Unset, CustomerManagedKeyPropertiesDeletionGracePeriod] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        customer_managed_keys = []
        for customer_managed_keys_item_data in self.customer_managed_keys:
            customer_managed_keys_item = customer_managed_keys_item_data.to_dict()
            customer_managed_keys.append(customer_managed_keys_item)

        deletion_grace_period: Union[Unset, str] = UNSET
        if not isinstance(self.deletion_grace_period, Unset):
            deletion_grace_period = self.deletion_grace_period.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "customerManagedKeys": customer_managed_keys,
            }
        )
        if deletion_grace_period is not UNSET:
            field_dict["deletionGracePeriod"] = deletion_grace_period

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.customer_managed_key import CustomerManagedKey

        d = dict(src_dict)
        customer_managed_keys = []
        _customer_managed_keys = d.pop("customerManagedKeys")
        for customer_managed_keys_item_data in _customer_managed_keys:
            customer_managed_keys_item = CustomerManagedKey.from_dict(customer_managed_keys_item_data)

            customer_managed_keys.append(customer_managed_keys_item)

        _deletion_grace_period = d.pop("deletionGracePeriod", UNSET)
        deletion_grace_period: Union[Unset, CustomerManagedKeyPropertiesDeletionGracePeriod]
        if isinstance(_deletion_grace_period, Unset):
            deletion_grace_period = UNSET
        else:
            deletion_grace_period = CustomerManagedKeyPropertiesDeletionGracePeriod(_deletion_grace_period)

        customer_managed_key_properties = cls(
            customer_managed_keys=customer_managed_keys,
            deletion_grace_period=deletion_grace_period,
        )

        customer_managed_key_properties.additional_properties = d
        return customer_managed_key_properties

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

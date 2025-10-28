from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CustomerManagedKey")


@_attrs_define
class CustomerManagedKey:
    """Object representing a customer managed key (CMK), along with the region it is associated to.

    Attributes:
        resource_name (str): Required. Resource name of the customer managed key as defined by the cloud provider.
            Example: projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME.
        region (Union[Unset, str]): Name of region to for the customer managed key as defined by the cloud provider.
            Required for active-active subscriptions.
    """

    resource_name: str
    region: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        resource_name = self.resource_name

        region = self.region

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "resourceName": resource_name,
            }
        )
        if region is not UNSET:
            field_dict["region"] = region

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        resource_name = d.pop("resourceName")

        region = d.pop("region", UNSET)

        customer_managed_key = cls(
            resource_name=resource_name,
            region=region,
        )

        customer_managed_key.additional_properties = d
        return customer_managed_key

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

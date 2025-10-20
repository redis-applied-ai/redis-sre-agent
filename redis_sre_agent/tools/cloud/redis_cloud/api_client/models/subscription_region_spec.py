from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.subscription_region_networking_spec import SubscriptionRegionNetworkingSpec


T = TypeVar("T", bound="SubscriptionRegionSpec")


@_attrs_define
class SubscriptionRegionSpec:
    """The cloud provider region or list of regions (Active-Active only) and networking details.

    Attributes:
        region (str): Deployment region as defined by the cloud provider. Example: us-east-1.
        multiple_availability_zones (Union[Unset, bool]): Optional. Support deployment on multiple availability zones
            within the selected region. Default: 'false'
        preferred_availability_zones (Union[Unset, list[str]]): Optional. List the zone ID(s) for your preferred
            availability zone(s) for the cloud provider and region. If ‘multipleAvailabilityZones’ is set to 'true', you
            must list three availability zones. Otherwise, list one availability zone.
        networking (Union[Unset, SubscriptionRegionNetworkingSpec]): Optional. Cloud networking details, per region.
            Required if creating an Active-Active subscription.
    """

    region: str
    multiple_availability_zones: Union[Unset, bool] = UNSET
    preferred_availability_zones: Union[Unset, list[str]] = UNSET
    networking: Union[Unset, "SubscriptionRegionNetworkingSpec"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        region = self.region

        multiple_availability_zones = self.multiple_availability_zones

        preferred_availability_zones: Union[Unset, list[str]] = UNSET
        if not isinstance(self.preferred_availability_zones, Unset):
            preferred_availability_zones = self.preferred_availability_zones

        networking: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.networking, Unset):
            networking = self.networking.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "region": region,
            }
        )
        if multiple_availability_zones is not UNSET:
            field_dict["multipleAvailabilityZones"] = multiple_availability_zones
        if preferred_availability_zones is not UNSET:
            field_dict["preferredAvailabilityZones"] = preferred_availability_zones
        if networking is not UNSET:
            field_dict["networking"] = networking

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.subscription_region_networking_spec import SubscriptionRegionNetworkingSpec

        d = dict(src_dict)
        region = d.pop("region")

        multiple_availability_zones = d.pop("multipleAvailabilityZones", UNSET)

        preferred_availability_zones = cast(list[str], d.pop("preferredAvailabilityZones", UNSET))

        _networking = d.pop("networking", UNSET)
        networking: Union[Unset, SubscriptionRegionNetworkingSpec]
        if isinstance(_networking, Unset):
            networking = UNSET
        else:
            networking = SubscriptionRegionNetworkingSpec.from_dict(_networking)

        subscription_region_spec = cls(
            region=region,
            multiple_availability_zones=multiple_availability_zones,
            preferred_availability_zones=preferred_availability_zones,
            networking=networking,
        )

        subscription_region_spec.additional_properties = d
        return subscription_region_spec

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

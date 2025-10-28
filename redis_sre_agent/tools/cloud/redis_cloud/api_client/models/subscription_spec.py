from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.subscription_spec_provider import SubscriptionSpecProvider
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.subscription_region_spec import SubscriptionRegionSpec


T = TypeVar("T", bound="SubscriptionSpec")


@_attrs_define
class SubscriptionSpec:
    """Cloud provider, region, and networking details.

    Attributes:
        regions (list['SubscriptionRegionSpec']): The cloud provider region or list of regions (Active-Active only) and
            networking details.
        provider (Union[Unset, SubscriptionSpecProvider]): Optional. Cloud provider. Default: 'AWS' Example: AWS.
        cloud_account_id (Union[Unset, int]): Optional. Cloud account identifier. Default: Redis internal cloud account
            (Cloud Account ID = 1). Use GET /cloud-accounts to list all available cloud accounts. Note: A subscription on
            Google Cloud can be created only with Redis internal cloud account. Example: 1.
    """

    regions: list["SubscriptionRegionSpec"]
    provider: Union[Unset, SubscriptionSpecProvider] = UNSET
    cloud_account_id: Union[Unset, int] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        regions = []
        for regions_item_data in self.regions:
            regions_item = regions_item_data.to_dict()
            regions.append(regions_item)

        provider: Union[Unset, str] = UNSET
        if not isinstance(self.provider, Unset):
            provider = self.provider.value

        cloud_account_id = self.cloud_account_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "regions": regions,
            }
        )
        if provider is not UNSET:
            field_dict["provider"] = provider
        if cloud_account_id is not UNSET:
            field_dict["cloudAccountId"] = cloud_account_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.subscription_region_spec import SubscriptionRegionSpec

        d = dict(src_dict)
        regions = []
        _regions = d.pop("regions")
        for regions_item_data in _regions:
            regions_item = SubscriptionRegionSpec.from_dict(regions_item_data)

            regions.append(regions_item)

        _provider = d.pop("provider", UNSET)
        provider: Union[Unset, SubscriptionSpecProvider]
        if isinstance(_provider, Unset):
            provider = UNSET
        else:
            provider = SubscriptionSpecProvider(_provider)

        cloud_account_id = d.pop("cloudAccountId", UNSET)

        subscription_spec = cls(
            regions=regions,
            provider=provider,
            cloud_account_id=cloud_account_id,
        )

        subscription_spec.additional_properties = d
        return subscription_spec

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

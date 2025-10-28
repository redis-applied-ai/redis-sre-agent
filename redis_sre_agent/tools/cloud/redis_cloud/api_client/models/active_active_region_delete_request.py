from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.active_active_region_to_delete import ActiveActiveRegionToDelete


T = TypeVar("T", bound="ActiveActiveRegionDeleteRequest")


@_attrs_define
class ActiveActiveRegionDeleteRequest:
    """Active active region deletion request message

    Attributes:
        subscription_id (Union[Unset, int]):
        regions (Union[Unset, list['ActiveActiveRegionToDelete']]): The names of the regions to delete.
        dry_run (Union[Unset, bool]): Optional. When 'false': Creates a deployment plan and deploys it, deleting any
            resources required by the plan. When 'true': creates a read-only deployment plan and does not delete or modify
            any resources. Default: 'false'
        command_type (Union[Unset, str]):
    """

    subscription_id: Union[Unset, int] = UNSET
    regions: Union[Unset, list["ActiveActiveRegionToDelete"]] = UNSET
    dry_run: Union[Unset, bool] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        regions: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.regions, Unset):
            regions = []
            for regions_item_data in self.regions:
                regions_item = regions_item_data.to_dict()
                regions.append(regions_item)

        dry_run = self.dry_run

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if regions is not UNSET:
            field_dict["regions"] = regions
        if dry_run is not UNSET:
            field_dict["dryRun"] = dry_run
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.active_active_region_to_delete import ActiveActiveRegionToDelete

        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId", UNSET)

        regions = []
        _regions = d.pop("regions", UNSET)
        for regions_item_data in _regions or []:
            regions_item = ActiveActiveRegionToDelete.from_dict(regions_item_data)

            regions.append(regions_item)

        dry_run = d.pop("dryRun", UNSET)

        command_type = d.pop("commandType", UNSET)

        active_active_region_delete_request = cls(
            subscription_id=subscription_id,
            regions=regions,
            dry_run=dry_run,
            command_type=command_type,
        )

        active_active_region_delete_request.additional_properties = d
        return active_active_region_delete_request

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

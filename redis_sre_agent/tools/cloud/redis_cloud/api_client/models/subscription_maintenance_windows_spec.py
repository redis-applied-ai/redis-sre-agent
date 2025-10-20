from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.subscription_maintenance_windows_spec_mode import SubscriptionMaintenanceWindowsSpecMode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.maintenance_window_spec import MaintenanceWindowSpec


T = TypeVar("T", bound="SubscriptionMaintenanceWindowsSpec")


@_attrs_define
class SubscriptionMaintenanceWindowsSpec:
    """
    Attributes:
        mode (SubscriptionMaintenanceWindowsSpecMode): Maintenance window mode: either 'manual' or 'automatic'. Must
            provide 'windows' if manual. Example: manual.
        windows (Union[Unset, list['MaintenanceWindowSpec']]): Maintenance window timeframes if mode is set to 'manual'.
            Up to 7 maintenance windows can be provided.
    """

    mode: SubscriptionMaintenanceWindowsSpecMode
    windows: Union[Unset, list["MaintenanceWindowSpec"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mode = self.mode.value

        windows: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.windows, Unset):
            windows = []
            for windows_item_data in self.windows:
                windows_item = windows_item_data.to_dict()
                windows.append(windows_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "mode": mode,
            }
        )
        if windows is not UNSET:
            field_dict["windows"] = windows

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.maintenance_window_spec import MaintenanceWindowSpec

        d = dict(src_dict)
        mode = SubscriptionMaintenanceWindowsSpecMode(d.pop("mode"))

        windows = []
        _windows = d.pop("windows", UNSET)
        for windows_item_data in _windows or []:
            windows_item = MaintenanceWindowSpec.from_dict(windows_item_data)

            windows.append(windows_item)

        subscription_maintenance_windows_spec = cls(
            mode=mode,
            windows=windows,
        )

        subscription_maintenance_windows_spec.additional_properties = d
        return subscription_maintenance_windows_spec

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

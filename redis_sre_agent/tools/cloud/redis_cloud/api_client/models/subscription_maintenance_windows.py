from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.subscription_maintenance_windows_mode import SubscriptionMaintenanceWindowsMode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.maintenance_window import MaintenanceWindow
    from ..models.maintenance_window_skip_status import MaintenanceWindowSkipStatus


T = TypeVar("T", bound="SubscriptionMaintenanceWindows")


@_attrs_define
class SubscriptionMaintenanceWindows:
    """
    Attributes:
        mode (Union[Unset, SubscriptionMaintenanceWindowsMode]):
        time_zone (Union[Unset, str]):
        windows (Union[Unset, list['MaintenanceWindow']]):
        skip_status (Union[Unset, MaintenanceWindowSkipStatus]):
    """

    mode: Union[Unset, SubscriptionMaintenanceWindowsMode] = UNSET
    time_zone: Union[Unset, str] = UNSET
    windows: Union[Unset, list["MaintenanceWindow"]] = UNSET
    skip_status: Union[Unset, "MaintenanceWindowSkipStatus"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mode: Union[Unset, str] = UNSET
        if not isinstance(self.mode, Unset):
            mode = self.mode.value

        time_zone = self.time_zone

        windows: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.windows, Unset):
            windows = []
            for windows_item_data in self.windows:
                windows_item = windows_item_data.to_dict()
                windows.append(windows_item)

        skip_status: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.skip_status, Unset):
            skip_status = self.skip_status.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if mode is not UNSET:
            field_dict["mode"] = mode
        if time_zone is not UNSET:
            field_dict["timeZone"] = time_zone
        if windows is not UNSET:
            field_dict["windows"] = windows
        if skip_status is not UNSET:
            field_dict["skipStatus"] = skip_status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.maintenance_window import MaintenanceWindow
        from ..models.maintenance_window_skip_status import MaintenanceWindowSkipStatus

        d = dict(src_dict)
        _mode = d.pop("mode", UNSET)
        mode: Union[Unset, SubscriptionMaintenanceWindowsMode]
        if isinstance(_mode, Unset):
            mode = UNSET
        else:
            mode = SubscriptionMaintenanceWindowsMode(_mode)

        time_zone = d.pop("timeZone", UNSET)

        windows = []
        _windows = d.pop("windows", UNSET)
        for windows_item_data in _windows or []:
            windows_item = MaintenanceWindow.from_dict(windows_item_data)

            windows.append(windows_item)

        _skip_status = d.pop("skipStatus", UNSET)
        skip_status: Union[Unset, MaintenanceWindowSkipStatus]
        if isinstance(_skip_status, Unset):
            skip_status = UNSET
        else:
            skip_status = MaintenanceWindowSkipStatus.from_dict(_skip_status)

        subscription_maintenance_windows = cls(
            mode=mode,
            time_zone=time_zone,
            windows=windows,
            skip_status=skip_status,
        )

        subscription_maintenance_windows.additional_properties = d
        return subscription_maintenance_windows

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

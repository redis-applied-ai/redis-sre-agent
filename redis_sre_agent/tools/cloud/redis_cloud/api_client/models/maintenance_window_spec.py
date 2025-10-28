from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="MaintenanceWindowSpec")


@_attrs_define
class MaintenanceWindowSpec:
    """Maintenance window timeframes if mode is set to 'manual'. Up to 7 maintenance windows can be provided.

    Attributes:
        start_hour (int): Starting hour of the maintenance window. Can be between '0' (12 AM in the deployment region's
            local time) and '23' (11 PM in the deployment region's local time). Example: 12.
        duration_in_hours (int): The duration of the maintenance window in hours. Can be between 4-24 hours (or 8-24
            hours if using 'ram-and-flash'). Example: 8.
        days (list[str]): Days where this maintenance window applies. Can contain one or more of: "Monday", "Tuesday",
            "Wednesday", "Thursday", "Friday", "Saturday", or "Sunday". Example: ['Monday', 'Wednesday'].
    """

    start_hour: int
    duration_in_hours: int
    days: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        start_hour = self.start_hour

        duration_in_hours = self.duration_in_hours

        days = self.days

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "startHour": start_hour,
                "durationInHours": duration_in_hours,
                "days": days,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        start_hour = d.pop("startHour")

        duration_in_hours = d.pop("durationInHours")

        days = cast(list[str], d.pop("days"))

        maintenance_window_spec = cls(
            start_hour=start_hour,
            duration_in_hours=duration_in_hours,
            days=days,
        )

        maintenance_window_spec.additional_properties = d
        return maintenance_window_spec

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

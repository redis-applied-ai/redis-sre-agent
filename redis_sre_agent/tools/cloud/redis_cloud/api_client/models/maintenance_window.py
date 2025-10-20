from collections.abc import Mapping
from typing import Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MaintenanceWindow")


@_attrs_define
class MaintenanceWindow:
    """
    Attributes:
        days (Union[Unset, list[str]]):
        start_hour (Union[Unset, int]):
        duration_in_hours (Union[Unset, int]):
    """

    days: Union[Unset, list[str]] = UNSET
    start_hour: Union[Unset, int] = UNSET
    duration_in_hours: Union[Unset, int] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        days: Union[Unset, list[str]] = UNSET
        if not isinstance(self.days, Unset):
            days = self.days

        start_hour = self.start_hour

        duration_in_hours = self.duration_in_hours

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if days is not UNSET:
            field_dict["days"] = days
        if start_hour is not UNSET:
            field_dict["startHour"] = start_hour
        if duration_in_hours is not UNSET:
            field_dict["durationInHours"] = duration_in_hours

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        days = cast(list[str], d.pop("days", UNSET))

        start_hour = d.pop("startHour", UNSET)

        duration_in_hours = d.pop("durationInHours", UNSET)

        maintenance_window = cls(
            days=days,
            start_hour=start_hour,
            duration_in_hours=duration_in_hours,
        )

        maintenance_window.additional_properties = d
        return maintenance_window

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

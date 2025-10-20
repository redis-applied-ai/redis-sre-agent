from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MaintenanceWindowSkipStatus")


@_attrs_define
class MaintenanceWindowSkipStatus:
    """
    Attributes:
        remaining_skips (Union[Unset, int]):
        current_skip_end (Union[Unset, str]):
    """

    remaining_skips: Union[Unset, int] = UNSET
    current_skip_end: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        remaining_skips = self.remaining_skips

        current_skip_end = self.current_skip_end

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if remaining_skips is not UNSET:
            field_dict["remainingSkips"] = remaining_skips
        if current_skip_end is not UNSET:
            field_dict["currentSkipEnd"] = current_skip_end

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        remaining_skips = d.pop("remainingSkips", UNSET)

        current_skip_end = d.pop("currentSkipEnd", UNSET)

        maintenance_window_skip_status = cls(
            remaining_skips=remaining_skips,
            current_skip_end=current_skip_end,
        )

        maintenance_window_skip_status.additional_properties = d
        return maintenance_window_skip_status

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

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="DatabaseSlowLogEntry")


@_attrs_define
class DatabaseSlowLogEntry:
    """Database slowlog entry

    Attributes:
        id (Union[Unset, int]):
        start_time (Union[Unset, datetime.datetime]):
        duration (Union[Unset, int]):
        arguments (Union[Unset, str]):
    """

    id: Union[Unset, int] = UNSET
    start_time: Union[Unset, datetime.datetime] = UNSET
    duration: Union[Unset, int] = UNSET
    arguments: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        start_time: Union[Unset, str] = UNSET
        if not isinstance(self.start_time, Unset):
            start_time = self.start_time.isoformat()

        duration = self.duration

        arguments = self.arguments

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if start_time is not UNSET:
            field_dict["startTime"] = start_time
        if duration is not UNSET:
            field_dict["duration"] = duration
        if arguments is not UNSET:
            field_dict["arguments"] = arguments

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id", UNSET)

        _start_time = d.pop("startTime", UNSET)
        start_time: Union[Unset, datetime.datetime]
        if isinstance(_start_time, Unset):
            start_time = UNSET
        else:
            start_time = isoparse(_start_time)

        duration = d.pop("duration", UNSET)

        arguments = d.pop("arguments", UNSET)

        database_slow_log_entry = cls(
            id=id,
            start_time=start_time,
            duration=duration,
            arguments=arguments,
        )

        database_slow_log_entry.additional_properties = d
        return database_slow_log_entry

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

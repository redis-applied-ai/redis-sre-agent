from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.database_throughput_spec_by import DatabaseThroughputSpecBy

T = TypeVar("T", bound="DatabaseThroughputSpec")


@_attrs_define
class DatabaseThroughputSpec:
    """Optional. Throughput measurement method.

    Attributes:
        by (DatabaseThroughputSpecBy): Throughput measurement method. Use 'operations-per-second' for all new databases.
        value (int): Throughput value in the selected measurement method. Example: 10000.
    """

    by: DatabaseThroughputSpecBy
    value: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        by = self.by.value

        value = self.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "by": by,
                "value": value,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        by = DatabaseThroughputSpecBy(d.pop("by"))

        value = d.pop("value")

        database_throughput_spec = cls(
            by=by,
            value=value,
        )

        database_throughput_spec.additional_properties = d
        return database_throughput_spec

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

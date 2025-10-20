from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.local_throughput import LocalThroughput


T = TypeVar("T", bound="CrdbRegionSpec")


@_attrs_define
class CrdbRegionSpec:
    """List of databases in the subscription with local throughput details. Default: 1000 read and write ops/sec for each
    database

        Attributes:
            name (Union[Unset, str]): Database name.
            local_throughput_measurement (Union[Unset, LocalThroughput]): Optional. Expected read and write throughput for
                this region.
    """

    name: Union[Unset, str] = UNSET
    local_throughput_measurement: Union[Unset, "LocalThroughput"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        local_throughput_measurement: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.local_throughput_measurement, Unset):
            local_throughput_measurement = self.local_throughput_measurement.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if local_throughput_measurement is not UNSET:
            field_dict["localThroughputMeasurement"] = local_throughput_measurement

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.local_throughput import LocalThroughput

        d = dict(src_dict)
        name = d.pop("name", UNSET)

        _local_throughput_measurement = d.pop("localThroughputMeasurement", UNSET)
        local_throughput_measurement: Union[Unset, LocalThroughput]
        if isinstance(_local_throughput_measurement, Unset):
            local_throughput_measurement = UNSET
        else:
            local_throughput_measurement = LocalThroughput.from_dict(_local_throughput_measurement)

        crdb_region_spec = cls(
            name=name,
            local_throughput_measurement=local_throughput_measurement,
        )

        crdb_region_spec.additional_properties = d
        return crdb_region_spec

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

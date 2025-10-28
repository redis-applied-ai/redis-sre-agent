from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="LocalThroughput")


@_attrs_define
class LocalThroughput:
    """Optional. Expected read and write throughput for this region.

    Attributes:
        region (Union[Unset, str]): Specify one of the selected cloud provider regions for the subscription.
        write_operations_per_second (Union[Unset, int]): Write operations for this region per second. Default: 1000
            ops/sec Example: 1000.
        read_operations_per_second (Union[Unset, int]): Read operations for this region per second. Default: 1000
            ops/sec Example: 1000.
    """

    region: Union[Unset, str] = UNSET
    write_operations_per_second: Union[Unset, int] = UNSET
    read_operations_per_second: Union[Unset, int] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        region = self.region

        write_operations_per_second = self.write_operations_per_second

        read_operations_per_second = self.read_operations_per_second

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if region is not UNSET:
            field_dict["region"] = region
        if write_operations_per_second is not UNSET:
            field_dict["writeOperationsPerSecond"] = write_operations_per_second
        if read_operations_per_second is not UNSET:
            field_dict["readOperationsPerSecond"] = read_operations_per_second

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        region = d.pop("region", UNSET)

        write_operations_per_second = d.pop("writeOperationsPerSecond", UNSET)

        read_operations_per_second = d.pop("readOperationsPerSecond", UNSET)

        local_throughput = cls(
            region=region,
            write_operations_per_second=write_operations_per_second,
            read_operations_per_second=read_operations_per_second,
        )

        local_throughput.additional_properties = d
        return local_throughput

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

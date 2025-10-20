from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="Cidr")


@_attrs_define
class Cidr:
    """Optional. List of transit gateway attachment CIDRs.

    Example:
        ['10.10.10.0/24', '10.10.20.0/24']

    Attributes:
        cidr_address (Union[Unset, str]):
    """

    cidr_address: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cidr_address = self.cidr_address

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if cidr_address is not UNSET:
            field_dict["cidrAddress"] = cidr_address

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cidr_address = d.pop("cidrAddress", UNSET)

        cidr = cls(
            cidr_address=cidr_address,
        )

        cidr.additional_properties = d
        return cidr

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

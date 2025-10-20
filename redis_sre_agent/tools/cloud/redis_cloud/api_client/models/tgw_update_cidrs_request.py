from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.cidr import Cidr


T = TypeVar("T", bound="TgwUpdateCidrsRequest")


@_attrs_define
class TgwUpdateCidrsRequest:
    """Transit Gateway update attachment cidr/s request message

    Attributes:
        cidrs (Union[Unset, list['Cidr']]): Optional. List of transit gateway attachment CIDRs. Example:
            ['10.10.10.0/24', '10.10.20.0/24'].
        command_type (Union[Unset, str]):
    """

    cidrs: Union[Unset, list["Cidr"]] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cidrs: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.cidrs, Unset):
            cidrs = []
            for cidrs_item_data in self.cidrs:
                cidrs_item = cidrs_item_data.to_dict()
                cidrs.append(cidrs_item)

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if cidrs is not UNSET:
            field_dict["cidrs"] = cidrs
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cidr import Cidr

        d = dict(src_dict)
        cidrs = []
        _cidrs = d.pop("cidrs", UNSET)
        for cidrs_item_data in _cidrs or []:
            cidrs_item = Cidr.from_dict(cidrs_item_data)

            cidrs.append(cidrs_item)

        command_type = d.pop("commandType", UNSET)

        tgw_update_cidrs_request = cls(
            cidrs=cidrs,
            command_type=command_type,
        )

        tgw_update_cidrs_request.additional_properties = d
        return tgw_update_cidrs_request

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

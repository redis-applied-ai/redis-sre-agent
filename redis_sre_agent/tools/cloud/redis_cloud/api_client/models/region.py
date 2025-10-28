from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.region_provider import RegionProvider
from ..types import UNSET, Unset

T = TypeVar("T", bound="Region")


@_attrs_define
class Region:
    """RedisLabs region information

    Attributes:
        name (Union[Unset, str]):
        provider (Union[Unset, RegionProvider]):
    """

    name: Union[Unset, str] = UNSET
    provider: Union[Unset, RegionProvider] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        provider: Union[Unset, str] = UNSET
        if not isinstance(self.provider, Unset):
            provider = self.provider.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if provider is not UNSET:
            field_dict["provider"] = provider

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name", UNSET)

        _provider = d.pop("provider", UNSET)
        provider: Union[Unset, RegionProvider]
        if isinstance(_provider, Unset):
            provider = UNSET
        else:
            provider = RegionProvider(_provider)

        region = cls(
            name=name,
            provider=provider,
        )

        region.additional_properties = d
        return region

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

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="RedisVersion")


@_attrs_define
class RedisVersion:
    """
    Attributes:
        version (Union[Unset, str]):
        eol_date (Union[Unset, datetime.date]):
        is_preview (Union[Unset, bool]):
        is_default (Union[Unset, bool]):
    """

    version: Union[Unset, str] = UNSET
    eol_date: Union[Unset, datetime.date] = UNSET
    is_preview: Union[Unset, bool] = UNSET
    is_default: Union[Unset, bool] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        version = self.version

        eol_date: Union[Unset, str] = UNSET
        if not isinstance(self.eol_date, Unset):
            eol_date = self.eol_date.isoformat()

        is_preview = self.is_preview

        is_default = self.is_default

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if version is not UNSET:
            field_dict["version"] = version
        if eol_date is not UNSET:
            field_dict["eolDate"] = eol_date
        if is_preview is not UNSET:
            field_dict["isPreview"] = is_preview
        if is_default is not UNSET:
            field_dict["isDefault"] = is_default

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        version = d.pop("version", UNSET)

        _eol_date = d.pop("eolDate", UNSET)
        eol_date: Union[Unset, datetime.date]
        if isinstance(_eol_date, Unset):
            eol_date = UNSET
        else:
            eol_date = isoparse(_eol_date).date()

        is_preview = d.pop("isPreview", UNSET)

        is_default = d.pop("isDefault", UNSET)

        redis_version = cls(
            version=version,
            eol_date=eol_date,
            is_preview=is_preview,
            is_default=is_default,
        )

        redis_version.additional_properties = d
        return redis_version

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

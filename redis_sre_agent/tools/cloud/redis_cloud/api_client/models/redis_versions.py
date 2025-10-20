from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.redis_version import RedisVersion


T = TypeVar("T", bound="RedisVersions")


@_attrs_define
class RedisVersions:
    """
    Attributes:
        redis_versions (Union[Unset, list['RedisVersion']]):
    """

    redis_versions: Union[Unset, list["RedisVersion"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        redis_versions: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.redis_versions, Unset):
            redis_versions = []
            for redis_versions_item_data in self.redis_versions:
                redis_versions_item = redis_versions_item_data.to_dict()
                redis_versions.append(redis_versions_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if redis_versions is not UNSET:
            field_dict["redisVersions"] = redis_versions

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.redis_version import RedisVersion

        d = dict(src_dict)
        redis_versions = []
        _redis_versions = d.pop("redisVersions", UNSET)
        for redis_versions_item_data in _redis_versions or []:
            redis_versions_item = RedisVersion.from_dict(redis_versions_item_data)

            redis_versions.append(redis_versions_item)

        redis_versions = cls(
            redis_versions=redis_versions,
        )

        redis_versions.additional_properties = d
        return redis_versions

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

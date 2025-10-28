from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.bdb_version_upgrade_status_upgrade_status import BdbVersionUpgradeStatusUpgradeStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="BdbVersionUpgradeStatus")


@_attrs_define
class BdbVersionUpgradeStatus:
    """
    Attributes:
        database_id (Union[Unset, int]):
        target_redis_version (Union[Unset, str]):
        progress (Union[Unset, float]):
        upgrade_status (Union[Unset, BdbVersionUpgradeStatusUpgradeStatus]):
    """

    database_id: Union[Unset, int] = UNSET
    target_redis_version: Union[Unset, str] = UNSET
    progress: Union[Unset, float] = UNSET
    upgrade_status: Union[Unset, BdbVersionUpgradeStatusUpgradeStatus] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        database_id = self.database_id

        target_redis_version = self.target_redis_version

        progress = self.progress

        upgrade_status: Union[Unset, str] = UNSET
        if not isinstance(self.upgrade_status, Unset):
            upgrade_status = self.upgrade_status.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if database_id is not UNSET:
            field_dict["databaseId"] = database_id
        if target_redis_version is not UNSET:
            field_dict["targetRedisVersion"] = target_redis_version
        if progress is not UNSET:
            field_dict["progress"] = progress
        if upgrade_status is not UNSET:
            field_dict["upgradeStatus"] = upgrade_status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        database_id = d.pop("databaseId", UNSET)

        target_redis_version = d.pop("targetRedisVersion", UNSET)

        progress = d.pop("progress", UNSET)

        _upgrade_status = d.pop("upgradeStatus", UNSET)
        upgrade_status: Union[Unset, BdbVersionUpgradeStatusUpgradeStatus]
        if isinstance(_upgrade_status, Unset):
            upgrade_status = UNSET
        else:
            upgrade_status = BdbVersionUpgradeStatusUpgradeStatus(_upgrade_status)

        bdb_version_upgrade_status = cls(
            database_id=database_id,
            target_redis_version=target_redis_version,
            progress=progress,
            upgrade_status=upgrade_status,
        )

        bdb_version_upgrade_status.additional_properties = d
        return bdb_version_upgrade_status

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

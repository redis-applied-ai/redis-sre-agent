from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="DatabaseBackupRequest")


@_attrs_define
class DatabaseBackupRequest:
    """Database backup request message

    Attributes:
        subscription_id (Union[Unset, int]):
        database_id (Union[Unset, int]):
        region_name (Union[Unset, str]): Required for Active-Active databases. Name of the cloud provider region to back
            up. When backing up an Active-Active database, you must back up each region separately.
        adhoc_backup_path (Union[Unset, str]): Optional. Manually backs up data to this location, instead of the set
            'remoteBackup' location. Example: s3://<backup-path>.
        command_type (Union[Unset, str]):
    """

    subscription_id: Union[Unset, int] = UNSET
    database_id: Union[Unset, int] = UNSET
    region_name: Union[Unset, str] = UNSET
    adhoc_backup_path: Union[Unset, str] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        database_id = self.database_id

        region_name = self.region_name

        adhoc_backup_path = self.adhoc_backup_path

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if database_id is not UNSET:
            field_dict["databaseId"] = database_id
        if region_name is not UNSET:
            field_dict["regionName"] = region_name
        if adhoc_backup_path is not UNSET:
            field_dict["adhocBackupPath"] = adhoc_backup_path
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId", UNSET)

        database_id = d.pop("databaseId", UNSET)

        region_name = d.pop("regionName", UNSET)

        adhoc_backup_path = d.pop("adhocBackupPath", UNSET)

        command_type = d.pop("commandType", UNSET)

        database_backup_request = cls(
            subscription_id=subscription_id,
            database_id=database_id,
            region_name=region_name,
            adhoc_backup_path=adhoc_backup_path,
            command_type=command_type,
        )

        database_backup_request.additional_properties = d
        return database_backup_request

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

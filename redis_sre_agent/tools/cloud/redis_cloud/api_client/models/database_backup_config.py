from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.database_backup_config_backup_interval import DatabaseBackupConfigBackupInterval
from ..models.database_backup_config_backup_storage_type import DatabaseBackupConfigBackupStorageType
from ..models.database_backup_config_database_backup_time_utc import DatabaseBackupConfigDatabaseBackupTimeUTC
from ..types import UNSET, Unset

T = TypeVar("T", bound="DatabaseBackupConfig")


@_attrs_define
class DatabaseBackupConfig:
    """Optional. Changes Remote backup configuration details.

    Attributes:
        active (Union[Unset, bool]): Optional. Determine if backup should be active. Default: null
        interval (Union[Unset, str]): Required when active is 'true'. Defines the interval between backups. Format:
            'every-x-hours', where x is one of 24, 12, 6, 4, 2, or 1. Example: "every-4-hours"
        backup_interval (Union[Unset, DatabaseBackupConfigBackupInterval]):
        time_utc (Union[Unset, str]): Optional. Hour when the backup starts. Available only for "every-12-hours" and
            "every-24-hours" backup intervals. Specified as an hour in 24-hour UTC time. Example: "14:00" is 2 PM UTC.
        database_backup_time_utc (Union[Unset, DatabaseBackupConfigDatabaseBackupTimeUTC]):
        storage_type (Union[Unset, str]): Required when active is 'true'. Type of storage to host backup files. Can be
            "aws-s3", "google-blob-storage", "azure-blob-storage", or "ftp". See [Set up backup storage
            locations](https://redis.io/docs/latest/operate/rc/databases/back-up-data/#set-up-backup-storage-locations) to
            learn how to set up backup storage locations.
        backup_storage_type (Union[Unset, DatabaseBackupConfigBackupStorageType]):
        storage_path (Union[Unset, str]): Required when active is 'true'. Path to the backup storage location.
    """

    active: Union[Unset, bool] = UNSET
    interval: Union[Unset, str] = UNSET
    backup_interval: Union[Unset, DatabaseBackupConfigBackupInterval] = UNSET
    time_utc: Union[Unset, str] = UNSET
    database_backup_time_utc: Union[Unset, DatabaseBackupConfigDatabaseBackupTimeUTC] = UNSET
    storage_type: Union[Unset, str] = UNSET
    backup_storage_type: Union[Unset, DatabaseBackupConfigBackupStorageType] = UNSET
    storage_path: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        active = self.active

        interval = self.interval

        backup_interval: Union[Unset, str] = UNSET
        if not isinstance(self.backup_interval, Unset):
            backup_interval = self.backup_interval.value

        time_utc = self.time_utc

        database_backup_time_utc: Union[Unset, str] = UNSET
        if not isinstance(self.database_backup_time_utc, Unset):
            database_backup_time_utc = self.database_backup_time_utc.value

        storage_type = self.storage_type

        backup_storage_type: Union[Unset, str] = UNSET
        if not isinstance(self.backup_storage_type, Unset):
            backup_storage_type = self.backup_storage_type.value

        storage_path = self.storage_path

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if active is not UNSET:
            field_dict["active"] = active
        if interval is not UNSET:
            field_dict["interval"] = interval
        if backup_interval is not UNSET:
            field_dict["backupInterval"] = backup_interval
        if time_utc is not UNSET:
            field_dict["timeUTC"] = time_utc
        if database_backup_time_utc is not UNSET:
            field_dict["databaseBackupTimeUTC"] = database_backup_time_utc
        if storage_type is not UNSET:
            field_dict["storageType"] = storage_type
        if backup_storage_type is not UNSET:
            field_dict["backupStorageType"] = backup_storage_type
        if storage_path is not UNSET:
            field_dict["storagePath"] = storage_path

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        active = d.pop("active", UNSET)

        interval = d.pop("interval", UNSET)

        _backup_interval = d.pop("backupInterval", UNSET)
        backup_interval: Union[Unset, DatabaseBackupConfigBackupInterval]
        if isinstance(_backup_interval, Unset):
            backup_interval = UNSET
        else:
            backup_interval = DatabaseBackupConfigBackupInterval(_backup_interval)

        time_utc = d.pop("timeUTC", UNSET)

        _database_backup_time_utc = d.pop("databaseBackupTimeUTC", UNSET)
        database_backup_time_utc: Union[Unset, DatabaseBackupConfigDatabaseBackupTimeUTC]
        if isinstance(_database_backup_time_utc, Unset):
            database_backup_time_utc = UNSET
        else:
            database_backup_time_utc = DatabaseBackupConfigDatabaseBackupTimeUTC(_database_backup_time_utc)

        storage_type = d.pop("storageType", UNSET)

        _backup_storage_type = d.pop("backupStorageType", UNSET)
        backup_storage_type: Union[Unset, DatabaseBackupConfigBackupStorageType]
        if isinstance(_backup_storage_type, Unset):
            backup_storage_type = UNSET
        else:
            backup_storage_type = DatabaseBackupConfigBackupStorageType(_backup_storage_type)

        storage_path = d.pop("storagePath", UNSET)

        database_backup_config = cls(
            active=active,
            interval=interval,
            backup_interval=backup_interval,
            time_utc=time_utc,
            database_backup_time_utc=database_backup_time_utc,
            storage_type=storage_type,
            backup_storage_type=backup_storage_type,
            storage_path=storage_path,
        )

        database_backup_config.additional_properties = d
        return database_backup_config

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

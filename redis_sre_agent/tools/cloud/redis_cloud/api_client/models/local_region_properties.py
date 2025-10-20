from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.local_region_properties_data_persistence import LocalRegionPropertiesDataPersistence
from ..models.local_region_properties_resp_version import LocalRegionPropertiesRespVersion
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.database_alert_spec import DatabaseAlertSpec
    from ..models.database_backup_config import DatabaseBackupConfig
    from ..models.local_throughput import LocalThroughput


T = TypeVar("T", bound="LocalRegionProperties")


@_attrs_define
class LocalRegionProperties:
    """Optional. A list of regions and local settings to update.

    Attributes:
        region (Union[Unset, str]): Required. Name of the region to update.
        remote_backup (Union[Unset, DatabaseBackupConfig]): Optional. Changes Remote backup configuration details.
        local_throughput_measurement (Union[Unset, LocalThroughput]): Optional. Expected read and write throughput for
            this region.
        data_persistence (Union[Unset, LocalRegionPropertiesDataPersistence]): Optional. Type and rate of data
            persistence for this region. If set, 'globalDataPersistence' will not apply to this region.
        password (Union[Unset, str]): Optional. Changes the password used to access the database in this region. If set,
            'globalPassword' will not apply to this region. Example: P@ssw0rd.
        source_ip (Union[Unset, list[str]]): Optional. List of source IP addresses or subnet masks to whitelist in this
            region. If set, Redis clients will be able to connect to the database in this region only from within the
            specified source IP addresses ranges, and 'globalSourceIp' will not apply to this region. Example:
            ['192.168.10.0/32', '192.168.12.0/24']
        alerts (Union[Unset, list['DatabaseAlertSpec']]): Optional. Redis database alert settings for this region. If
            set, 'glboalAlerts' will not apply to this region.
        resp_version (Union[Unset, LocalRegionPropertiesRespVersion]): Optional. Redis Serialization Protocol version
            for this region. Must be compatible with Redis version. Example: resp3.
        enable_default_user (Union[Unset, bool]): Optional. When 'true', allows connecting to the database with the
            'default' user. When 'false', only defined access control users can connect to the database. If set,
            'globalEnableDefaultUser' will not apply to this region.
    """

    region: Union[Unset, str] = UNSET
    remote_backup: Union[Unset, "DatabaseBackupConfig"] = UNSET
    local_throughput_measurement: Union[Unset, "LocalThroughput"] = UNSET
    data_persistence: Union[Unset, LocalRegionPropertiesDataPersistence] = UNSET
    password: Union[Unset, str] = UNSET
    source_ip: Union[Unset, list[str]] = UNSET
    alerts: Union[Unset, list["DatabaseAlertSpec"]] = UNSET
    resp_version: Union[Unset, LocalRegionPropertiesRespVersion] = UNSET
    enable_default_user: Union[Unset, bool] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        region = self.region

        remote_backup: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.remote_backup, Unset):
            remote_backup = self.remote_backup.to_dict()

        local_throughput_measurement: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.local_throughput_measurement, Unset):
            local_throughput_measurement = self.local_throughput_measurement.to_dict()

        data_persistence: Union[Unset, str] = UNSET
        if not isinstance(self.data_persistence, Unset):
            data_persistence = self.data_persistence.value

        password = self.password

        source_ip: Union[Unset, list[str]] = UNSET
        if not isinstance(self.source_ip, Unset):
            source_ip = self.source_ip

        alerts: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.alerts, Unset):
            alerts = []
            for alerts_item_data in self.alerts:
                alerts_item = alerts_item_data.to_dict()
                alerts.append(alerts_item)

        resp_version: Union[Unset, str] = UNSET
        if not isinstance(self.resp_version, Unset):
            resp_version = self.resp_version.value

        enable_default_user = self.enable_default_user

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if region is not UNSET:
            field_dict["region"] = region
        if remote_backup is not UNSET:
            field_dict["remoteBackup"] = remote_backup
        if local_throughput_measurement is not UNSET:
            field_dict["localThroughputMeasurement"] = local_throughput_measurement
        if data_persistence is not UNSET:
            field_dict["dataPersistence"] = data_persistence
        if password is not UNSET:
            field_dict["password"] = password
        if source_ip is not UNSET:
            field_dict["sourceIp"] = source_ip
        if alerts is not UNSET:
            field_dict["alerts"] = alerts
        if resp_version is not UNSET:
            field_dict["respVersion"] = resp_version
        if enable_default_user is not UNSET:
            field_dict["enableDefaultUser"] = enable_default_user

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.database_alert_spec import DatabaseAlertSpec
        from ..models.database_backup_config import DatabaseBackupConfig
        from ..models.local_throughput import LocalThroughput

        d = dict(src_dict)
        region = d.pop("region", UNSET)

        _remote_backup = d.pop("remoteBackup", UNSET)
        remote_backup: Union[Unset, DatabaseBackupConfig]
        if isinstance(_remote_backup, Unset):
            remote_backup = UNSET
        else:
            remote_backup = DatabaseBackupConfig.from_dict(_remote_backup)

        _local_throughput_measurement = d.pop("localThroughputMeasurement", UNSET)
        local_throughput_measurement: Union[Unset, LocalThroughput]
        if isinstance(_local_throughput_measurement, Unset):
            local_throughput_measurement = UNSET
        else:
            local_throughput_measurement = LocalThroughput.from_dict(_local_throughput_measurement)

        _data_persistence = d.pop("dataPersistence", UNSET)
        data_persistence: Union[Unset, LocalRegionPropertiesDataPersistence]
        if isinstance(_data_persistence, Unset):
            data_persistence = UNSET
        else:
            data_persistence = LocalRegionPropertiesDataPersistence(_data_persistence)

        password = d.pop("password", UNSET)

        source_ip = cast(list[str], d.pop("sourceIp", UNSET))

        alerts = []
        _alerts = d.pop("alerts", UNSET)
        for alerts_item_data in _alerts or []:
            alerts_item = DatabaseAlertSpec.from_dict(alerts_item_data)

            alerts.append(alerts_item)

        _resp_version = d.pop("respVersion", UNSET)
        resp_version: Union[Unset, LocalRegionPropertiesRespVersion]
        if isinstance(_resp_version, Unset):
            resp_version = UNSET
        else:
            resp_version = LocalRegionPropertiesRespVersion(_resp_version)

        enable_default_user = d.pop("enableDefaultUser", UNSET)

        local_region_properties = cls(
            region=region,
            remote_backup=remote_backup,
            local_throughput_measurement=local_throughput_measurement,
            data_persistence=data_persistence,
            password=password,
            source_ip=source_ip,
            alerts=alerts,
            resp_version=resp_version,
            enable_default_user=enable_default_user,
        )

        local_region_properties.additional_properties = d
        return local_region_properties

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

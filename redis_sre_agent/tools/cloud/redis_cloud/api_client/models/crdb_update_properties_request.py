from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.crdb_update_properties_request_data_eviction_policy import CrdbUpdatePropertiesRequestDataEvictionPolicy
from ..models.crdb_update_properties_request_global_data_persistence import (
    CrdbUpdatePropertiesRequestGlobalDataPersistence,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.database_alert_spec import DatabaseAlertSpec
    from ..models.database_certificate_spec import DatabaseCertificateSpec
    from ..models.local_region_properties import LocalRegionProperties


T = TypeVar("T", bound="CrdbUpdatePropertiesRequest")


@_attrs_define
class CrdbUpdatePropertiesRequest:
    r"""Active-Active database update local properties request message

    Attributes:
        subscription_id (Union[Unset, int]):
        database_id (Union[Unset, int]):
        name (Union[Unset, str]): Optional. Updated database name. Database name is limited to 40 characters or less and
            must include only letters, digits, and hyphens ('-'). It must start with a letter and end with a letter or
            digit. Example: Redis-database-example.
        dry_run (Union[Unset, bool]): Optional. When 'false': Creates a deployment plan and deploys it, updating any
            resources required by the plan. When 'true': creates a read-only deployment plan and does not update any
            resources. Default: 'false'
        memory_limit_in_gb (Union[Unset, float]): Optional. Total memory in GB, including replication and other
            overhead. You cannot set both datasetSizeInGb and totalMemoryInGb. Example: 1.
        dataset_size_in_gb (Union[Unset, float]): Optional. The maximum amount of data in the dataset for this database
            in GB. You cannot set both datasetSizeInGb and totalMemoryInGb. If ‘replication’ is 'true', the database’s total
            memory will be twice as large as the datasetSizeInGb.If ‘replication’ is false, the database’s total memory will
            be the datasetSizeInGb value. Example: 1.
        support_oss_cluster_api (Union[Unset, bool]): Optional. Support Redis [OSS Cluster
            API](https://redis.io/docs/latest/operate/rc/databases/configuration/clustering/#oss-cluster-api). Default:
            'false'
        use_external_endpoint_for_oss_cluster_api (Union[Unset, bool]): Optional. If set to 'true', the database will
            use the external endpoint for OSS Cluster API. This setting blocks the database's private endpoint. Can only be
            set if 'supportOSSClusterAPI' is 'true'.
        client_ssl_certificate (Union[Unset, str]): Optional. A public key client TLS/SSL certificate with new line
            characters replaced with '\n'. If specified, mTLS authentication will be required to authenticate user
            connections if it is not already required. If set to an empty string, TLS client certificates will be removed
            and mTLS will not be required. TLS connection may still apply, depending on the value of 'enableTls'.
        client_tls_certificates (Union[Unset, list['DatabaseCertificateSpec']]): Optional. A list of client TLS/SSL
            certificates. If specified, mTLS authentication will be required to authenticate user connections. If set to an
            empty list, TLS client certificates will be removed and mTLS will not be required. TLS connection may still
            apply, depending on the value of 'enableTls'.
        enable_tls (Union[Unset, bool]): Optional. When 'true', requires TLS authentication for all connections - mTLS
            with valid clientTlsCertificates, regular TLS when clientTlsCertificates is not provided. If enableTls is set to
            'false' while mTLS is required, it will remove the mTLS requirement and erase previously provided
            clientTlsCertificates.
        global_data_persistence (Union[Unset, CrdbUpdatePropertiesRequestGlobalDataPersistence]): Optional. Type and
            rate of data persistence in all regions that don't set local 'dataPersistence'.
        global_password (Union[Unset, str]): Optional. Changes the password used to access the database in all regions
            that don't set a local 'password'.
        global_enable_default_user (Union[Unset, bool]): Optional. When 'true', allows connecting to the database with
            the 'default' user in all regions that don't set local 'enableDefaultUser'. When 'false', only defined access
            control users can connect to the database.
        global_source_ip (Union[Unset, list[str]]): Optional. List of source IP addresses or subnet masks to whitelist
            in all regions that don't set local 'sourceIp' settings. If set, Redis clients will be able to connect to this
            database only from within the specified source IP addresses ranges. Example: ['192.168.10.0/32',
            '192.168.12.0/24']
        global_alerts (Union[Unset, list['DatabaseAlertSpec']]): Optional. Redis database alert settings in all regions
            that don't set local 'alerts'.
        regions (Union[Unset, list['LocalRegionProperties']]): Optional. A list of regions and local settings to update.
        data_eviction_policy (Union[Unset, CrdbUpdatePropertiesRequestDataEvictionPolicy]): Optional. Data eviction
            policy.
        command_type (Union[Unset, str]):
    """

    subscription_id: Union[Unset, int] = UNSET
    database_id: Union[Unset, int] = UNSET
    name: Union[Unset, str] = UNSET
    dry_run: Union[Unset, bool] = UNSET
    memory_limit_in_gb: Union[Unset, float] = UNSET
    dataset_size_in_gb: Union[Unset, float] = UNSET
    support_oss_cluster_api: Union[Unset, bool] = UNSET
    use_external_endpoint_for_oss_cluster_api: Union[Unset, bool] = UNSET
    client_ssl_certificate: Union[Unset, str] = UNSET
    client_tls_certificates: Union[Unset, list["DatabaseCertificateSpec"]] = UNSET
    enable_tls: Union[Unset, bool] = UNSET
    global_data_persistence: Union[Unset, CrdbUpdatePropertiesRequestGlobalDataPersistence] = UNSET
    global_password: Union[Unset, str] = UNSET
    global_enable_default_user: Union[Unset, bool] = UNSET
    global_source_ip: Union[Unset, list[str]] = UNSET
    global_alerts: Union[Unset, list["DatabaseAlertSpec"]] = UNSET
    regions: Union[Unset, list["LocalRegionProperties"]] = UNSET
    data_eviction_policy: Union[Unset, CrdbUpdatePropertiesRequestDataEvictionPolicy] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        database_id = self.database_id

        name = self.name

        dry_run = self.dry_run

        memory_limit_in_gb = self.memory_limit_in_gb

        dataset_size_in_gb = self.dataset_size_in_gb

        support_oss_cluster_api = self.support_oss_cluster_api

        use_external_endpoint_for_oss_cluster_api = self.use_external_endpoint_for_oss_cluster_api

        client_ssl_certificate = self.client_ssl_certificate

        client_tls_certificates: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.client_tls_certificates, Unset):
            client_tls_certificates = []
            for client_tls_certificates_item_data in self.client_tls_certificates:
                client_tls_certificates_item = client_tls_certificates_item_data.to_dict()
                client_tls_certificates.append(client_tls_certificates_item)

        enable_tls = self.enable_tls

        global_data_persistence: Union[Unset, str] = UNSET
        if not isinstance(self.global_data_persistence, Unset):
            global_data_persistence = self.global_data_persistence.value

        global_password = self.global_password

        global_enable_default_user = self.global_enable_default_user

        global_source_ip: Union[Unset, list[str]] = UNSET
        if not isinstance(self.global_source_ip, Unset):
            global_source_ip = self.global_source_ip

        global_alerts: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.global_alerts, Unset):
            global_alerts = []
            for global_alerts_item_data in self.global_alerts:
                global_alerts_item = global_alerts_item_data.to_dict()
                global_alerts.append(global_alerts_item)

        regions: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.regions, Unset):
            regions = []
            for regions_item_data in self.regions:
                regions_item = regions_item_data.to_dict()
                regions.append(regions_item)

        data_eviction_policy: Union[Unset, str] = UNSET
        if not isinstance(self.data_eviction_policy, Unset):
            data_eviction_policy = self.data_eviction_policy.value

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if database_id is not UNSET:
            field_dict["databaseId"] = database_id
        if name is not UNSET:
            field_dict["name"] = name
        if dry_run is not UNSET:
            field_dict["dryRun"] = dry_run
        if memory_limit_in_gb is not UNSET:
            field_dict["memoryLimitInGb"] = memory_limit_in_gb
        if dataset_size_in_gb is not UNSET:
            field_dict["datasetSizeInGb"] = dataset_size_in_gb
        if support_oss_cluster_api is not UNSET:
            field_dict["supportOSSClusterApi"] = support_oss_cluster_api
        if use_external_endpoint_for_oss_cluster_api is not UNSET:
            field_dict["useExternalEndpointForOSSClusterApi"] = use_external_endpoint_for_oss_cluster_api
        if client_ssl_certificate is not UNSET:
            field_dict["clientSslCertificate"] = client_ssl_certificate
        if client_tls_certificates is not UNSET:
            field_dict["clientTlsCertificates"] = client_tls_certificates
        if enable_tls is not UNSET:
            field_dict["enableTls"] = enable_tls
        if global_data_persistence is not UNSET:
            field_dict["globalDataPersistence"] = global_data_persistence
        if global_password is not UNSET:
            field_dict["globalPassword"] = global_password
        if global_enable_default_user is not UNSET:
            field_dict["globalEnableDefaultUser"] = global_enable_default_user
        if global_source_ip is not UNSET:
            field_dict["globalSourceIp"] = global_source_ip
        if global_alerts is not UNSET:
            field_dict["globalAlerts"] = global_alerts
        if regions is not UNSET:
            field_dict["regions"] = regions
        if data_eviction_policy is not UNSET:
            field_dict["dataEvictionPolicy"] = data_eviction_policy
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.database_alert_spec import DatabaseAlertSpec
        from ..models.database_certificate_spec import DatabaseCertificateSpec
        from ..models.local_region_properties import LocalRegionProperties

        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId", UNSET)

        database_id = d.pop("databaseId", UNSET)

        name = d.pop("name", UNSET)

        dry_run = d.pop("dryRun", UNSET)

        memory_limit_in_gb = d.pop("memoryLimitInGb", UNSET)

        dataset_size_in_gb = d.pop("datasetSizeInGb", UNSET)

        support_oss_cluster_api = d.pop("supportOSSClusterApi", UNSET)

        use_external_endpoint_for_oss_cluster_api = d.pop("useExternalEndpointForOSSClusterApi", UNSET)

        client_ssl_certificate = d.pop("clientSslCertificate", UNSET)

        client_tls_certificates = []
        _client_tls_certificates = d.pop("clientTlsCertificates", UNSET)
        for client_tls_certificates_item_data in _client_tls_certificates or []:
            client_tls_certificates_item = DatabaseCertificateSpec.from_dict(client_tls_certificates_item_data)

            client_tls_certificates.append(client_tls_certificates_item)

        enable_tls = d.pop("enableTls", UNSET)

        _global_data_persistence = d.pop("globalDataPersistence", UNSET)
        global_data_persistence: Union[Unset, CrdbUpdatePropertiesRequestGlobalDataPersistence]
        if isinstance(_global_data_persistence, Unset):
            global_data_persistence = UNSET
        else:
            global_data_persistence = CrdbUpdatePropertiesRequestGlobalDataPersistence(_global_data_persistence)

        global_password = d.pop("globalPassword", UNSET)

        global_enable_default_user = d.pop("globalEnableDefaultUser", UNSET)

        global_source_ip = cast(list[str], d.pop("globalSourceIp", UNSET))

        global_alerts = []
        _global_alerts = d.pop("globalAlerts", UNSET)
        for global_alerts_item_data in _global_alerts or []:
            global_alerts_item = DatabaseAlertSpec.from_dict(global_alerts_item_data)

            global_alerts.append(global_alerts_item)

        regions = []
        _regions = d.pop("regions", UNSET)
        for regions_item_data in _regions or []:
            regions_item = LocalRegionProperties.from_dict(regions_item_data)

            regions.append(regions_item)

        _data_eviction_policy = d.pop("dataEvictionPolicy", UNSET)
        data_eviction_policy: Union[Unset, CrdbUpdatePropertiesRequestDataEvictionPolicy]
        if isinstance(_data_eviction_policy, Unset):
            data_eviction_policy = UNSET
        else:
            data_eviction_policy = CrdbUpdatePropertiesRequestDataEvictionPolicy(_data_eviction_policy)

        command_type = d.pop("commandType", UNSET)

        crdb_update_properties_request = cls(
            subscription_id=subscription_id,
            database_id=database_id,
            name=name,
            dry_run=dry_run,
            memory_limit_in_gb=memory_limit_in_gb,
            dataset_size_in_gb=dataset_size_in_gb,
            support_oss_cluster_api=support_oss_cluster_api,
            use_external_endpoint_for_oss_cluster_api=use_external_endpoint_for_oss_cluster_api,
            client_ssl_certificate=client_ssl_certificate,
            client_tls_certificates=client_tls_certificates,
            enable_tls=enable_tls,
            global_data_persistence=global_data_persistence,
            global_password=global_password,
            global_enable_default_user=global_enable_default_user,
            global_source_ip=global_source_ip,
            global_alerts=global_alerts,
            regions=regions,
            data_eviction_policy=data_eviction_policy,
            command_type=command_type,
        )

        crdb_update_properties_request.additional_properties = d
        return crdb_update_properties_request

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

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.fixed_database_update_request_data_eviction_policy import FixedDatabaseUpdateRequestDataEvictionPolicy
from ..models.fixed_database_update_request_data_persistence import FixedDatabaseUpdateRequestDataPersistence
from ..models.fixed_database_update_request_resp_version import FixedDatabaseUpdateRequestRespVersion
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.database_alert_spec import DatabaseAlertSpec
    from ..models.database_certificate_spec import DatabaseCertificateSpec
    from ..models.replica_of_spec import ReplicaOfSpec


T = TypeVar("T", bound="FixedDatabaseUpdateRequest")


@_attrs_define
class FixedDatabaseUpdateRequest:
    r"""Essentials database update request

    Attributes:
        subscription_id (Union[Unset, int]):
        database_id (Union[Unset, int]):
        name (Union[Unset, str]): Optional. Updated database name. Example: Redis-Essentials-database-example.
        memory_limit_in_gb (Union[Unset, float]): (Pay-as-you-go subscriptions only) Optional. Total memory in GB,
            including replication and other overhead. You cannot set both datasetSizeInGb and totalMemoryInGb. Example: 1.
        dataset_size_in_gb (Union[Unset, float]): (Pay-as-you-go subscriptions only) Optional. The maximum amount of
            data in the dataset for this database in GB. You cannot set both datasetSizeInGb and totalMemoryInGb. If
            ‘replication’ is 'true', the database’s total memory will be twice as large as the datasetSizeInGb. If
            ‘replication’ is false, the database’s total memory will be the datasetSizeInGb value. Example: 1.
        support_oss_cluster_api (Union[Unset, bool]): (Pay-as-you-go subscriptions only) Optional. Support Redis [OSS
            Cluster API](https://redis.io/docs/latest/operate/rc/databases/configuration/clustering/#oss-cluster-api).
            Example: True.
        resp_version (Union[Unset, FixedDatabaseUpdateRequestRespVersion]): Optional. Redis Serialization Protocol
            version. Must be compatible with Redis version. Example: resp3.
        use_external_endpoint_for_oss_cluster_api (Union[Unset, bool]): (Pay-as-you-go subscriptions only) Optional. If
            set to 'true', the database will use the external endpoint for OSS Cluster API. This setting blocks the
            database's private endpoint. Can only be set if 'supportOSSClusterAPI' is 'true'. Default: 'false' Example:
            True.
        enable_database_clustering (Union[Unset, bool]): (Pay-as-you-go subscriptions only) Optional. Distributes
            database data to different cloud instances.
        number_of_shards (Union[Unset, int]): (Pay-as-you-go subscriptions only) Optional. Changes the number of master
            shards. Example: 2.
        data_persistence (Union[Unset, FixedDatabaseUpdateRequestDataPersistence]): Optional. Type and rate of data
            persistence in persistent storage. Use GET /fixed/plans/{planId} to see if your plan supports data persistence.
        data_eviction_policy (Union[Unset, FixedDatabaseUpdateRequestDataEvictionPolicy]): Optional. Turns database
            replication on or off.
        replication (Union[Unset, bool]): Optional. Sets database replication. Use GET /fixed/plans/{planId} to see if
            your plan supports database replication.
        periodic_backup_path (Union[Unset, str]): Optional. Changes the backup location path. If specified, the database
            will back up every 24 hours to this location, and you can manually back up the database to this location at any
            time. Use GET /fixed/plans/{planId} to see if your plan supports database backups. If set to an empty string,
            the backup path will be removed. Example: s3://<backup-path>.
        source_ips (Union[Unset, list[str]]): Optional. List of source IP addresses or subnet masks to allow. If
            specified, Redis clients will be able to connect to this database only from within the specified source IP
            addresses ranges. Example: '['192.168.10.0/32', '192.168.12.0/24']'
        replica_of (Union[Unset, list[str]]): Optional. This database will be a replica of the specified Redis databases
            provided as one or more URI (sample format: 'redis://user:password@host:port)'. If the URI provided is Redis
            Cloud instance, only host and port should be provided (using the format: ['redis://endpoint1:6379',
            'redis://endpoint2:6380'] ).
        replica (Union[Unset, ReplicaOfSpec]): Optional. Changes Replica Of (also known as Active-Passive) configuration
            details.
        regex_rules (Union[Unset, list[str]]): (Pay-as-you-go subscriptions only) Optional. Hashing policy Regex rules.
            Used only if 'shardingType' is 'custom-regex-rules'.
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
        password (Union[Unset, str]): Optional. Changes the password used to access the database with the 'default'
            user.
        enable_default_user (Union[Unset, bool]): Optional. When 'true', allows connecting to the database with the
            'default' user. When 'false', only defined access control users can connect to the database.
        alerts (Union[Unset, list['DatabaseAlertSpec']]): Optional. Changes Redis database alert details.
        command_type (Union[Unset, str]):
    """

    subscription_id: Union[Unset, int] = UNSET
    database_id: Union[Unset, int] = UNSET
    name: Union[Unset, str] = UNSET
    memory_limit_in_gb: Union[Unset, float] = UNSET
    dataset_size_in_gb: Union[Unset, float] = UNSET
    support_oss_cluster_api: Union[Unset, bool] = UNSET
    resp_version: Union[Unset, FixedDatabaseUpdateRequestRespVersion] = UNSET
    use_external_endpoint_for_oss_cluster_api: Union[Unset, bool] = UNSET
    enable_database_clustering: Union[Unset, bool] = UNSET
    number_of_shards: Union[Unset, int] = UNSET
    data_persistence: Union[Unset, FixedDatabaseUpdateRequestDataPersistence] = UNSET
    data_eviction_policy: Union[Unset, FixedDatabaseUpdateRequestDataEvictionPolicy] = UNSET
    replication: Union[Unset, bool] = UNSET
    periodic_backup_path: Union[Unset, str] = UNSET
    source_ips: Union[Unset, list[str]] = UNSET
    replica_of: Union[Unset, list[str]] = UNSET
    replica: Union[Unset, "ReplicaOfSpec"] = UNSET
    regex_rules: Union[Unset, list[str]] = UNSET
    client_ssl_certificate: Union[Unset, str] = UNSET
    client_tls_certificates: Union[Unset, list["DatabaseCertificateSpec"]] = UNSET
    enable_tls: Union[Unset, bool] = UNSET
    password: Union[Unset, str] = UNSET
    enable_default_user: Union[Unset, bool] = UNSET
    alerts: Union[Unset, list["DatabaseAlertSpec"]] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        database_id = self.database_id

        name = self.name

        memory_limit_in_gb = self.memory_limit_in_gb

        dataset_size_in_gb = self.dataset_size_in_gb

        support_oss_cluster_api = self.support_oss_cluster_api

        resp_version: Union[Unset, str] = UNSET
        if not isinstance(self.resp_version, Unset):
            resp_version = self.resp_version.value

        use_external_endpoint_for_oss_cluster_api = self.use_external_endpoint_for_oss_cluster_api

        enable_database_clustering = self.enable_database_clustering

        number_of_shards = self.number_of_shards

        data_persistence: Union[Unset, str] = UNSET
        if not isinstance(self.data_persistence, Unset):
            data_persistence = self.data_persistence.value

        data_eviction_policy: Union[Unset, str] = UNSET
        if not isinstance(self.data_eviction_policy, Unset):
            data_eviction_policy = self.data_eviction_policy.value

        replication = self.replication

        periodic_backup_path = self.periodic_backup_path

        source_ips: Union[Unset, list[str]] = UNSET
        if not isinstance(self.source_ips, Unset):
            source_ips = self.source_ips

        replica_of: Union[Unset, list[str]] = UNSET
        if not isinstance(self.replica_of, Unset):
            replica_of = self.replica_of

        replica: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.replica, Unset):
            replica = self.replica.to_dict()

        regex_rules: Union[Unset, list[str]] = UNSET
        if not isinstance(self.regex_rules, Unset):
            regex_rules = self.regex_rules

        client_ssl_certificate = self.client_ssl_certificate

        client_tls_certificates: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.client_tls_certificates, Unset):
            client_tls_certificates = []
            for client_tls_certificates_item_data in self.client_tls_certificates:
                client_tls_certificates_item = client_tls_certificates_item_data.to_dict()
                client_tls_certificates.append(client_tls_certificates_item)

        enable_tls = self.enable_tls

        password = self.password

        enable_default_user = self.enable_default_user

        alerts: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.alerts, Unset):
            alerts = []
            for alerts_item_data in self.alerts:
                alerts_item = alerts_item_data.to_dict()
                alerts.append(alerts_item)

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
        if memory_limit_in_gb is not UNSET:
            field_dict["memoryLimitInGb"] = memory_limit_in_gb
        if dataset_size_in_gb is not UNSET:
            field_dict["datasetSizeInGb"] = dataset_size_in_gb
        if support_oss_cluster_api is not UNSET:
            field_dict["supportOSSClusterApi"] = support_oss_cluster_api
        if resp_version is not UNSET:
            field_dict["respVersion"] = resp_version
        if use_external_endpoint_for_oss_cluster_api is not UNSET:
            field_dict["useExternalEndpointForOSSClusterApi"] = use_external_endpoint_for_oss_cluster_api
        if enable_database_clustering is not UNSET:
            field_dict["enableDatabaseClustering"] = enable_database_clustering
        if number_of_shards is not UNSET:
            field_dict["numberOfShards"] = number_of_shards
        if data_persistence is not UNSET:
            field_dict["dataPersistence"] = data_persistence
        if data_eviction_policy is not UNSET:
            field_dict["dataEvictionPolicy"] = data_eviction_policy
        if replication is not UNSET:
            field_dict["replication"] = replication
        if periodic_backup_path is not UNSET:
            field_dict["periodicBackupPath"] = periodic_backup_path
        if source_ips is not UNSET:
            field_dict["sourceIps"] = source_ips
        if replica_of is not UNSET:
            field_dict["replicaOf"] = replica_of
        if replica is not UNSET:
            field_dict["replica"] = replica
        if regex_rules is not UNSET:
            field_dict["regexRules"] = regex_rules
        if client_ssl_certificate is not UNSET:
            field_dict["clientSslCertificate"] = client_ssl_certificate
        if client_tls_certificates is not UNSET:
            field_dict["clientTlsCertificates"] = client_tls_certificates
        if enable_tls is not UNSET:
            field_dict["enableTls"] = enable_tls
        if password is not UNSET:
            field_dict["password"] = password
        if enable_default_user is not UNSET:
            field_dict["enableDefaultUser"] = enable_default_user
        if alerts is not UNSET:
            field_dict["alerts"] = alerts
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.database_alert_spec import DatabaseAlertSpec
        from ..models.database_certificate_spec import DatabaseCertificateSpec
        from ..models.replica_of_spec import ReplicaOfSpec

        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId", UNSET)

        database_id = d.pop("databaseId", UNSET)

        name = d.pop("name", UNSET)

        memory_limit_in_gb = d.pop("memoryLimitInGb", UNSET)

        dataset_size_in_gb = d.pop("datasetSizeInGb", UNSET)

        support_oss_cluster_api = d.pop("supportOSSClusterApi", UNSET)

        _resp_version = d.pop("respVersion", UNSET)
        resp_version: Union[Unset, FixedDatabaseUpdateRequestRespVersion]
        if isinstance(_resp_version, Unset):
            resp_version = UNSET
        else:
            resp_version = FixedDatabaseUpdateRequestRespVersion(_resp_version)

        use_external_endpoint_for_oss_cluster_api = d.pop("useExternalEndpointForOSSClusterApi", UNSET)

        enable_database_clustering = d.pop("enableDatabaseClustering", UNSET)

        number_of_shards = d.pop("numberOfShards", UNSET)

        _data_persistence = d.pop("dataPersistence", UNSET)
        data_persistence: Union[Unset, FixedDatabaseUpdateRequestDataPersistence]
        if isinstance(_data_persistence, Unset):
            data_persistence = UNSET
        else:
            data_persistence = FixedDatabaseUpdateRequestDataPersistence(_data_persistence)

        _data_eviction_policy = d.pop("dataEvictionPolicy", UNSET)
        data_eviction_policy: Union[Unset, FixedDatabaseUpdateRequestDataEvictionPolicy]
        if isinstance(_data_eviction_policy, Unset):
            data_eviction_policy = UNSET
        else:
            data_eviction_policy = FixedDatabaseUpdateRequestDataEvictionPolicy(_data_eviction_policy)

        replication = d.pop("replication", UNSET)

        periodic_backup_path = d.pop("periodicBackupPath", UNSET)

        source_ips = cast(list[str], d.pop("sourceIps", UNSET))

        replica_of = cast(list[str], d.pop("replicaOf", UNSET))

        _replica = d.pop("replica", UNSET)
        replica: Union[Unset, ReplicaOfSpec]
        if isinstance(_replica, Unset):
            replica = UNSET
        else:
            replica = ReplicaOfSpec.from_dict(_replica)

        regex_rules = cast(list[str], d.pop("regexRules", UNSET))

        client_ssl_certificate = d.pop("clientSslCertificate", UNSET)

        client_tls_certificates = []
        _client_tls_certificates = d.pop("clientTlsCertificates", UNSET)
        for client_tls_certificates_item_data in _client_tls_certificates or []:
            client_tls_certificates_item = DatabaseCertificateSpec.from_dict(client_tls_certificates_item_data)

            client_tls_certificates.append(client_tls_certificates_item)

        enable_tls = d.pop("enableTls", UNSET)

        password = d.pop("password", UNSET)

        enable_default_user = d.pop("enableDefaultUser", UNSET)

        alerts = []
        _alerts = d.pop("alerts", UNSET)
        for alerts_item_data in _alerts or []:
            alerts_item = DatabaseAlertSpec.from_dict(alerts_item_data)

            alerts.append(alerts_item)

        command_type = d.pop("commandType", UNSET)

        fixed_database_update_request = cls(
            subscription_id=subscription_id,
            database_id=database_id,
            name=name,
            memory_limit_in_gb=memory_limit_in_gb,
            dataset_size_in_gb=dataset_size_in_gb,
            support_oss_cluster_api=support_oss_cluster_api,
            resp_version=resp_version,
            use_external_endpoint_for_oss_cluster_api=use_external_endpoint_for_oss_cluster_api,
            enable_database_clustering=enable_database_clustering,
            number_of_shards=number_of_shards,
            data_persistence=data_persistence,
            data_eviction_policy=data_eviction_policy,
            replication=replication,
            periodic_backup_path=periodic_backup_path,
            source_ips=source_ips,
            replica_of=replica_of,
            replica=replica,
            regex_rules=regex_rules,
            client_ssl_certificate=client_ssl_certificate,
            client_tls_certificates=client_tls_certificates,
            enable_tls=enable_tls,
            password=password,
            enable_default_user=enable_default_user,
            alerts=alerts,
            command_type=command_type,
        )

        fixed_database_update_request.additional_properties = d
        return fixed_database_update_request

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

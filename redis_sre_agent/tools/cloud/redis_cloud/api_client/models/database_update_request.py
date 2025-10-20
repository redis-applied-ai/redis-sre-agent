from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.database_update_request_data_eviction_policy import DatabaseUpdateRequestDataEvictionPolicy
from ..models.database_update_request_data_persistence import DatabaseUpdateRequestDataPersistence
from ..models.database_update_request_resp_version import DatabaseUpdateRequestRespVersion
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.database_alert_spec import DatabaseAlertSpec
    from ..models.database_backup_config import DatabaseBackupConfig
    from ..models.database_certificate_spec import DatabaseCertificateSpec
    from ..models.database_throughput_spec import DatabaseThroughputSpec
    from ..models.replica_of_spec import ReplicaOfSpec


T = TypeVar("T", bound="DatabaseUpdateRequest")


@_attrs_define
class DatabaseUpdateRequest:
    r"""Database update request

    Attributes:
        subscription_id (Union[Unset, int]):
        database_id (Union[Unset, int]):
        dry_run (Union[Unset, bool]): Optional. When 'false': Creates a deployment plan and deploys it, updating any
            resources required by the plan. When 'true': creates a read-only deployment plan and does not update any
            resources. Default: 'false'
        name (Union[Unset, str]): Optional. Updated database name. Example: Redis-database-example-updated.
        memory_limit_in_gb (Union[Unset, float]): Optional. Total memory in GB, including replication and other
            overhead. You cannot set both datasetSizeInGb and totalMemoryInGb. Example: 1.
        dataset_size_in_gb (Union[Unset, float]): Optional. The maximum amount of data in the dataset for this database
            in GB. You cannot set both datasetSizeInGb and totalMemoryInGb. If ‘replication’ is 'true', the database’s total
            memory will be twice as large as the datasetSizeInGb.If ‘replication’ is false, the database’s total memory will
            be the datasetSizeInGb value. Example: 1.
        resp_version (Union[Unset, DatabaseUpdateRequestRespVersion]): Optional. Redis Serialization Protocol version.
            Must be compatible with Redis version. Example: resp3.
        throughput_measurement (Union[Unset, DatabaseThroughputSpec]): Optional. Throughput measurement method.
        data_persistence (Union[Unset, DatabaseUpdateRequestDataPersistence]): Optional. Type and rate of data
            persistence in persistent storage.
        data_eviction_policy (Union[Unset, DatabaseUpdateRequestDataEvictionPolicy]): Optional. Data eviction policy.
        replication (Union[Unset, bool]): Optional. Turns database replication on or off.
        regex_rules (Union[Unset, list[str]]): Optional. Hashing policy Regex rules. Used only if 'shardingType' is
            'custom-regex-rules'.
        replica_of (Union[Unset, list[str]]): Optional. This database will be a replica of the specified Redis databases
            provided as one or more URI(s). Example: 'redis://user:password@host:port'. If the URI provided is a Redis Cloud
            database, only host and port should be provided. Example: ['redis://endpoint1:6379', 'redis://endpoint2:6380'].
        replica (Union[Unset, ReplicaOfSpec]): Optional. Changes Replica Of (also known as Active-Passive) configuration
            details.
        support_oss_cluster_api (Union[Unset, bool]): Optional. Support Redis [OSS Cluster
            API](https://redis.io/docs/latest/operate/rc/databases/configuration/clustering/#oss-cluster-api).
        use_external_endpoint_for_oss_cluster_api (Union[Unset, bool]): Optional. If set to 'true', the database will
            use the external endpoint for OSS Cluster API. This setting blocks the database's private endpoint. Can only be
            set if 'supportOSSClusterAPI' is 'true'.
        password (Union[Unset, str]): Optional. Changes the password used to access the database with the 'default'
            user. Can only be set if 'protocol' is 'redis'. Example: P@ssw0rd.
        sasl_username (Union[Unset, str]): Optional. Changes the Memcached (SASL) username to access the database. Can
            only be set if 'protocol' is 'memcached'. Example: mc-HR7gb.
        sasl_password (Union[Unset, str]): Optional. Changes the Memcached (SASL) password to access the database. Can
            only be set if 'protocol' is 'memcached'. Example: 7igza2WZ0UPgMyqjsxuIZtla8xBdzkJT.
        source_ip (Union[Unset, list[str]]): Optional. List of source IP addresses or subnet masks to allow. If
            specified, Redis clients will be able to connect to this database only from within the specified source IP
            addresses ranges. Example: '['192.168.10.0/32', '192.168.12.0/24']'
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
        enable_default_user (Union[Unset, bool]): Optional. When 'true', allows connecting to the database with the
            'default' user. When 'false', only defined access control users can connect to the database. Can only be set if
            'protocol' is 'redis'.
        periodic_backup_path (Union[Unset, str]): Optional. Changes the backup location path. If specified, the database
            will back up every 24 hours to this location, and you can manually back up the database to this location at any
            time. If set to an empty string, the backup path will be removed. Example: s3://<backup-path>.
        remote_backup (Union[Unset, DatabaseBackupConfig]): Optional. Changes Remote backup configuration details.
        alerts (Union[Unset, list['DatabaseAlertSpec']]): Optional. Changes Redis database alert details.
        command_type (Union[Unset, str]):
        query_performance_factor (Union[Unset, str]): Optional. Changes the query performance factor. The query
            performance factor adds extra compute power specifically for search and query databases. You can increase your
            queries per second by the selected factor. Example: 2x.
    """

    subscription_id: Union[Unset, int] = UNSET
    database_id: Union[Unset, int] = UNSET
    dry_run: Union[Unset, bool] = UNSET
    name: Union[Unset, str] = UNSET
    memory_limit_in_gb: Union[Unset, float] = UNSET
    dataset_size_in_gb: Union[Unset, float] = UNSET
    resp_version: Union[Unset, DatabaseUpdateRequestRespVersion] = UNSET
    throughput_measurement: Union[Unset, "DatabaseThroughputSpec"] = UNSET
    data_persistence: Union[Unset, DatabaseUpdateRequestDataPersistence] = UNSET
    data_eviction_policy: Union[Unset, DatabaseUpdateRequestDataEvictionPolicy] = UNSET
    replication: Union[Unset, bool] = UNSET
    regex_rules: Union[Unset, list[str]] = UNSET
    replica_of: Union[Unset, list[str]] = UNSET
    replica: Union[Unset, "ReplicaOfSpec"] = UNSET
    support_oss_cluster_api: Union[Unset, bool] = UNSET
    use_external_endpoint_for_oss_cluster_api: Union[Unset, bool] = UNSET
    password: Union[Unset, str] = UNSET
    sasl_username: Union[Unset, str] = UNSET
    sasl_password: Union[Unset, str] = UNSET
    source_ip: Union[Unset, list[str]] = UNSET
    client_ssl_certificate: Union[Unset, str] = UNSET
    client_tls_certificates: Union[Unset, list["DatabaseCertificateSpec"]] = UNSET
    enable_tls: Union[Unset, bool] = UNSET
    enable_default_user: Union[Unset, bool] = UNSET
    periodic_backup_path: Union[Unset, str] = UNSET
    remote_backup: Union[Unset, "DatabaseBackupConfig"] = UNSET
    alerts: Union[Unset, list["DatabaseAlertSpec"]] = UNSET
    command_type: Union[Unset, str] = UNSET
    query_performance_factor: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        database_id = self.database_id

        dry_run = self.dry_run

        name = self.name

        memory_limit_in_gb = self.memory_limit_in_gb

        dataset_size_in_gb = self.dataset_size_in_gb

        resp_version: Union[Unset, str] = UNSET
        if not isinstance(self.resp_version, Unset):
            resp_version = self.resp_version.value

        throughput_measurement: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.throughput_measurement, Unset):
            throughput_measurement = self.throughput_measurement.to_dict()

        data_persistence: Union[Unset, str] = UNSET
        if not isinstance(self.data_persistence, Unset):
            data_persistence = self.data_persistence.value

        data_eviction_policy: Union[Unset, str] = UNSET
        if not isinstance(self.data_eviction_policy, Unset):
            data_eviction_policy = self.data_eviction_policy.value

        replication = self.replication

        regex_rules: Union[Unset, list[str]] = UNSET
        if not isinstance(self.regex_rules, Unset):
            regex_rules = self.regex_rules

        replica_of: Union[Unset, list[str]] = UNSET
        if not isinstance(self.replica_of, Unset):
            replica_of = self.replica_of

        replica: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.replica, Unset):
            replica = self.replica.to_dict()

        support_oss_cluster_api = self.support_oss_cluster_api

        use_external_endpoint_for_oss_cluster_api = self.use_external_endpoint_for_oss_cluster_api

        password = self.password

        sasl_username = self.sasl_username

        sasl_password = self.sasl_password

        source_ip: Union[Unset, list[str]] = UNSET
        if not isinstance(self.source_ip, Unset):
            source_ip = self.source_ip

        client_ssl_certificate = self.client_ssl_certificate

        client_tls_certificates: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.client_tls_certificates, Unset):
            client_tls_certificates = []
            for client_tls_certificates_item_data in self.client_tls_certificates:
                client_tls_certificates_item = client_tls_certificates_item_data.to_dict()
                client_tls_certificates.append(client_tls_certificates_item)

        enable_tls = self.enable_tls

        enable_default_user = self.enable_default_user

        periodic_backup_path = self.periodic_backup_path

        remote_backup: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.remote_backup, Unset):
            remote_backup = self.remote_backup.to_dict()

        alerts: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.alerts, Unset):
            alerts = []
            for alerts_item_data in self.alerts:
                alerts_item = alerts_item_data.to_dict()
                alerts.append(alerts_item)

        command_type = self.command_type

        query_performance_factor = self.query_performance_factor

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if database_id is not UNSET:
            field_dict["databaseId"] = database_id
        if dry_run is not UNSET:
            field_dict["dryRun"] = dry_run
        if name is not UNSET:
            field_dict["name"] = name
        if memory_limit_in_gb is not UNSET:
            field_dict["memoryLimitInGb"] = memory_limit_in_gb
        if dataset_size_in_gb is not UNSET:
            field_dict["datasetSizeInGb"] = dataset_size_in_gb
        if resp_version is not UNSET:
            field_dict["respVersion"] = resp_version
        if throughput_measurement is not UNSET:
            field_dict["throughputMeasurement"] = throughput_measurement
        if data_persistence is not UNSET:
            field_dict["dataPersistence"] = data_persistence
        if data_eviction_policy is not UNSET:
            field_dict["dataEvictionPolicy"] = data_eviction_policy
        if replication is not UNSET:
            field_dict["replication"] = replication
        if regex_rules is not UNSET:
            field_dict["regexRules"] = regex_rules
        if replica_of is not UNSET:
            field_dict["replicaOf"] = replica_of
        if replica is not UNSET:
            field_dict["replica"] = replica
        if support_oss_cluster_api is not UNSET:
            field_dict["supportOSSClusterApi"] = support_oss_cluster_api
        if use_external_endpoint_for_oss_cluster_api is not UNSET:
            field_dict["useExternalEndpointForOSSClusterApi"] = use_external_endpoint_for_oss_cluster_api
        if password is not UNSET:
            field_dict["password"] = password
        if sasl_username is not UNSET:
            field_dict["saslUsername"] = sasl_username
        if sasl_password is not UNSET:
            field_dict["saslPassword"] = sasl_password
        if source_ip is not UNSET:
            field_dict["sourceIp"] = source_ip
        if client_ssl_certificate is not UNSET:
            field_dict["clientSslCertificate"] = client_ssl_certificate
        if client_tls_certificates is not UNSET:
            field_dict["clientTlsCertificates"] = client_tls_certificates
        if enable_tls is not UNSET:
            field_dict["enableTls"] = enable_tls
        if enable_default_user is not UNSET:
            field_dict["enableDefaultUser"] = enable_default_user
        if periodic_backup_path is not UNSET:
            field_dict["periodicBackupPath"] = periodic_backup_path
        if remote_backup is not UNSET:
            field_dict["remoteBackup"] = remote_backup
        if alerts is not UNSET:
            field_dict["alerts"] = alerts
        if command_type is not UNSET:
            field_dict["commandType"] = command_type
        if query_performance_factor is not UNSET:
            field_dict["queryPerformanceFactor"] = query_performance_factor

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.database_alert_spec import DatabaseAlertSpec
        from ..models.database_backup_config import DatabaseBackupConfig
        from ..models.database_certificate_spec import DatabaseCertificateSpec
        from ..models.database_throughput_spec import DatabaseThroughputSpec
        from ..models.replica_of_spec import ReplicaOfSpec

        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId", UNSET)

        database_id = d.pop("databaseId", UNSET)

        dry_run = d.pop("dryRun", UNSET)

        name = d.pop("name", UNSET)

        memory_limit_in_gb = d.pop("memoryLimitInGb", UNSET)

        dataset_size_in_gb = d.pop("datasetSizeInGb", UNSET)

        _resp_version = d.pop("respVersion", UNSET)
        resp_version: Union[Unset, DatabaseUpdateRequestRespVersion]
        if isinstance(_resp_version, Unset):
            resp_version = UNSET
        else:
            resp_version = DatabaseUpdateRequestRespVersion(_resp_version)

        _throughput_measurement = d.pop("throughputMeasurement", UNSET)
        throughput_measurement: Union[Unset, DatabaseThroughputSpec]
        if isinstance(_throughput_measurement, Unset):
            throughput_measurement = UNSET
        else:
            throughput_measurement = DatabaseThroughputSpec.from_dict(_throughput_measurement)

        _data_persistence = d.pop("dataPersistence", UNSET)
        data_persistence: Union[Unset, DatabaseUpdateRequestDataPersistence]
        if isinstance(_data_persistence, Unset):
            data_persistence = UNSET
        else:
            data_persistence = DatabaseUpdateRequestDataPersistence(_data_persistence)

        _data_eviction_policy = d.pop("dataEvictionPolicy", UNSET)
        data_eviction_policy: Union[Unset, DatabaseUpdateRequestDataEvictionPolicy]
        if isinstance(_data_eviction_policy, Unset):
            data_eviction_policy = UNSET
        else:
            data_eviction_policy = DatabaseUpdateRequestDataEvictionPolicy(_data_eviction_policy)

        replication = d.pop("replication", UNSET)

        regex_rules = cast(list[str], d.pop("regexRules", UNSET))

        replica_of = cast(list[str], d.pop("replicaOf", UNSET))

        _replica = d.pop("replica", UNSET)
        replica: Union[Unset, ReplicaOfSpec]
        if isinstance(_replica, Unset):
            replica = UNSET
        else:
            replica = ReplicaOfSpec.from_dict(_replica)

        support_oss_cluster_api = d.pop("supportOSSClusterApi", UNSET)

        use_external_endpoint_for_oss_cluster_api = d.pop("useExternalEndpointForOSSClusterApi", UNSET)

        password = d.pop("password", UNSET)

        sasl_username = d.pop("saslUsername", UNSET)

        sasl_password = d.pop("saslPassword", UNSET)

        source_ip = cast(list[str], d.pop("sourceIp", UNSET))

        client_ssl_certificate = d.pop("clientSslCertificate", UNSET)

        client_tls_certificates = []
        _client_tls_certificates = d.pop("clientTlsCertificates", UNSET)
        for client_tls_certificates_item_data in _client_tls_certificates or []:
            client_tls_certificates_item = DatabaseCertificateSpec.from_dict(client_tls_certificates_item_data)

            client_tls_certificates.append(client_tls_certificates_item)

        enable_tls = d.pop("enableTls", UNSET)

        enable_default_user = d.pop("enableDefaultUser", UNSET)

        periodic_backup_path = d.pop("periodicBackupPath", UNSET)

        _remote_backup = d.pop("remoteBackup", UNSET)
        remote_backup: Union[Unset, DatabaseBackupConfig]
        if isinstance(_remote_backup, Unset):
            remote_backup = UNSET
        else:
            remote_backup = DatabaseBackupConfig.from_dict(_remote_backup)

        alerts = []
        _alerts = d.pop("alerts", UNSET)
        for alerts_item_data in _alerts or []:
            alerts_item = DatabaseAlertSpec.from_dict(alerts_item_data)

            alerts.append(alerts_item)

        command_type = d.pop("commandType", UNSET)

        query_performance_factor = d.pop("queryPerformanceFactor", UNSET)

        database_update_request = cls(
            subscription_id=subscription_id,
            database_id=database_id,
            dry_run=dry_run,
            name=name,
            memory_limit_in_gb=memory_limit_in_gb,
            dataset_size_in_gb=dataset_size_in_gb,
            resp_version=resp_version,
            throughput_measurement=throughput_measurement,
            data_persistence=data_persistence,
            data_eviction_policy=data_eviction_policy,
            replication=replication,
            regex_rules=regex_rules,
            replica_of=replica_of,
            replica=replica,
            support_oss_cluster_api=support_oss_cluster_api,
            use_external_endpoint_for_oss_cluster_api=use_external_endpoint_for_oss_cluster_api,
            password=password,
            sasl_username=sasl_username,
            sasl_password=sasl_password,
            source_ip=source_ip,
            client_ssl_certificate=client_ssl_certificate,
            client_tls_certificates=client_tls_certificates,
            enable_tls=enable_tls,
            enable_default_user=enable_default_user,
            periodic_backup_path=periodic_backup_path,
            remote_backup=remote_backup,
            alerts=alerts,
            command_type=command_type,
            query_performance_factor=query_performance_factor,
        )

        database_update_request.additional_properties = d
        return database_update_request

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

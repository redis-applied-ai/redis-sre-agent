from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.database_create_request_data_eviction_policy import DatabaseCreateRequestDataEvictionPolicy
from ..models.database_create_request_data_persistence import DatabaseCreateRequestDataPersistence
from ..models.database_create_request_protocol import DatabaseCreateRequestProtocol
from ..models.database_create_request_resp_version import DatabaseCreateRequestRespVersion
from ..models.database_create_request_sharding_type import DatabaseCreateRequestShardingType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.database_alert_spec import DatabaseAlertSpec
    from ..models.database_backup_config import DatabaseBackupConfig
    from ..models.database_certificate_spec import DatabaseCertificateSpec
    from ..models.database_module_spec import DatabaseModuleSpec
    from ..models.database_throughput_spec import DatabaseThroughputSpec
    from ..models.local_throughput import LocalThroughput
    from ..models.replica_of_spec import ReplicaOfSpec


T = TypeVar("T", bound="DatabaseCreateRequest")


@_attrs_define
class DatabaseCreateRequest:
    r"""Database definition

    Attributes:
        name (str): Name of the database. Database name is limited to 40 characters or less and must include only
            letters, digits, and hyphens ('-'). It must start with a letter and end with a letter or digit. Example: Redis-
            database-example.
        subscription_id (Union[Unset, int]):
        dry_run (Union[Unset, bool]): Optional. When 'false': Creates a deployment plan and deploys it, creating any
            resources required by the plan. When 'true': creates a read-only deployment plan and does not create any
            resources. Default: 'false'
        protocol (Union[Unset, DatabaseCreateRequestProtocol]): Optional. Database protocol. Only set to 'memcached' if
            you have a legacy application. Default: 'redis'
        port (Union[Unset, int]): Optional. TCP port on which the database is available (10000-19999). Generated
            automatically if not set. Example: 10000.
        memory_limit_in_gb (Union[Unset, float]): Optional. Total memory in GB, including replication and other
            overhead. You cannot set both datasetSizeInGb and totalMemoryInGb. Example: 1.
        dataset_size_in_gb (Union[Unset, float]): Optional. The maximum amount of data in the dataset for this database
            in GB. You cannot set both datasetSizeInGb and totalMemoryInGb. If ‘replication’ is 'true', the database’s total
            memory will be twice as large as the datasetSizeInGb. If ‘replication’ is false, the database’s total memory
            will be the datasetSizeInGb value. Example: 1.
        redis_version (Union[Unset, str]): Optional. If specified, redisVersion defines the Redis database version. If
            omitted, the Redis version will be set to the default version (available in 'GET /subscriptions/redis-versions')
            Example: 7.2.
        resp_version (Union[Unset, DatabaseCreateRequestRespVersion]): Optional. Redis Serialization Protocol version.
            Must be compatible with Redis version. Example: resp3.
        support_oss_cluster_api (Union[Unset, bool]): Optional. Support [OSS Cluster
            API](https://redis.io/docs/latest/operate/rc/databases/configuration/clustering/#oss-cluster-api). Default:
            'false'
        use_external_endpoint_for_oss_cluster_api (Union[Unset, bool]): Optional. If set to 'true', the database will
            use the external endpoint for OSS Cluster API. This setting blocks the database's private endpoint. Can only be
            set if 'supportOSSClusterAPI' is 'true'. Default: 'false'
        data_persistence (Union[Unset, DatabaseCreateRequestDataPersistence]): Optional. Type and rate of data
            persistence in persistent storage. Default: 'none'
        data_eviction_policy (Union[Unset, DatabaseCreateRequestDataEvictionPolicy]): Optional. Data eviction policy.
            Default: 'volatile-lru'
        replication (Union[Unset, bool]): Optional. Sets database replication. Default: 'true'
        replica_of (Union[Unset, list[str]]): Optional. This database will be a replica of the specified Redis databases
            provided as one or more URI(s). Example: 'redis://user:password@host:port'. If the URI provided is a Redis Cloud
            database, only host and port should be provided. Example: ['redis://endpoint1:6379', 'redis://endpoint2:6380'].
        replica (Union[Unset, ReplicaOfSpec]): Optional. Changes Replica Of (also known as Active-Passive) configuration
            details.
        throughput_measurement (Union[Unset, DatabaseThroughputSpec]): Optional. Throughput measurement method.
        local_throughput_measurement (Union[Unset, list['LocalThroughput']]): Optional. Expected throughput per region
            for an Active-Active database. Default: 1000 read and write ops/sec for each region
        average_item_size_in_bytes (Union[Unset, int]): Optional. Relevant only to ram-and-flash (also known as Auto
            Tiering) subscriptions. Estimated average size in bytes of the items stored in the database. Default: 1000
        periodic_backup_path (Union[Unset, str]): Optional. The path to a backup storage location. If specified, the
            database will back up every 24 hours to this location, and you can manually back up the database to this
            location at any time. Example: s3://<backup-path>.
        remote_backup (Union[Unset, DatabaseBackupConfig]): Optional. Changes Remote backup configuration details.
        source_ip (Union[Unset, list[str]]): Optional. List of source IP addresses or subnet masks to allow. If
            specified, Redis clients will be able to connect to this database only from within the specified source IP
            addresses ranges. Example: '['192.168.10.0/32', '192.168.12.0/24']'
        client_ssl_certificate (Union[Unset, str]): Optional. A public key client TLS/SSL certificate with new line
            characters replaced with '\n'. If specified, mTLS authentication will be required to authenticate user
            connections. Default: 'null'
        client_tls_certificates (Union[Unset, list['DatabaseCertificateSpec']]): Optional. A list of client TLS/SSL
            certificates. If specified, mTLS authentication will be required to authenticate user connections.
        enable_tls (Union[Unset, bool]): Optional. When 'true', requires TLS authentication for all connections - mTLS
            with valid clientTlsCertificates, regular TLS when clientTlsCertificates is not provided. Default: 'false'
        password (Union[Unset, str]): Optional. Password to access the database. If not set, a random 32-character
            alphanumeric password will be automatically generated. Can only be set if 'protocol' is 'redis'.
        sasl_username (Union[Unset, str]): Optional. Memcached (SASL) Username to access the database. If not set, the
            username will be set to a 'mc-' prefix followed by a random 5 character long alphanumeric. Can only be set if
            'protocol' is 'memcached'.
        sasl_password (Union[Unset, str]): Optional. Memcached (SASL) Password to access the database. If not set, a
            random 32 character long alphanumeric password will be automatically generated. Can only be set if 'protocol' is
            'memcached'.
        alerts (Union[Unset, list['DatabaseAlertSpec']]): Optional. Redis database alert details.
        modules (Union[Unset, list['DatabaseModuleSpec']]): Optional. Redis advanced capabilities (also known as
            modules) to be provisioned in the database. Use GET /database-modules to get a list of available advanced
            capabilities.
        sharding_type (Union[Unset, DatabaseCreateRequestShardingType]): Optional. Database [Hashing
            policy](https://redis.io/docs/latest/operate/rc/databases/configuration/clustering/#manage-the-hashing-policy).
        command_type (Union[Unset, str]):
        query_performance_factor (Union[Unset, str]): Optional. The query performance factor adds extra compute power
            specifically for search and query databases. You can increase your queries per second by the selected factor.
            Example: 2x.
    """

    name: str
    subscription_id: Union[Unset, int] = UNSET
    dry_run: Union[Unset, bool] = UNSET
    protocol: Union[Unset, DatabaseCreateRequestProtocol] = UNSET
    port: Union[Unset, int] = UNSET
    memory_limit_in_gb: Union[Unset, float] = UNSET
    dataset_size_in_gb: Union[Unset, float] = UNSET
    redis_version: Union[Unset, str] = UNSET
    resp_version: Union[Unset, DatabaseCreateRequestRespVersion] = UNSET
    support_oss_cluster_api: Union[Unset, bool] = UNSET
    use_external_endpoint_for_oss_cluster_api: Union[Unset, bool] = UNSET
    data_persistence: Union[Unset, DatabaseCreateRequestDataPersistence] = UNSET
    data_eviction_policy: Union[Unset, DatabaseCreateRequestDataEvictionPolicy] = UNSET
    replication: Union[Unset, bool] = UNSET
    replica_of: Union[Unset, list[str]] = UNSET
    replica: Union[Unset, "ReplicaOfSpec"] = UNSET
    throughput_measurement: Union[Unset, "DatabaseThroughputSpec"] = UNSET
    local_throughput_measurement: Union[Unset, list["LocalThroughput"]] = UNSET
    average_item_size_in_bytes: Union[Unset, int] = UNSET
    periodic_backup_path: Union[Unset, str] = UNSET
    remote_backup: Union[Unset, "DatabaseBackupConfig"] = UNSET
    source_ip: Union[Unset, list[str]] = UNSET
    client_ssl_certificate: Union[Unset, str] = UNSET
    client_tls_certificates: Union[Unset, list["DatabaseCertificateSpec"]] = UNSET
    enable_tls: Union[Unset, bool] = UNSET
    password: Union[Unset, str] = UNSET
    sasl_username: Union[Unset, str] = UNSET
    sasl_password: Union[Unset, str] = UNSET
    alerts: Union[Unset, list["DatabaseAlertSpec"]] = UNSET
    modules: Union[Unset, list["DatabaseModuleSpec"]] = UNSET
    sharding_type: Union[Unset, DatabaseCreateRequestShardingType] = UNSET
    command_type: Union[Unset, str] = UNSET
    query_performance_factor: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        subscription_id = self.subscription_id

        dry_run = self.dry_run

        protocol: Union[Unset, str] = UNSET
        if not isinstance(self.protocol, Unset):
            protocol = self.protocol.value

        port = self.port

        memory_limit_in_gb = self.memory_limit_in_gb

        dataset_size_in_gb = self.dataset_size_in_gb

        redis_version = self.redis_version

        resp_version: Union[Unset, str] = UNSET
        if not isinstance(self.resp_version, Unset):
            resp_version = self.resp_version.value

        support_oss_cluster_api = self.support_oss_cluster_api

        use_external_endpoint_for_oss_cluster_api = self.use_external_endpoint_for_oss_cluster_api

        data_persistence: Union[Unset, str] = UNSET
        if not isinstance(self.data_persistence, Unset):
            data_persistence = self.data_persistence.value

        data_eviction_policy: Union[Unset, str] = UNSET
        if not isinstance(self.data_eviction_policy, Unset):
            data_eviction_policy = self.data_eviction_policy.value

        replication = self.replication

        replica_of: Union[Unset, list[str]] = UNSET
        if not isinstance(self.replica_of, Unset):
            replica_of = self.replica_of

        replica: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.replica, Unset):
            replica = self.replica.to_dict()

        throughput_measurement: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.throughput_measurement, Unset):
            throughput_measurement = self.throughput_measurement.to_dict()

        local_throughput_measurement: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.local_throughput_measurement, Unset):
            local_throughput_measurement = []
            for local_throughput_measurement_item_data in self.local_throughput_measurement:
                local_throughput_measurement_item = local_throughput_measurement_item_data.to_dict()
                local_throughput_measurement.append(local_throughput_measurement_item)

        average_item_size_in_bytes = self.average_item_size_in_bytes

        periodic_backup_path = self.periodic_backup_path

        remote_backup: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.remote_backup, Unset):
            remote_backup = self.remote_backup.to_dict()

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

        password = self.password

        sasl_username = self.sasl_username

        sasl_password = self.sasl_password

        alerts: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.alerts, Unset):
            alerts = []
            for alerts_item_data in self.alerts:
                alerts_item = alerts_item_data.to_dict()
                alerts.append(alerts_item)

        modules: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.modules, Unset):
            modules = []
            for modules_item_data in self.modules:
                modules_item = modules_item_data.to_dict()
                modules.append(modules_item)

        sharding_type: Union[Unset, str] = UNSET
        if not isinstance(self.sharding_type, Unset):
            sharding_type = self.sharding_type.value

        command_type = self.command_type

        query_performance_factor = self.query_performance_factor

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
            }
        )
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if dry_run is not UNSET:
            field_dict["dryRun"] = dry_run
        if protocol is not UNSET:
            field_dict["protocol"] = protocol
        if port is not UNSET:
            field_dict["port"] = port
        if memory_limit_in_gb is not UNSET:
            field_dict["memoryLimitInGb"] = memory_limit_in_gb
        if dataset_size_in_gb is not UNSET:
            field_dict["datasetSizeInGb"] = dataset_size_in_gb
        if redis_version is not UNSET:
            field_dict["redisVersion"] = redis_version
        if resp_version is not UNSET:
            field_dict["respVersion"] = resp_version
        if support_oss_cluster_api is not UNSET:
            field_dict["supportOSSClusterApi"] = support_oss_cluster_api
        if use_external_endpoint_for_oss_cluster_api is not UNSET:
            field_dict["useExternalEndpointForOSSClusterApi"] = use_external_endpoint_for_oss_cluster_api
        if data_persistence is not UNSET:
            field_dict["dataPersistence"] = data_persistence
        if data_eviction_policy is not UNSET:
            field_dict["dataEvictionPolicy"] = data_eviction_policy
        if replication is not UNSET:
            field_dict["replication"] = replication
        if replica_of is not UNSET:
            field_dict["replicaOf"] = replica_of
        if replica is not UNSET:
            field_dict["replica"] = replica
        if throughput_measurement is not UNSET:
            field_dict["throughputMeasurement"] = throughput_measurement
        if local_throughput_measurement is not UNSET:
            field_dict["localThroughputMeasurement"] = local_throughput_measurement
        if average_item_size_in_bytes is not UNSET:
            field_dict["averageItemSizeInBytes"] = average_item_size_in_bytes
        if periodic_backup_path is not UNSET:
            field_dict["periodicBackupPath"] = periodic_backup_path
        if remote_backup is not UNSET:
            field_dict["remoteBackup"] = remote_backup
        if source_ip is not UNSET:
            field_dict["sourceIp"] = source_ip
        if client_ssl_certificate is not UNSET:
            field_dict["clientSslCertificate"] = client_ssl_certificate
        if client_tls_certificates is not UNSET:
            field_dict["clientTlsCertificates"] = client_tls_certificates
        if enable_tls is not UNSET:
            field_dict["enableTls"] = enable_tls
        if password is not UNSET:
            field_dict["password"] = password
        if sasl_username is not UNSET:
            field_dict["saslUsername"] = sasl_username
        if sasl_password is not UNSET:
            field_dict["saslPassword"] = sasl_password
        if alerts is not UNSET:
            field_dict["alerts"] = alerts
        if modules is not UNSET:
            field_dict["modules"] = modules
        if sharding_type is not UNSET:
            field_dict["shardingType"] = sharding_type
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
        from ..models.database_module_spec import DatabaseModuleSpec
        from ..models.database_throughput_spec import DatabaseThroughputSpec
        from ..models.local_throughput import LocalThroughput
        from ..models.replica_of_spec import ReplicaOfSpec

        d = dict(src_dict)
        name = d.pop("name")

        subscription_id = d.pop("subscriptionId", UNSET)

        dry_run = d.pop("dryRun", UNSET)

        _protocol = d.pop("protocol", UNSET)
        protocol: Union[Unset, DatabaseCreateRequestProtocol]
        if isinstance(_protocol, Unset):
            protocol = UNSET
        else:
            protocol = DatabaseCreateRequestProtocol(_protocol)

        port = d.pop("port", UNSET)

        memory_limit_in_gb = d.pop("memoryLimitInGb", UNSET)

        dataset_size_in_gb = d.pop("datasetSizeInGb", UNSET)

        redis_version = d.pop("redisVersion", UNSET)

        _resp_version = d.pop("respVersion", UNSET)
        resp_version: Union[Unset, DatabaseCreateRequestRespVersion]
        if isinstance(_resp_version, Unset):
            resp_version = UNSET
        else:
            resp_version = DatabaseCreateRequestRespVersion(_resp_version)

        support_oss_cluster_api = d.pop("supportOSSClusterApi", UNSET)

        use_external_endpoint_for_oss_cluster_api = d.pop("useExternalEndpointForOSSClusterApi", UNSET)

        _data_persistence = d.pop("dataPersistence", UNSET)
        data_persistence: Union[Unset, DatabaseCreateRequestDataPersistence]
        if isinstance(_data_persistence, Unset):
            data_persistence = UNSET
        else:
            data_persistence = DatabaseCreateRequestDataPersistence(_data_persistence)

        _data_eviction_policy = d.pop("dataEvictionPolicy", UNSET)
        data_eviction_policy: Union[Unset, DatabaseCreateRequestDataEvictionPolicy]
        if isinstance(_data_eviction_policy, Unset):
            data_eviction_policy = UNSET
        else:
            data_eviction_policy = DatabaseCreateRequestDataEvictionPolicy(_data_eviction_policy)

        replication = d.pop("replication", UNSET)

        replica_of = cast(list[str], d.pop("replicaOf", UNSET))

        _replica = d.pop("replica", UNSET)
        replica: Union[Unset, ReplicaOfSpec]
        if isinstance(_replica, Unset):
            replica = UNSET
        else:
            replica = ReplicaOfSpec.from_dict(_replica)

        _throughput_measurement = d.pop("throughputMeasurement", UNSET)
        throughput_measurement: Union[Unset, DatabaseThroughputSpec]
        if isinstance(_throughput_measurement, Unset):
            throughput_measurement = UNSET
        else:
            throughput_measurement = DatabaseThroughputSpec.from_dict(_throughput_measurement)

        local_throughput_measurement = []
        _local_throughput_measurement = d.pop("localThroughputMeasurement", UNSET)
        for local_throughput_measurement_item_data in _local_throughput_measurement or []:
            local_throughput_measurement_item = LocalThroughput.from_dict(local_throughput_measurement_item_data)

            local_throughput_measurement.append(local_throughput_measurement_item)

        average_item_size_in_bytes = d.pop("averageItemSizeInBytes", UNSET)

        periodic_backup_path = d.pop("periodicBackupPath", UNSET)

        _remote_backup = d.pop("remoteBackup", UNSET)
        remote_backup: Union[Unset, DatabaseBackupConfig]
        if isinstance(_remote_backup, Unset):
            remote_backup = UNSET
        else:
            remote_backup = DatabaseBackupConfig.from_dict(_remote_backup)

        source_ip = cast(list[str], d.pop("sourceIp", UNSET))

        client_ssl_certificate = d.pop("clientSslCertificate", UNSET)

        client_tls_certificates = []
        _client_tls_certificates = d.pop("clientTlsCertificates", UNSET)
        for client_tls_certificates_item_data in _client_tls_certificates or []:
            client_tls_certificates_item = DatabaseCertificateSpec.from_dict(client_tls_certificates_item_data)

            client_tls_certificates.append(client_tls_certificates_item)

        enable_tls = d.pop("enableTls", UNSET)

        password = d.pop("password", UNSET)

        sasl_username = d.pop("saslUsername", UNSET)

        sasl_password = d.pop("saslPassword", UNSET)

        alerts = []
        _alerts = d.pop("alerts", UNSET)
        for alerts_item_data in _alerts or []:
            alerts_item = DatabaseAlertSpec.from_dict(alerts_item_data)

            alerts.append(alerts_item)

        modules = []
        _modules = d.pop("modules", UNSET)
        for modules_item_data in _modules or []:
            modules_item = DatabaseModuleSpec.from_dict(modules_item_data)

            modules.append(modules_item)

        _sharding_type = d.pop("shardingType", UNSET)
        sharding_type: Union[Unset, DatabaseCreateRequestShardingType]
        if isinstance(_sharding_type, Unset):
            sharding_type = UNSET
        else:
            sharding_type = DatabaseCreateRequestShardingType(_sharding_type)

        command_type = d.pop("commandType", UNSET)

        query_performance_factor = d.pop("queryPerformanceFactor", UNSET)

        database_create_request = cls(
            name=name,
            subscription_id=subscription_id,
            dry_run=dry_run,
            protocol=protocol,
            port=port,
            memory_limit_in_gb=memory_limit_in_gb,
            dataset_size_in_gb=dataset_size_in_gb,
            redis_version=redis_version,
            resp_version=resp_version,
            support_oss_cluster_api=support_oss_cluster_api,
            use_external_endpoint_for_oss_cluster_api=use_external_endpoint_for_oss_cluster_api,
            data_persistence=data_persistence,
            data_eviction_policy=data_eviction_policy,
            replication=replication,
            replica_of=replica_of,
            replica=replica,
            throughput_measurement=throughput_measurement,
            local_throughput_measurement=local_throughput_measurement,
            average_item_size_in_bytes=average_item_size_in_bytes,
            periodic_backup_path=periodic_backup_path,
            remote_backup=remote_backup,
            source_ip=source_ip,
            client_ssl_certificate=client_ssl_certificate,
            client_tls_certificates=client_tls_certificates,
            enable_tls=enable_tls,
            password=password,
            sasl_username=sasl_username,
            sasl_password=sasl_password,
            alerts=alerts,
            modules=modules,
            sharding_type=sharding_type,
            command_type=command_type,
            query_performance_factor=query_performance_factor,
        )

        database_create_request.additional_properties = d
        return database_create_request

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

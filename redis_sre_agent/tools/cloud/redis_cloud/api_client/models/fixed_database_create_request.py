from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.fixed_database_create_request_data_eviction_policy import FixedDatabaseCreateRequestDataEvictionPolicy
from ..models.fixed_database_create_request_data_persistence import FixedDatabaseCreateRequestDataPersistence
from ..models.fixed_database_create_request_protocol import FixedDatabaseCreateRequestProtocol
from ..models.fixed_database_create_request_resp_version import FixedDatabaseCreateRequestRespVersion
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.database_alert_spec import DatabaseAlertSpec
    from ..models.database_certificate_spec import DatabaseCertificateSpec
    from ..models.database_module_spec import DatabaseModuleSpec
    from ..models.replica_of_spec import ReplicaOfSpec


T = TypeVar("T", bound="FixedDatabaseCreateRequest")


@_attrs_define
class FixedDatabaseCreateRequest:
    r"""Essentials database definition

    Attributes:
        name (str): Name of the database. Database name is limited to 40 characters or less and must include only
            letters, digits, and hyphens ('-'). It must start with a letter and end with a letter or digit. Example: Redis-
            Essentials-database-example.
        subscription_id (Union[Unset, int]):
        protocol (Union[Unset, FixedDatabaseCreateRequestProtocol]): Optional. Database protocol. Use 'stack' to get all
            of Redis' advanced capabilities. Only use 'redis' for Pay-as-you-go or Redis Flex subscriptions. Default:
            'stack' for most subscriptions, 'redis' for Redis Flex subscriptions.
        memory_limit_in_gb (Union[Unset, float]): (Pay-as-you-go subscriptions only) Optional. Total memory in GB,
            including replication and other overhead. You cannot set both datasetSizeInGb and totalMemoryInGb. Example: 1.
        dataset_size_in_gb (Union[Unset, float]): (Pay-as-you-go subscriptions only) Optional. The maximum amount of
            data in the dataset for this database in GB. You cannot set both datasetSizeInGb and totalMemoryInGb. If
            ‘replication’ is 'true', the database’s total memory will be twice as large as the datasetSizeInGb. If
            ‘replication’ is false, the database’s total memory will be the datasetSizeInGb value. Example: 1.
        support_oss_cluster_api (Union[Unset, bool]): (Pay-as-you-go subscriptions only) Optional. Support Redis [OSS
            Cluster API](https://redis.io/docs/latest/operate/rc/databases/configuration/clustering/#oss-cluster-api).
            Default: 'false' Example: True.
        redis_version (Union[Unset, str]): Optional. If specified, redisVersion defines the Redis database version. If
            omitted, the Redis version will be set to the default version.  (available in 'GET /fixed/redis-versions')
            Example: 7.4.
        resp_version (Union[Unset, FixedDatabaseCreateRequestRespVersion]): Optional. Redis Serialization Protocol
            version. Must be compatible with Redis version. Example: resp3.
        use_external_endpoint_for_oss_cluster_api (Union[Unset, bool]): (Pay-as-you-go subscriptions only) Optional. If
            set to 'true', the database will use the external endpoint for OSS Cluster API. This setting blocks the
            database's private endpoint. Can only be set if 'supportOSSClusterAPI' is 'true'. Default: 'false' Example:
            True.
        enable_database_clustering (Union[Unset, bool]): (Pay-as-you-go subscriptions only) Optional. Distributes
            database data to different cloud instances. Default: 'false'
        number_of_shards (Union[Unset, int]): (Pay-as-you-go subscriptions only) Optional. Specifies the number of
            master shards. Example: 2.
        data_persistence (Union[Unset, FixedDatabaseCreateRequestDataPersistence]): Optional. Type and rate of data
            persistence in persistent storage. Use GET /fixed/plans/{planId} to see if your plan supports data persistence.
        data_eviction_policy (Union[Unset, FixedDatabaseCreateRequestDataEvictionPolicy]): Optional. Data eviction
            policy.
        replication (Union[Unset, bool]): Optional. Sets database replication. Use GET /fixed/plans/{planId} to see if
            your plan supports database replication.
        periodic_backup_path (Union[Unset, str]): Optional. The path to a backup storage location. If specified, the
            database will back up every 24 hours to this location, and you can manually back up the database to this
            location at any time. Use GET /fixed/plans/{planId} to see if your plan supports database backups. Example:
            s3://<backup-path>.
        source_ips (Union[Unset, list[str]]): Optional. List of source IP addresses or subnet masks to allow. If
            specified, Redis clients will be able to connect to this database only from within the specified source IP
            addresses ranges. Use GET /fixed/plans/{planId} to see how many CIDR allow rules your plan supports. Example:
            '['192.168.10.0/32', '192.168.12.0/24']'
        regex_rules (Union[Unset, list[str]]): (Pay-as-you-go subscriptions only) Optional. Hashing policy Regex rules.
            Used only if 'enableDatabaseClustering' is set to 'true' and .
        replica_of (Union[Unset, list[str]]): Optional. This database will be a replica of the specified Redis databases
            provided as one or more URI(s). Example: 'redis://user:password@host:port'. If the URI provided is a Redis Cloud
            database, only host and port should be provided. Example: ['redis://endpoint1:6379', 'redis://endpoint2:6380'].
        replica (Union[Unset, ReplicaOfSpec]): Optional. Changes Replica Of (also known as Active-Passive) configuration
            details.
        client_ssl_certificate (Union[Unset, str]): Optional. A public key client TLS/SSL certificate with new line
            characters replaced with '\n'. If specified, mTLS authentication will be required to authenticate user
            connections. Default: 'null'
        client_tls_certificates (Union[Unset, list['DatabaseCertificateSpec']]): Optional. A list of client TLS/SSL
            certificates. If specified, mTLS authentication will be required to authenticate user connections.
        enable_tls (Union[Unset, bool]): Optional. When 'true', requires TLS authentication for all connections - mTLS
            with valid clientTlsCertificates, regular TLS when clientTlsCertificates is not provided. Default: 'false'
        password (Union[Unset, str]): Optional. Password to access the database. If not set, a random 32-character
            alphanumeric password will be automatically generated.
        alerts (Union[Unset, list['DatabaseAlertSpec']]): Optional. Redis database alert details.
        modules (Union[Unset, list['DatabaseModuleSpec']]): Optional. Redis advanced capabilities (also known as
            modules) to be provisioned in the database. Use GET /database-modules to get a list of available advanced
            capabilities. Can only be set if 'protocol' is 'redis'.
        command_type (Union[Unset, str]):
    """

    name: str
    subscription_id: Union[Unset, int] = UNSET
    protocol: Union[Unset, FixedDatabaseCreateRequestProtocol] = UNSET
    memory_limit_in_gb: Union[Unset, float] = UNSET
    dataset_size_in_gb: Union[Unset, float] = UNSET
    support_oss_cluster_api: Union[Unset, bool] = UNSET
    redis_version: Union[Unset, str] = UNSET
    resp_version: Union[Unset, FixedDatabaseCreateRequestRespVersion] = UNSET
    use_external_endpoint_for_oss_cluster_api: Union[Unset, bool] = UNSET
    enable_database_clustering: Union[Unset, bool] = UNSET
    number_of_shards: Union[Unset, int] = UNSET
    data_persistence: Union[Unset, FixedDatabaseCreateRequestDataPersistence] = UNSET
    data_eviction_policy: Union[Unset, FixedDatabaseCreateRequestDataEvictionPolicy] = UNSET
    replication: Union[Unset, bool] = UNSET
    periodic_backup_path: Union[Unset, str] = UNSET
    source_ips: Union[Unset, list[str]] = UNSET
    regex_rules: Union[Unset, list[str]] = UNSET
    replica_of: Union[Unset, list[str]] = UNSET
    replica: Union[Unset, "ReplicaOfSpec"] = UNSET
    client_ssl_certificate: Union[Unset, str] = UNSET
    client_tls_certificates: Union[Unset, list["DatabaseCertificateSpec"]] = UNSET
    enable_tls: Union[Unset, bool] = UNSET
    password: Union[Unset, str] = UNSET
    alerts: Union[Unset, list["DatabaseAlertSpec"]] = UNSET
    modules: Union[Unset, list["DatabaseModuleSpec"]] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        subscription_id = self.subscription_id

        protocol: Union[Unset, str] = UNSET
        if not isinstance(self.protocol, Unset):
            protocol = self.protocol.value

        memory_limit_in_gb = self.memory_limit_in_gb

        dataset_size_in_gb = self.dataset_size_in_gb

        support_oss_cluster_api = self.support_oss_cluster_api

        redis_version = self.redis_version

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

        regex_rules: Union[Unset, list[str]] = UNSET
        if not isinstance(self.regex_rules, Unset):
            regex_rules = self.regex_rules

        replica_of: Union[Unset, list[str]] = UNSET
        if not isinstance(self.replica_of, Unset):
            replica_of = self.replica_of

        replica: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.replica, Unset):
            replica = self.replica.to_dict()

        client_ssl_certificate = self.client_ssl_certificate

        client_tls_certificates: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.client_tls_certificates, Unset):
            client_tls_certificates = []
            for client_tls_certificates_item_data in self.client_tls_certificates:
                client_tls_certificates_item = client_tls_certificates_item_data.to_dict()
                client_tls_certificates.append(client_tls_certificates_item)

        enable_tls = self.enable_tls

        password = self.password

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

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
            }
        )
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if protocol is not UNSET:
            field_dict["protocol"] = protocol
        if memory_limit_in_gb is not UNSET:
            field_dict["memoryLimitInGb"] = memory_limit_in_gb
        if dataset_size_in_gb is not UNSET:
            field_dict["datasetSizeInGb"] = dataset_size_in_gb
        if support_oss_cluster_api is not UNSET:
            field_dict["supportOSSClusterApi"] = support_oss_cluster_api
        if redis_version is not UNSET:
            field_dict["redisVersion"] = redis_version
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
        if regex_rules is not UNSET:
            field_dict["regexRules"] = regex_rules
        if replica_of is not UNSET:
            field_dict["replicaOf"] = replica_of
        if replica is not UNSET:
            field_dict["replica"] = replica
        if client_ssl_certificate is not UNSET:
            field_dict["clientSslCertificate"] = client_ssl_certificate
        if client_tls_certificates is not UNSET:
            field_dict["clientTlsCertificates"] = client_tls_certificates
        if enable_tls is not UNSET:
            field_dict["enableTls"] = enable_tls
        if password is not UNSET:
            field_dict["password"] = password
        if alerts is not UNSET:
            field_dict["alerts"] = alerts
        if modules is not UNSET:
            field_dict["modules"] = modules
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.database_alert_spec import DatabaseAlertSpec
        from ..models.database_certificate_spec import DatabaseCertificateSpec
        from ..models.database_module_spec import DatabaseModuleSpec
        from ..models.replica_of_spec import ReplicaOfSpec

        d = dict(src_dict)
        name = d.pop("name")

        subscription_id = d.pop("subscriptionId", UNSET)

        _protocol = d.pop("protocol", UNSET)
        protocol: Union[Unset, FixedDatabaseCreateRequestProtocol]
        if isinstance(_protocol, Unset):
            protocol = UNSET
        else:
            protocol = FixedDatabaseCreateRequestProtocol(_protocol)

        memory_limit_in_gb = d.pop("memoryLimitInGb", UNSET)

        dataset_size_in_gb = d.pop("datasetSizeInGb", UNSET)

        support_oss_cluster_api = d.pop("supportOSSClusterApi", UNSET)

        redis_version = d.pop("redisVersion", UNSET)

        _resp_version = d.pop("respVersion", UNSET)
        resp_version: Union[Unset, FixedDatabaseCreateRequestRespVersion]
        if isinstance(_resp_version, Unset):
            resp_version = UNSET
        else:
            resp_version = FixedDatabaseCreateRequestRespVersion(_resp_version)

        use_external_endpoint_for_oss_cluster_api = d.pop("useExternalEndpointForOSSClusterApi", UNSET)

        enable_database_clustering = d.pop("enableDatabaseClustering", UNSET)

        number_of_shards = d.pop("numberOfShards", UNSET)

        _data_persistence = d.pop("dataPersistence", UNSET)
        data_persistence: Union[Unset, FixedDatabaseCreateRequestDataPersistence]
        if isinstance(_data_persistence, Unset):
            data_persistence = UNSET
        else:
            data_persistence = FixedDatabaseCreateRequestDataPersistence(_data_persistence)

        _data_eviction_policy = d.pop("dataEvictionPolicy", UNSET)
        data_eviction_policy: Union[Unset, FixedDatabaseCreateRequestDataEvictionPolicy]
        if isinstance(_data_eviction_policy, Unset):
            data_eviction_policy = UNSET
        else:
            data_eviction_policy = FixedDatabaseCreateRequestDataEvictionPolicy(_data_eviction_policy)

        replication = d.pop("replication", UNSET)

        periodic_backup_path = d.pop("periodicBackupPath", UNSET)

        source_ips = cast(list[str], d.pop("sourceIps", UNSET))

        regex_rules = cast(list[str], d.pop("regexRules", UNSET))

        replica_of = cast(list[str], d.pop("replicaOf", UNSET))

        _replica = d.pop("replica", UNSET)
        replica: Union[Unset, ReplicaOfSpec]
        if isinstance(_replica, Unset):
            replica = UNSET
        else:
            replica = ReplicaOfSpec.from_dict(_replica)

        client_ssl_certificate = d.pop("clientSslCertificate", UNSET)

        client_tls_certificates = []
        _client_tls_certificates = d.pop("clientTlsCertificates", UNSET)
        for client_tls_certificates_item_data in _client_tls_certificates or []:
            client_tls_certificates_item = DatabaseCertificateSpec.from_dict(client_tls_certificates_item_data)

            client_tls_certificates.append(client_tls_certificates_item)

        enable_tls = d.pop("enableTls", UNSET)

        password = d.pop("password", UNSET)

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

        command_type = d.pop("commandType", UNSET)

        fixed_database_create_request = cls(
            name=name,
            subscription_id=subscription_id,
            protocol=protocol,
            memory_limit_in_gb=memory_limit_in_gb,
            dataset_size_in_gb=dataset_size_in_gb,
            support_oss_cluster_api=support_oss_cluster_api,
            redis_version=redis_version,
            resp_version=resp_version,
            use_external_endpoint_for_oss_cluster_api=use_external_endpoint_for_oss_cluster_api,
            enable_database_clustering=enable_database_clustering,
            number_of_shards=number_of_shards,
            data_persistence=data_persistence,
            data_eviction_policy=data_eviction_policy,
            replication=replication,
            periodic_backup_path=periodic_backup_path,
            source_ips=source_ips,
            regex_rules=regex_rules,
            replica_of=replica_of,
            replica=replica,
            client_ssl_certificate=client_ssl_certificate,
            client_tls_certificates=client_tls_certificates,
            enable_tls=enable_tls,
            password=password,
            alerts=alerts,
            modules=modules,
            command_type=command_type,
        )

        fixed_database_create_request.additional_properties = d
        return fixed_database_create_request

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

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.subscription_database_spec_data_persistence import SubscriptionDatabaseSpecDataPersistence
from ..models.subscription_database_spec_protocol import SubscriptionDatabaseSpecProtocol
from ..models.subscription_database_spec_resp_version import SubscriptionDatabaseSpecRespVersion
from ..models.subscription_database_spec_sharding_type import SubscriptionDatabaseSpecShardingType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.database_module_spec import DatabaseModuleSpec
    from ..models.database_throughput_spec import DatabaseThroughputSpec
    from ..models.local_throughput import LocalThroughput


T = TypeVar("T", bound="SubscriptionDatabaseSpec")


@_attrs_define
class SubscriptionDatabaseSpec:
    """One or more database specification(s) to create in this subscription.

    Attributes:
        name (str): Name of the database. Database name is limited to 40 characters or less and must include only
            letters, digits, and hyphens ('-'). It must start with a letter and end with a letter or digit. Example: Redis-
            database-example.
        protocol (SubscriptionDatabaseSpecProtocol): Optional. Database protocol. Only set to 'memcached' if you have a
            legacy application. Default: 'redis'
        port (Union[Unset, int]): Optional. TCP port on which the database is available (10000-19999). Generated
            automatically if not set. Example: 10000.
        memory_limit_in_gb (Union[Unset, float]): Optional. Total memory in GB, including replication and other
            overhead. You cannot set both datasetSizeInGb and totalMemoryInGb. Example: 1.
        dataset_size_in_gb (Union[Unset, float]): Optional. The maximum amount of data in the dataset for this database
            in GB. You cannot set both datasetSizeInGb and totalMemoryInGb. If ‘replication’ is 'true', the database’s total
            memory will be twice as large as the datasetSizeInGb.If ‘replication’ is false, the database’s total memory will
            be the datasetSizeInGb value. Example: 1.
        support_oss_cluster_api (Union[Unset, bool]): Optional. Support Redis [OSS Cluster
            API](https://redis.io/docs/latest/operate/rc/databases/configuration/clustering/#oss-cluster-api). Default:
            'false'
        data_persistence (Union[Unset, SubscriptionDatabaseSpecDataPersistence]): Optional. Type and rate of data
            persistence in persistent storage. Default: 'none'
        replication (Union[Unset, bool]): Optional. Databases replication. Default: 'true'
        throughput_measurement (Union[Unset, DatabaseThroughputSpec]): Optional. Throughput measurement method.
        local_throughput_measurement (Union[Unset, list['LocalThroughput']]): Optional. Expected throughput per region
            for an Active-Active database. Default: 1000 read and write ops/sec for each region
        modules (Union[Unset, list['DatabaseModuleSpec']]): Optional. Redis advanced capabilities (also known as
            modules) to be provisioned in the database. Use GET /database-modules to get a list of available advanced
            capabilities.
        quantity (Union[Unset, int]): Optional. Number of databases that will be created with these settings. Default: 1
            Example: 1.
        average_item_size_in_bytes (Union[Unset, int]): Optional. Relevant only to ram-and-flash (also known as Auto
            Tiering) subscriptions. Estimated average size in bytes of the items stored in the database. Default: 1000
        resp_version (Union[Unset, SubscriptionDatabaseSpecRespVersion]): Optional. Redis Serialization Protocol
            version. Must be compatible with Redis version. Example: resp3.
        redis_version (Union[Unset, str]): Optional. If specified, redisVersion defines the Redis database version. If
            omitted, the Redis version will be set to the default version (available in 'GET /subscriptions/redis-versions')
            Example: 7.2.
        sharding_type (Union[Unset, SubscriptionDatabaseSpecShardingType]): Optional. Database [Hashing
            policy](https://redis.io/docs/latest/operate/rc/databases/configuration/clustering/#manage-the-hashing-policy).
        query_performance_factor (Union[Unset, str]): Optional. The query performance factor adds extra compute power
            specifically for search and query databases. You can increase your queries per second by the selected factor.
            Example: 2x.
    """

    name: str
    protocol: SubscriptionDatabaseSpecProtocol
    port: Union[Unset, int] = UNSET
    memory_limit_in_gb: Union[Unset, float] = UNSET
    dataset_size_in_gb: Union[Unset, float] = UNSET
    support_oss_cluster_api: Union[Unset, bool] = UNSET
    data_persistence: Union[Unset, SubscriptionDatabaseSpecDataPersistence] = UNSET
    replication: Union[Unset, bool] = UNSET
    throughput_measurement: Union[Unset, "DatabaseThroughputSpec"] = UNSET
    local_throughput_measurement: Union[Unset, list["LocalThroughput"]] = UNSET
    modules: Union[Unset, list["DatabaseModuleSpec"]] = UNSET
    quantity: Union[Unset, int] = UNSET
    average_item_size_in_bytes: Union[Unset, int] = UNSET
    resp_version: Union[Unset, SubscriptionDatabaseSpecRespVersion] = UNSET
    redis_version: Union[Unset, str] = UNSET
    sharding_type: Union[Unset, SubscriptionDatabaseSpecShardingType] = UNSET
    query_performance_factor: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        protocol = self.protocol.value

        port = self.port

        memory_limit_in_gb = self.memory_limit_in_gb

        dataset_size_in_gb = self.dataset_size_in_gb

        support_oss_cluster_api = self.support_oss_cluster_api

        data_persistence: Union[Unset, str] = UNSET
        if not isinstance(self.data_persistence, Unset):
            data_persistence = self.data_persistence.value

        replication = self.replication

        throughput_measurement: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.throughput_measurement, Unset):
            throughput_measurement = self.throughput_measurement.to_dict()

        local_throughput_measurement: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.local_throughput_measurement, Unset):
            local_throughput_measurement = []
            for local_throughput_measurement_item_data in self.local_throughput_measurement:
                local_throughput_measurement_item = local_throughput_measurement_item_data.to_dict()
                local_throughput_measurement.append(local_throughput_measurement_item)

        modules: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.modules, Unset):
            modules = []
            for modules_item_data in self.modules:
                modules_item = modules_item_data.to_dict()
                modules.append(modules_item)

        quantity = self.quantity

        average_item_size_in_bytes = self.average_item_size_in_bytes

        resp_version: Union[Unset, str] = UNSET
        if not isinstance(self.resp_version, Unset):
            resp_version = self.resp_version.value

        redis_version = self.redis_version

        sharding_type: Union[Unset, str] = UNSET
        if not isinstance(self.sharding_type, Unset):
            sharding_type = self.sharding_type.value

        query_performance_factor = self.query_performance_factor

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "protocol": protocol,
            }
        )
        if port is not UNSET:
            field_dict["port"] = port
        if memory_limit_in_gb is not UNSET:
            field_dict["memoryLimitInGb"] = memory_limit_in_gb
        if dataset_size_in_gb is not UNSET:
            field_dict["datasetSizeInGb"] = dataset_size_in_gb
        if support_oss_cluster_api is not UNSET:
            field_dict["supportOSSClusterApi"] = support_oss_cluster_api
        if data_persistence is not UNSET:
            field_dict["dataPersistence"] = data_persistence
        if replication is not UNSET:
            field_dict["replication"] = replication
        if throughput_measurement is not UNSET:
            field_dict["throughputMeasurement"] = throughput_measurement
        if local_throughput_measurement is not UNSET:
            field_dict["localThroughputMeasurement"] = local_throughput_measurement
        if modules is not UNSET:
            field_dict["modules"] = modules
        if quantity is not UNSET:
            field_dict["quantity"] = quantity
        if average_item_size_in_bytes is not UNSET:
            field_dict["averageItemSizeInBytes"] = average_item_size_in_bytes
        if resp_version is not UNSET:
            field_dict["respVersion"] = resp_version
        if redis_version is not UNSET:
            field_dict["redisVersion"] = redis_version
        if sharding_type is not UNSET:
            field_dict["shardingType"] = sharding_type
        if query_performance_factor is not UNSET:
            field_dict["queryPerformanceFactor"] = query_performance_factor

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.database_module_spec import DatabaseModuleSpec
        from ..models.database_throughput_spec import DatabaseThroughputSpec
        from ..models.local_throughput import LocalThroughput

        d = dict(src_dict)
        name = d.pop("name")

        protocol = SubscriptionDatabaseSpecProtocol(d.pop("protocol"))

        port = d.pop("port", UNSET)

        memory_limit_in_gb = d.pop("memoryLimitInGb", UNSET)

        dataset_size_in_gb = d.pop("datasetSizeInGb", UNSET)

        support_oss_cluster_api = d.pop("supportOSSClusterApi", UNSET)

        _data_persistence = d.pop("dataPersistence", UNSET)
        data_persistence: Union[Unset, SubscriptionDatabaseSpecDataPersistence]
        if isinstance(_data_persistence, Unset):
            data_persistence = UNSET
        else:
            data_persistence = SubscriptionDatabaseSpecDataPersistence(_data_persistence)

        replication = d.pop("replication", UNSET)

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

        modules = []
        _modules = d.pop("modules", UNSET)
        for modules_item_data in _modules or []:
            modules_item = DatabaseModuleSpec.from_dict(modules_item_data)

            modules.append(modules_item)

        quantity = d.pop("quantity", UNSET)

        average_item_size_in_bytes = d.pop("averageItemSizeInBytes", UNSET)

        _resp_version = d.pop("respVersion", UNSET)
        resp_version: Union[Unset, SubscriptionDatabaseSpecRespVersion]
        if isinstance(_resp_version, Unset):
            resp_version = UNSET
        else:
            resp_version = SubscriptionDatabaseSpecRespVersion(_resp_version)

        redis_version = d.pop("redisVersion", UNSET)

        _sharding_type = d.pop("shardingType", UNSET)
        sharding_type: Union[Unset, SubscriptionDatabaseSpecShardingType]
        if isinstance(_sharding_type, Unset):
            sharding_type = UNSET
        else:
            sharding_type = SubscriptionDatabaseSpecShardingType(_sharding_type)

        query_performance_factor = d.pop("queryPerformanceFactor", UNSET)

        subscription_database_spec = cls(
            name=name,
            protocol=protocol,
            port=port,
            memory_limit_in_gb=memory_limit_in_gb,
            dataset_size_in_gb=dataset_size_in_gb,
            support_oss_cluster_api=support_oss_cluster_api,
            data_persistence=data_persistence,
            replication=replication,
            throughput_measurement=throughput_measurement,
            local_throughput_measurement=local_throughput_measurement,
            modules=modules,
            quantity=quantity,
            average_item_size_in_bytes=average_item_size_in_bytes,
            resp_version=resp_version,
            redis_version=redis_version,
            sharding_type=sharding_type,
            query_performance_factor=query_performance_factor,
        )

        subscription_database_spec.additional_properties = d
        return subscription_database_spec

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

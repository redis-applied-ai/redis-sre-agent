import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.fixed_database_data_eviction_policy import FixedDatabaseDataEvictionPolicy
from ..models.fixed_database_data_persistence import FixedDatabaseDataPersistence
from ..models.fixed_database_memory_storage import FixedDatabaseMemoryStorage
from ..models.fixed_database_protocol import FixedDatabaseProtocol
from ..models.fixed_database_resp_version import FixedDatabaseRespVersion
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.dynamic_endpoints import DynamicEndpoints
    from ..models.fixed_database_links_item import FixedDatabaseLinksItem


T = TypeVar("T", bound="FixedDatabase")


@_attrs_define
class FixedDatabase:
    r"""
    Example:
        {'databaseId': 51324587, 'name': 'bdb', 'protocol': 'stack', 'provider': 'AWS', 'region': 'us-east-1', 'status':
            'draft', 'planMemoryLimit': 250, 'respVersion': 'resp2', 'memoryLimitMeasurementUnit': 'MB', 'memoryUsedInMb':
            7, 'memoryStorage': 'ram', 'dataPersistence': 'none', 'replication': True, 'dataEvictionPolicy': 'noeviction',
            'clustering': {'enabled': False, 'regexRules': [{'ordinal': 0, 'pattern': '.*\\{(?<tag>.*)\\}.*'}, {'ordinal':
            1, 'pattern': '(?<tag>.*)'}], 'hashingPolicy': 'standard'}, 'security': {'defaultUserEnabled': True, 'password':
            'myCustomPassword', 'sourceIps': ['0.0.0.0/0']}, 'modules': [{'id': 18534, 'name': 'RediSearch',
            'capabilityName': 'Search and query', 'version': '2.2.6', 'description': 'A comprehensive, expressive, flexible,
            fast and developer-friendly search and query engine for the diversity of data types in Redis with state-of-the-
            art scoring algorithms', 'parameters': []}, {'id': 18535, 'name': 'RedisBloom', 'capabilityName':
            'Probabilistic', 'version': '2.2.12', 'description': 'A set of probabilistic data structures to Redis, including
            Bloom filter, Cuckoo filter, Count-min sketch, Top-K, and t-digest', 'parameters': []}, {'id': 18536, 'name':
            'RedisJSON', 'capabilityName': 'JSON', 'version': '2.0.6', 'description': 'Native JSON Data Type for Redis,
            allowing for atomic reads and writes of sub-elements', 'parameters': []}, {'id': 18537, 'name':
            'RedisTimeSeries', 'capabilityName': 'Time series', 'version': '1.6.8', 'description': 'Time-Series data
            structure for Redis', 'parameters': []}], 'alerts': [{'name': 'connections-limit', 'value': 80, 'defaultValue':
            80}], 'backup': {'remoteBackupEnabled': False}, 'links': []}

    Attributes:
        database_id (Union[Unset, int]):
        name (Union[Unset, str]):
        protocol (Union[Unset, FixedDatabaseProtocol]):
        provider (Union[Unset, str]):
        region (Union[Unset, str]):
        redis_version (Union[Unset, str]):
        redis_version_compliance (Union[Unset, str]):
        resp_version (Union[Unset, FixedDatabaseRespVersion]):
        status (Union[Unset, str]):
        plan_memory_limit (Union[Unset, float]):
        plan_dataset_size (Union[Unset, float]):
        memory_limit_measurement_unit (Union[Unset, str]):
        memory_limit_in_gb (Union[Unset, float]):
        dataset_size_in_gb (Union[Unset, float]):
        memory_used_in_mb (Union[Unset, float]):
        network_monthly_usage_in_byte (Union[Unset, float]):
        memory_storage (Union[Unset, FixedDatabaseMemoryStorage]):
        redis_flex (Union[Unset, bool]):
        support_oss_cluster_api (Union[Unset, bool]):
        use_external_endpoint_for_oss_cluster_api (Union[Unset, bool]):
        data_persistence (Union[Unset, FixedDatabaseDataPersistence]):
        replication (Union[Unset, bool]):
        data_eviction_policy (Union[Unset, FixedDatabaseDataEvictionPolicy]):
        activated_on (Union[Unset, datetime.datetime]):
        last_modified (Union[Unset, datetime.datetime]):
        public_endpoint (Union[Unset, str]):
        private_endpoint (Union[Unset, str]):
        dynamic_endpoints (Union[Unset, DynamicEndpoints]):
        links (Union[Unset, list['FixedDatabaseLinksItem']]):
    """

    database_id: Union[Unset, int] = UNSET
    name: Union[Unset, str] = UNSET
    protocol: Union[Unset, FixedDatabaseProtocol] = UNSET
    provider: Union[Unset, str] = UNSET
    region: Union[Unset, str] = UNSET
    redis_version: Union[Unset, str] = UNSET
    redis_version_compliance: Union[Unset, str] = UNSET
    resp_version: Union[Unset, FixedDatabaseRespVersion] = UNSET
    status: Union[Unset, str] = UNSET
    plan_memory_limit: Union[Unset, float] = UNSET
    plan_dataset_size: Union[Unset, float] = UNSET
    memory_limit_measurement_unit: Union[Unset, str] = UNSET
    memory_limit_in_gb: Union[Unset, float] = UNSET
    dataset_size_in_gb: Union[Unset, float] = UNSET
    memory_used_in_mb: Union[Unset, float] = UNSET
    network_monthly_usage_in_byte: Union[Unset, float] = UNSET
    memory_storage: Union[Unset, FixedDatabaseMemoryStorage] = UNSET
    redis_flex: Union[Unset, bool] = UNSET
    support_oss_cluster_api: Union[Unset, bool] = UNSET
    use_external_endpoint_for_oss_cluster_api: Union[Unset, bool] = UNSET
    data_persistence: Union[Unset, FixedDatabaseDataPersistence] = UNSET
    replication: Union[Unset, bool] = UNSET
    data_eviction_policy: Union[Unset, FixedDatabaseDataEvictionPolicy] = UNSET
    activated_on: Union[Unset, datetime.datetime] = UNSET
    last_modified: Union[Unset, datetime.datetime] = UNSET
    public_endpoint: Union[Unset, str] = UNSET
    private_endpoint: Union[Unset, str] = UNSET
    dynamic_endpoints: Union[Unset, "DynamicEndpoints"] = UNSET
    links: Union[Unset, list["FixedDatabaseLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        database_id = self.database_id

        name = self.name

        protocol: Union[Unset, str] = UNSET
        if not isinstance(self.protocol, Unset):
            protocol = self.protocol.value

        provider = self.provider

        region = self.region

        redis_version = self.redis_version

        redis_version_compliance = self.redis_version_compliance

        resp_version: Union[Unset, str] = UNSET
        if not isinstance(self.resp_version, Unset):
            resp_version = self.resp_version.value

        status = self.status

        plan_memory_limit = self.plan_memory_limit

        plan_dataset_size = self.plan_dataset_size

        memory_limit_measurement_unit = self.memory_limit_measurement_unit

        memory_limit_in_gb = self.memory_limit_in_gb

        dataset_size_in_gb = self.dataset_size_in_gb

        memory_used_in_mb = self.memory_used_in_mb

        network_monthly_usage_in_byte = self.network_monthly_usage_in_byte

        memory_storage: Union[Unset, str] = UNSET
        if not isinstance(self.memory_storage, Unset):
            memory_storage = self.memory_storage.value

        redis_flex = self.redis_flex

        support_oss_cluster_api = self.support_oss_cluster_api

        use_external_endpoint_for_oss_cluster_api = self.use_external_endpoint_for_oss_cluster_api

        data_persistence: Union[Unset, str] = UNSET
        if not isinstance(self.data_persistence, Unset):
            data_persistence = self.data_persistence.value

        replication = self.replication

        data_eviction_policy: Union[Unset, str] = UNSET
        if not isinstance(self.data_eviction_policy, Unset):
            data_eviction_policy = self.data_eviction_policy.value

        activated_on: Union[Unset, str] = UNSET
        if not isinstance(self.activated_on, Unset):
            activated_on = self.activated_on.isoformat()

        last_modified: Union[Unset, str] = UNSET
        if not isinstance(self.last_modified, Unset):
            last_modified = self.last_modified.isoformat()

        public_endpoint = self.public_endpoint

        private_endpoint = self.private_endpoint

        dynamic_endpoints: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.dynamic_endpoints, Unset):
            dynamic_endpoints = self.dynamic_endpoints.to_dict()

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if database_id is not UNSET:
            field_dict["databaseId"] = database_id
        if name is not UNSET:
            field_dict["name"] = name
        if protocol is not UNSET:
            field_dict["protocol"] = protocol
        if provider is not UNSET:
            field_dict["provider"] = provider
        if region is not UNSET:
            field_dict["region"] = region
        if redis_version is not UNSET:
            field_dict["redisVersion"] = redis_version
        if redis_version_compliance is not UNSET:
            field_dict["redisVersionCompliance"] = redis_version_compliance
        if resp_version is not UNSET:
            field_dict["respVersion"] = resp_version
        if status is not UNSET:
            field_dict["status"] = status
        if plan_memory_limit is not UNSET:
            field_dict["planMemoryLimit"] = plan_memory_limit
        if plan_dataset_size is not UNSET:
            field_dict["planDatasetSize"] = plan_dataset_size
        if memory_limit_measurement_unit is not UNSET:
            field_dict["memoryLimitMeasurementUnit"] = memory_limit_measurement_unit
        if memory_limit_in_gb is not UNSET:
            field_dict["memoryLimitInGb"] = memory_limit_in_gb
        if dataset_size_in_gb is not UNSET:
            field_dict["datasetSizeInGb"] = dataset_size_in_gb
        if memory_used_in_mb is not UNSET:
            field_dict["memoryUsedInMb"] = memory_used_in_mb
        if network_monthly_usage_in_byte is not UNSET:
            field_dict["networkMonthlyUsageInByte"] = network_monthly_usage_in_byte
        if memory_storage is not UNSET:
            field_dict["memoryStorage"] = memory_storage
        if redis_flex is not UNSET:
            field_dict["redisFlex"] = redis_flex
        if support_oss_cluster_api is not UNSET:
            field_dict["supportOSSClusterApi"] = support_oss_cluster_api
        if use_external_endpoint_for_oss_cluster_api is not UNSET:
            field_dict["useExternalEndpointForOSSClusterApi"] = use_external_endpoint_for_oss_cluster_api
        if data_persistence is not UNSET:
            field_dict["dataPersistence"] = data_persistence
        if replication is not UNSET:
            field_dict["replication"] = replication
        if data_eviction_policy is not UNSET:
            field_dict["dataEvictionPolicy"] = data_eviction_policy
        if activated_on is not UNSET:
            field_dict["activatedOn"] = activated_on
        if last_modified is not UNSET:
            field_dict["lastModified"] = last_modified
        if public_endpoint is not UNSET:
            field_dict["publicEndpoint"] = public_endpoint
        if private_endpoint is not UNSET:
            field_dict["privateEndpoint"] = private_endpoint
        if dynamic_endpoints is not UNSET:
            field_dict["dynamicEndpoints"] = dynamic_endpoints
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dynamic_endpoints import DynamicEndpoints
        from ..models.fixed_database_links_item import FixedDatabaseLinksItem

        d = dict(src_dict)
        database_id = d.pop("databaseId", UNSET)

        name = d.pop("name", UNSET)

        _protocol = d.pop("protocol", UNSET)
        protocol: Union[Unset, FixedDatabaseProtocol]
        if isinstance(_protocol, Unset):
            protocol = UNSET
        else:
            protocol = FixedDatabaseProtocol(_protocol)

        provider = d.pop("provider", UNSET)

        region = d.pop("region", UNSET)

        redis_version = d.pop("redisVersion", UNSET)

        redis_version_compliance = d.pop("redisVersionCompliance", UNSET)

        _resp_version = d.pop("respVersion", UNSET)
        resp_version: Union[Unset, FixedDatabaseRespVersion]
        if isinstance(_resp_version, Unset):
            resp_version = UNSET
        else:
            resp_version = FixedDatabaseRespVersion(_resp_version)

        status = d.pop("status", UNSET)

        plan_memory_limit = d.pop("planMemoryLimit", UNSET)

        plan_dataset_size = d.pop("planDatasetSize", UNSET)

        memory_limit_measurement_unit = d.pop("memoryLimitMeasurementUnit", UNSET)

        memory_limit_in_gb = d.pop("memoryLimitInGb", UNSET)

        dataset_size_in_gb = d.pop("datasetSizeInGb", UNSET)

        memory_used_in_mb = d.pop("memoryUsedInMb", UNSET)

        network_monthly_usage_in_byte = d.pop("networkMonthlyUsageInByte", UNSET)

        _memory_storage = d.pop("memoryStorage", UNSET)
        memory_storage: Union[Unset, FixedDatabaseMemoryStorage]
        if isinstance(_memory_storage, Unset):
            memory_storage = UNSET
        else:
            memory_storage = FixedDatabaseMemoryStorage(_memory_storage)

        redis_flex = d.pop("redisFlex", UNSET)

        support_oss_cluster_api = d.pop("supportOSSClusterApi", UNSET)

        use_external_endpoint_for_oss_cluster_api = d.pop("useExternalEndpointForOSSClusterApi", UNSET)

        _data_persistence = d.pop("dataPersistence", UNSET)
        data_persistence: Union[Unset, FixedDatabaseDataPersistence]
        if isinstance(_data_persistence, Unset):
            data_persistence = UNSET
        else:
            data_persistence = FixedDatabaseDataPersistence(_data_persistence)

        replication = d.pop("replication", UNSET)

        _data_eviction_policy = d.pop("dataEvictionPolicy", UNSET)
        data_eviction_policy: Union[Unset, FixedDatabaseDataEvictionPolicy]
        if isinstance(_data_eviction_policy, Unset):
            data_eviction_policy = UNSET
        else:
            data_eviction_policy = FixedDatabaseDataEvictionPolicy(_data_eviction_policy)

        _activated_on = d.pop("activatedOn", UNSET)
        activated_on: Union[Unset, datetime.datetime]
        if isinstance(_activated_on, Unset):
            activated_on = UNSET
        else:
            activated_on = isoparse(_activated_on)

        _last_modified = d.pop("lastModified", UNSET)
        last_modified: Union[Unset, datetime.datetime]
        if isinstance(_last_modified, Unset):
            last_modified = UNSET
        else:
            last_modified = isoparse(_last_modified)

        public_endpoint = d.pop("publicEndpoint", UNSET)

        private_endpoint = d.pop("privateEndpoint", UNSET)

        _dynamic_endpoints = d.pop("dynamicEndpoints", UNSET)
        dynamic_endpoints: Union[Unset, DynamicEndpoints]
        if isinstance(_dynamic_endpoints, Unset):
            dynamic_endpoints = UNSET
        else:
            dynamic_endpoints = DynamicEndpoints.from_dict(_dynamic_endpoints)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = FixedDatabaseLinksItem.from_dict(links_item_data)

            links.append(links_item)

        fixed_database = cls(
            database_id=database_id,
            name=name,
            protocol=protocol,
            provider=provider,
            region=region,
            redis_version=redis_version,
            redis_version_compliance=redis_version_compliance,
            resp_version=resp_version,
            status=status,
            plan_memory_limit=plan_memory_limit,
            plan_dataset_size=plan_dataset_size,
            memory_limit_measurement_unit=memory_limit_measurement_unit,
            memory_limit_in_gb=memory_limit_in_gb,
            dataset_size_in_gb=dataset_size_in_gb,
            memory_used_in_mb=memory_used_in_mb,
            network_monthly_usage_in_byte=network_monthly_usage_in_byte,
            memory_storage=memory_storage,
            redis_flex=redis_flex,
            support_oss_cluster_api=support_oss_cluster_api,
            use_external_endpoint_for_oss_cluster_api=use_external_endpoint_for_oss_cluster_api,
            data_persistence=data_persistence,
            replication=replication,
            data_eviction_policy=data_eviction_policy,
            activated_on=activated_on,
            last_modified=last_modified,
            public_endpoint=public_endpoint,
            private_endpoint=private_endpoint,
            dynamic_endpoints=dynamic_endpoints,
            links=links,
        )

        fixed_database.additional_properties = d
        return fixed_database

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

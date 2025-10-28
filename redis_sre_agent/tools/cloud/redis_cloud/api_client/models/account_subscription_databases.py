from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.account_subscription_databases_links_item import AccountSubscriptionDatabasesLinksItem


T = TypeVar("T", bound="AccountSubscriptionDatabases")


@_attrs_define
class AccountSubscriptionDatabases:
    r"""RedisLabs Account Subscription Databases information

    Example:
        {'accountId': 1001, 'subscription': [{'subscriptionId': 1206, 'numberOfDatabases': 6, 'databases':
            [{'databaseId': 1, 'name': 'DB-RCP-2-81-7', 'protocol': 'redis', 'provider': 'AWS', 'region': 'us-east-1',
            'redisVersion': '7.4', 'respVersion': 'resp2', 'status': 'active', 'datasetSizeInGb': 2, 'memoryUsedInMb': 4,
            'memoryStorage': 'ram', 'supportOSSClusterApi': True, 'useExternalEndpointForOSSClusterApi': True,
            'dataPersistence': 'snapshot-every-1-hour', 'replication': False, 'dataEvictionPolicy': 'noeviction',
            'throughputMeasurement': {'by': 'operations-per-second', 'value': 2500}, 'activatedOn': '2021-08-29T13:03:08Z',
            'lastModified': '2021-08-29T13:03:08Z', 'publicEndpoint': 'redis-17571.c235866.us-east-1-1.ec2.qa-
            cloud.rlrcp.com:17571', 'privateEndpoint': 'redis-17571.internal.c235866.us-east-1-1.ec2.qa-
            cloud.rlrcp.com:17571', 'replica': {'syncSources': [{'endpoint': 'redis://localhost:6379', 'encryption': True,
            'clientCert': '-----BEGIN CERTIFICATE-----\n ... -----END CERTIFICATE-----'}]}, 'clustering': {'numberOfShards':
            1, 'regexRules': [{'ordinal': 1, 'pattern': '(?<tag>.*)'}, {'ordinal': 0, 'pattern': '.*\\{(?<tag>.*)\\}.*'}],
            'hashingPolicy': 'standard'}, 'security': {'enableDefaultUser': True, 'sslClientAuthentication': False,
            'tlsClientAuthentication': False, 'enableTls': False, 'sourceIps': ['0.0.0.0/0']}, 'modules': [{'id': 18536,
            'name': 'RedisJSON', 'capabilityName': 'JSON', 'version': '2.0.6', 'description': 'Native JSON Data Type for
            Redis, allowing for atomic reads and writes of sub-elements', 'parameters': []}], 'alerts': [], 'links': []},
            {'databaseId': 2, 'name': 'DB-RCP-2-81-5', 'protocol': 'redis', 'provider': 'AWS', 'region': 'us-east-1',
            'redisVersion': '7.4', 'status': 'active', 'datasetSizeInGb': 2, 'memoryUsedInMb': 2, 'memoryStorage': 'ram',
            'supportOSSClusterApi': True, 'useExternalEndpointForOSSClusterApi': True, 'dataPersistence': 'snapshot-
            every-1-hour', 'replication': False, 'dataEvictionPolicy': 'noeviction', 'throughputMeasurement': {'by':
            'operations-per-second', 'value': 25000}, 'activatedOn': '2021-08-29T13:03:27Z', 'lastModified':
            '2021-08-29T13:03:27Z', 'publicEndpoint': 'redis-11836.c235866.us-east-1-1.ec2.qa-cloud.rlrcp.com:11836',
            'privateEndpoint': 'redis-11836.internal.c235866.us-east-1-1.ec2.qa-cloud.rlrcp.com:11836', 'replica':
            {'syncSources': [{'endpoint': 'redis://localhost:6379', 'encryption': True, 'clientCert': '-----BEGIN
            CERTIFICATE-----\n ... -----END CERTIFICATE-----'}]}, 'clustering': {'numberOfShards': 1, 'regexRules':
            [{'ordinal': 0, 'pattern': '.*\\{(?<tag>.*)\\}.*'}, {'ordinal': 1, 'pattern': '(?<tag>.*)'}], 'hashingPolicy':
            'standard'}, 'security': {'enableDefaultUser': True, 'sslClientAuthentication': False,
            'tlsClientAuthentication': False, 'enableTls': False, 'sourceIps': ['0.0.0.0/0']}, 'modules': [{'id': 6652,
            'name': 'RediSearch', 'capabilityName': 'Search and query', 'version': '2.0.11', 'description': 'A
            comprehensive, expressive, flexible, fast and developer-friendly search and query engine for the diversity of
            data types in Redis with state-of-the-art scoring algorithms', 'parameters': []}], 'alerts': [], 'links': []},
            {'databaseId': 3, 'name': 'Redis-database-example-updated', 'protocol': 'redis', 'provider': 'AWS', 'region':
            'us-east-1', 'redisVersion': '7.4', 'status': 'active', 'datasetSizeInGb': 2, 'memoryUsedInMb': 2,
            'memoryStorage': 'ram', 'supportOSSClusterApi': True, 'useExternalEndpointForOSSClusterApi': True,
            'dataPersistence': 'snapshot-every-1-hour', 'replication': False, 'dataEvictionPolicy': 'noeviction',
            'throughputMeasurement': {'by': 'operations-per-second', 'value': 2500}, 'activatedOn': '2021-08-29T13:03:26Z',
            'lastModified': '2021-08-29T13:03:26Z', 'publicEndpoint': 'redis-19708.c235866.us-east-1-1.ec2.qa-
            cloud.rlrcp.com:19708', 'privateEndpoint': 'redis-19708.internal.c235866.us-east-1-1.ec2.qa-
            cloud.rlrcp.com:19708', 'replica': {'syncSources': [{'endpoint': 'redis://localhost:6379', 'encryption': True,
            'clientCert': '-----BEGIN CERTIFICATE-----\n ... -----END CERTIFICATE-----'}]}, 'clustering': {'numberOfShards':
            1, 'regexRules': [{'ordinal': 1, 'pattern': '(?<tag>.*)'}, {'ordinal': 0, 'pattern': '.*\\{(?<tag>.*)\\}.*'}],
            'hashingPolicy': 'standard'}, 'security': {'enableDefaultUser': False, 'sslClientAuthentication': False,
            'tlsClientAuthentication': False, 'enableTls': False, 'sourceIps': ['0.0.0.0/0']}, 'modules': [{'id': 18536,
            'name': 'RedisJSON', 'capabilityName': 'JSON', 'version': '2.0.6', 'description': 'Native JSON Data Type for
            Redis, allowing for atomic reads and writes of sub-elements', 'parameters': []}], 'alerts': [], 'links': []},
            {'databaseId': 4, 'name': 'DB-RCP-2-81-6', 'protocol': 'redis', 'provider': 'AWS', 'region': 'us-east-1',
            'redisVersion': '7.4', 'status': 'active', 'datasetSizeInGb': 2, 'memoryUsedInMb': 2, 'memoryStorage': 'ram',
            'supportOSSClusterApi': True, 'useExternalEndpointForOSSClusterApi': True, 'dataPersistence': 'snapshot-
            every-1-hour', 'replication': False, 'dataEvictionPolicy': 'noeviction', 'throughputMeasurement': {'by':
            'operations-per-second', 'value': 25000}, 'activatedOn': '2021-08-29T13:03:27Z', 'lastModified':
            '2021-08-29T13:03:27Z', 'publicEndpoint': 'redis-14503.c235866.us-east-1-1.ec2.qa-cloud.rlrcp.com:14503',
            'privateEndpoint': 'redis-14503.internal.c235866.us-east-1-1.ec2.qa-cloud.rlrcp.com:14503', 'replica':
            {'syncSources': [{'endpoint': 'redis://localhost:6379', 'encryption': True, 'clientCert': '-----BEGIN
            CERTIFICATE-----\n ... -----END CERTIFICATE-----'}]}, 'clustering': {'numberOfShards': 1, 'regexRules':
            [{'ordinal': 1, 'pattern': '(?<tag>.*)'}, {'ordinal': 0, 'pattern': '.*\\{(?<tag>.*)\\}.*'}], 'hashingPolicy':
            'standard'}, 'security': {'enableDefaultUser': True, 'sslClientAuthentication': False,
            'tlsClientAuthentication': False, 'enableTls': False, 'sourceIps': ['0.0.0.0/0']}, 'modules': [{'id': 6653,
            'name': 'RedisTimeSeries', 'capabilityName': 'Time series', 'version': '1.4.10', 'description': 'Time-Series
            data structure for redis', 'parameters': []}], 'alerts': [], 'links': []}, {'databaseId': 5, 'name': 'CI-tests-
            DO-NOT-DELETE', 'protocol': 'redis', 'provider': 'AWS', 'region': 'us-east-1', 'redisVersion': '7.4', 'status':
            'active', 'datasetSizeInGb': 2, 'memoryUsedInMb': 4, 'memoryStorage': 'ram', 'supportOSSClusterApi': False,
            'useExternalEndpointForOSSClusterApi': False, 'dataPersistence': 'none', 'replication': True,
            'dataEvictionPolicy': 'volatile-lru', 'throughputMeasurement': {'by': 'operations-per-second', 'value': 25000},
            'activatedOn': '2021-08-29T13:03:22Z', 'lastModified': '2021-08-29T13:03:22Z', 'publicEndpoint':
            'redis-11349.c235866.us-east-1-1.ec2.qa-cloud.rlrcp.com:11349', 'privateEndpoint':
            'redis-11349.internal.c235866.us-east-1-1.ec2.qa-cloud.rlrcp.com:11349', 'replica': {'syncSources':
            [{'endpoint': 'redis://localhost:6379', 'encryption': True, 'clientCert': '-----BEGIN CERTIFICATE-----\n ...
            -----END CERTIFICATE-----'}]}, 'clustering': {'numberOfShards': 1, 'regexRules': [], 'hashingPolicy':
            'standard'}, 'security': {'enableDefaultUser': True, 'sslClientAuthentication': False,
            'tlsClientAuthentication': False, 'enableTls': False, 'sourceIps': ['0.0.0.0/0']}, 'modules': [], 'alerts': [],
            'links': []}, {'databaseId': 6, 'name': 'DB-RCP-2-81-4', 'protocol': 'redis', 'provider': 'AWS', 'region': 'us-
            east-1', 'redisVersion': '7.4', 'status': 'active', 'datasetSizeInGb': 2, 'memoryUsedInMb': 1, 'memoryStorage':
            'ram', 'supportOSSClusterApi': True, 'useExternalEndpointForOSSClusterApi': True, 'dataPersistence': 'snapshot-
            every-1-hour', 'replication': False, 'dataEvictionPolicy': 'noeviction', 'throughputMeasurement': {'by':
            'operations-per-second', 'value': 25000}, 'activatedOn': '2021-08-29T13:03:27Z', 'lastModified':
            '2021-08-29T13:03:27Z', 'publicEndpoint': 'redis-13074.c235866.us-east-1-1.ec2.qa-cloud.rlrcp.com:13074',
            'privateEndpoint': 'redis-13074.internal.c235866.us-east-1-1.ec2.qa-cloud.rlrcp.com:13074', 'replica':
            {'syncSources': [{'endpoint': 'redis://localhost:6379', 'encryption': True, 'clientCert': '-----BEGIN
            CERTIFICATE-----\n ... -----END CERTIFICATE-----'}]}, 'clustering': {'numberOfShards': 1, 'regexRules':
            [{'ordinal': 1, 'pattern': '(?<tag>.*)'}, {'ordinal': 0, 'pattern': '.*\\{(?<tag>.*)\\}.*'}], 'hashingPolicy':
            'standard'}, 'security': {'enableDefaultUser': True, 'sslClientAuthentication': False,
            'tlsClientAuthentication': False, 'enableTls': False, 'sourceIps': ['0.0.0.0/0']}, 'modules': [{'id': 6651,
            'name': 'RediSearch', 'capabilityName': 'Search and query', 'version': '2.0.11', 'description': 'A
            comprehensive, expressive, flexible, fast and developer-friendly search and query engine for the diversity of
            data types in Redis with state-of-the-art scoring algorithms', 'parameters': []}], 'alerts': [], 'links': []}],
            'links': []}], 'links': [{'rel': 'self', 'href': 'https://api-
            cloudapi.qa.redislabs.com/v1/subscriptions/120416/databases?offset=0&limit=100', 'type': 'GET'}]}

    Attributes:
        account_id (Union[Unset, int]):
        links (Union[Unset, list['AccountSubscriptionDatabasesLinksItem']]):
    """

    account_id: Union[Unset, int] = UNSET
    links: Union[Unset, list["AccountSubscriptionDatabasesLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        account_id = self.account_id

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if account_id is not UNSET:
            field_dict["accountId"] = account_id
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.account_subscription_databases_links_item import AccountSubscriptionDatabasesLinksItem

        d = dict(src_dict)
        account_id = d.pop("accountId", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = AccountSubscriptionDatabasesLinksItem.from_dict(links_item_data)

            links.append(links_item)

        account_subscription_databases = cls(
            account_id=account_id,
            links=links,
        )

        account_subscription_databases.additional_properties = d
        return account_subscription_databases

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

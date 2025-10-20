from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.account_fixed_subscription_databases_links_item import AccountFixedSubscriptionDatabasesLinksItem


T = TypeVar("T", bound="AccountFixedSubscriptionDatabases")


@_attrs_define
class AccountFixedSubscriptionDatabases:
    r"""RedisLabs Account Subscription Databases information

    Example:
        {'accountId': 40131, 'subscription': {'subscriptionId': 154714, 'numberOfDatabases': 2, 'databases':
            [{'databaseId': 51324587, 'name': 'bdb', 'protocol': 'stack', 'provider': 'AWS', 'region': 'us-east-1',
            'redisVersion': '7.4', 'status': 'draft', 'planMemoryLimit': 250, 'respVersion': 'resp2',
            'memoryLimitMeasurementUnit': 'MB', 'memoryUsedInMb': 1, 'memoryStorage': 'ram', 'dataPersistence': 'none',
            'replication': True, 'dataEvictionPolicy': 'noeviction', 'clustering': {'enabled': False, 'regexRules':
            [{'ordinal': 0, 'pattern': '.*\\{(?<tag>.*)\\}.*'}, {'ordinal': 1, 'pattern': '(?<tag>.*)'}], 'hashingPolicy':
            'standard'}, 'security': {'defaultUserEnabled': True, 'sourceIps': ['0.0.0.0/0']}, 'modules': [{'id': 18534,
            'name': 'searchlight', 'capabilityName': 'Search and query', 'version': '2.2.6', 'description': 'A
            comprehensive, expressive, flexible, fast and developer-friendly search and query engine for the diversity of
            data types in Redis with state-of-the-art scoring algorithms', 'parameters': []}, {'id': 18535, 'name':
            'RedisBloom', 'capabilityName': 'Probabilistic', 'version': '2.2.12', 'description': 'A set of probabilistic
            data structures to Redis, including Bloom filter, Cuckoo filter, Count-min sketch, Top-K, and t-digest',
            'parameters': []}, {'id': 18536, 'name': 'RedisJSON', 'capabilityName': 'JSON', 'version': '2.0.6',
            'description': 'Native JSON Data Type for Redis, allowing for atomic reads and writes of sub-elements',
            'parameters': []}, {'id': 18537, 'name': 'RedisTimeSeries', 'capabilityName': 'Time series', 'version': '1.6.8',
            'description': 'Time-Series data structure for Redis', 'parameters': []}], 'alerts': [{'name': 'connections-
            limit', 'value': 80, 'defaultValue': 80}], 'backup': {'remoteBackupEnabled': False}, 'links': []},
            {'databaseId': 51324586, 'name': 'firstDB', 'protocol': 'stack', 'provider': 'AWS', 'region': 'us-east-1',
            'status': 'draft', 'planMemoryLimit': 250, 'memoryLimitMeasurementUnit': 'MB', 'memoryUsedInMb': 1,
            'memoryStorage': 'ram', 'dataPersistence': 'none', 'replication': True, 'dataEvictionPolicy': 'noeviction',
            'clustering': {'enabled': False, 'regexRules': [{'ordinal': 0, 'pattern': '.*\\{(?<tag>.*)\\}.*'}, {'ordinal':
            1, 'pattern': '(?<tag>.*)'}], 'hashingPolicy': 'standard'}, 'security': {'defaultUserEnabled': True,
            'sourceIps': ['0.0.0.0/0']}, 'modules': [{'id': 18529, 'name': 'searchlight', 'capabilityName': 'Search and
            query', 'version': '2.2.6', 'description': 'A comprehensive, expressive, flexible, fast and developer-friendly
            search and query engine for the diversity of data types in Redis with state-of-the-art scoring algorithms',
            'parameters': []}, {'id': 18530, 'name': 'RedisBloom', 'capabilityName': 'Probabilistic', 'version': '2.2.12',
            'description': 'A set of probabilistic data structures to Redis, including Bloom filter, Cuckoo filter, Count-
            min sketch, Top-K, and t-digest', 'parameters': []}, {'id': 18531, 'name': 'RedisJSON', 'capabilityName':
            'JSON', 'version': '2.0.6', 'description': 'Native JSON Data Type for Redis, allowing for atomic reads and
            writes of sub-elements', 'parameters': []}, {'id': 18532, 'name': 'RedisTimeSeries', 'capabilityName': 'Time
            series', 'version': '1.6.8', 'description': 'Time-Series data structure for Redis', 'parameters': []}],
            'alerts': [{'name': 'connections-limit', 'value': 80, 'defaultValue': 80}], 'backup': {'remoteBackupEnabled':
            False}, 'links': []}], 'links': []}, 'links': []}

    Attributes:
        account_id (Union[Unset, int]):
        links (Union[Unset, list['AccountFixedSubscriptionDatabasesLinksItem']]):
    """

    account_id: Union[Unset, int] = UNSET
    links: Union[Unset, list["AccountFixedSubscriptionDatabasesLinksItem"]] = UNSET
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
        from ..models.account_fixed_subscription_databases_links_item import AccountFixedSubscriptionDatabasesLinksItem

        d = dict(src_dict)
        account_id = d.pop("accountId", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = AccountFixedSubscriptionDatabasesLinksItem.from_dict(links_item_data)

            links.append(links_item)

        account_fixed_subscription_databases = cls(
            account_id=account_id,
            links=links,
        )

        account_fixed_subscription_databases.additional_properties = d
        return account_fixed_subscription_databases

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

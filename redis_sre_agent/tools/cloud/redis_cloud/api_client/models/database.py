from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.database_links_item import DatabaseLinksItem


T = TypeVar("T", bound="Database")


@_attrs_define
class Database:
    r"""
    Example:
        {'databaseId': 1, 'name': 'DB-RCP-2-81-7', 'protocol': 'redis', 'provider': 'AWS', 'region': 'us-east-1',
            'redisVersion': '7.4', 'respVersion': 'resp3', 'status': 'active', 'datasetSizeInGb': 2, 'memoryUsedInMb': 4,
            'memoryStorage': 'ram', 'supportOSSClusterApi': True, 'useExternalEndpointForOSSClusterApi': True,
            'dataPersistence': 'snapshot-every-1-hour', 'replication': False, 'dataEvictionPolicy': 'noeviction',
            'throughputMeasurement': {'by': 'operations-per-second', 'value': 2500}, 'activatedOn': '2021-08-29T13:03:08Z',
            'lastModified': '2021-08-29T13:03:08Z', 'publicEndpoint': 'redis-17571.c235866.us-east-1-1.ec2.qa-
            cloud.rlrcp.com:17571', 'privateEndpoint': 'redis-17571.internal.c235866.us-east-1-1.ec2.qa-
            cloud.rlrcp.com:17571', 'replica': {'syncSources': [{'endpoint': 'redis://localhost:6379', 'encryption': True,
            'clientCert': '-----BEGIN CERTIFICATE-----\n ... -----END CERTIFICATE-----'}]}, 'clustering': {'numberOfShards':
            1, 'regexRules': [{'ordinal': 1, 'pattern': '(?<tag>.*)'}, {'ordinal': 0, 'pattern': '.*\\{(?<tag>.*)\\}.*'}],
            'hashingPolicy': 'standard'}, 'security': {'enableDefaultUser': True, 'password': 'redis123456redis',
            'sslClientAuthentication': False, 'tlsClientAuthentication': False, 'enableTls': False, 'sourceIps':
            ['0.0.0.0/0']}, 'modules': [{'id': 18536, 'name': 'RedisJSON', 'capabilityName': 'JSON', 'version': '2.0.6',
            'description': 'Native JSON Data Type for Redis, allowing for atomic reads and writes of sub-elements',
            'parameters': []}], 'alerts': [], 'links': [{'rel': 'self', 'href': 'https://api-
            cloudapi.qa.redislabs.com/v1/subscriptions/120416/databases/51170941', 'type': 'GET'}]}

    Attributes:
        database_id (Union[Unset, int]):
        links (Union[Unset, list['DatabaseLinksItem']]):
    """

    database_id: Union[Unset, int] = UNSET
    links: Union[Unset, list["DatabaseLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        database_id = self.database_id

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
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.database_links_item import DatabaseLinksItem

        d = dict(src_dict)
        database_id = d.pop("databaseId", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = DatabaseLinksItem.from_dict(links_item_data)

            links.append(links_item)

        database = cls(
            database_id=database_id,
            links=links,
        )

        database.additional_properties = d
        return database

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

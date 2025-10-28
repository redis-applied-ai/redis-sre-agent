from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.data_persistence_entry import DataPersistenceEntry
    from ..models.data_persistence_options_links_item import DataPersistenceOptionsLinksItem


T = TypeVar("T", bound="DataPersistenceOptions")


@_attrs_define
class DataPersistenceOptions:
    """
    Example:
        {'dataPersistence': [{'name': 'none', 'description': 'None'}, {'name': 'aof-every-1-second', 'description':
            'Append only file (AOF) - fsync every 1 second'}, {'name': 'aof-every-write', 'description': 'Append only file
            (AOF) - fsync every write'}, {'name': 'snapshot-every-1-hour', 'description': 'Snapshot every 1 hour'}, {'name':
            'snapshot-every-6-hours', 'description': 'Snapshot every 6 hour'}, {'name': 'snapshot-every-12-hours',
            'description': 'Snapshot every 12 hour'}], 'links': [{'rel': 'self', 'href': 'https://api-
            cloudapi.qa.redislabs.com/v1/data-persistence', 'type': 'GET'}]}

    Attributes:
        data_persistence (Union[Unset, list['DataPersistenceEntry']]):
        links (Union[Unset, list['DataPersistenceOptionsLinksItem']]):
    """

    data_persistence: Union[Unset, list["DataPersistenceEntry"]] = UNSET
    links: Union[Unset, list["DataPersistenceOptionsLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data_persistence: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.data_persistence, Unset):
            data_persistence = []
            for data_persistence_item_data in self.data_persistence:
                data_persistence_item = data_persistence_item_data.to_dict()
                data_persistence.append(data_persistence_item)

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if data_persistence is not UNSET:
            field_dict["dataPersistence"] = data_persistence
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.data_persistence_entry import DataPersistenceEntry
        from ..models.data_persistence_options_links_item import DataPersistenceOptionsLinksItem

        d = dict(src_dict)
        data_persistence = []
        _data_persistence = d.pop("dataPersistence", UNSET)
        for data_persistence_item_data in _data_persistence or []:
            data_persistence_item = DataPersistenceEntry.from_dict(data_persistence_item_data)

            data_persistence.append(data_persistence_item)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = DataPersistenceOptionsLinksItem.from_dict(links_item_data)

            links.append(links_item)

        data_persistence_options = cls(
            data_persistence=data_persistence,
            links=links,
        )

        data_persistence_options.additional_properties = d
        return data_persistence_options

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

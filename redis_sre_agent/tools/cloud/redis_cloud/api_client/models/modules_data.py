from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.module import Module
    from ..models.modules_data_links_item import ModulesDataLinksItem


T = TypeVar("T", bound="ModulesData")


@_attrs_define
class ModulesData:
    """
    Example:
        {'modules': [{'name': 'RedisBloom', 'capabilityName': 'Probabilistic', 'description': 'A set of probabilistic
            data structures to Redis, including Bloom filter, Cuckoo filter, Count-min sketch, Top-K, and t-digest',
            'parameters': []}, {'name': 'RedisJSON', 'capabilityName': 'JSON', 'description': 'Native JSON Data Type for
            Redis, allowing for atomic reads and writes of sub-elements', 'parameters': []}, {'name': 'RediSearch',
            'capabilityName': 'Search and query', 'description': 'A comprehensive, expressive, flexible, fast and developer-
            friendly search and query engine for the diversity of data types in Redis with state-of-the-art scoring
            algorithms', 'parameters': [{'name': 'number-of-documents', 'description': 'Expected number of documents the
            database module will be indexing', 'type': 'integer', 'defaultValue': 1000000, 'required': False}]}, {'name':
            'RedisTimeSeries', 'capabilityName': 'Time series', 'description': 'Time-Series data structure for redis',
            'parameters': []}]}

    Attributes:
        modules (Union[Unset, list['Module']]):
        links (Union[Unset, list['ModulesDataLinksItem']]):
    """

    modules: Union[Unset, list["Module"]] = UNSET
    links: Union[Unset, list["ModulesDataLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        modules: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.modules, Unset):
            modules = []
            for modules_item_data in self.modules:
                modules_item = modules_item_data.to_dict()
                modules.append(modules_item)

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if modules is not UNSET:
            field_dict["modules"] = modules
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.module import Module
        from ..models.modules_data_links_item import ModulesDataLinksItem

        d = dict(src_dict)
        modules = []
        _modules = d.pop("modules", UNSET)
        for modules_item_data in _modules or []:
            modules_item = Module.from_dict(modules_item_data)

            modules.append(modules_item)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = ModulesDataLinksItem.from_dict(links_item_data)

            links.append(links_item)

        modules_data = cls(
            modules=modules,
            links=links,
        )

        modules_data.additional_properties = d
        return modules_data

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

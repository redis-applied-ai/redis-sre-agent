from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.cloud_tag_links_item import CloudTagLinksItem


T = TypeVar("T", bound="CloudTag")


@_attrs_define
class CloudTag:
    """Database tag

    Example:
        {'key': 'environment', 'value': 'production', 'createdAt': '2024-05-21T20:02:21+02:00', 'updatedAt':
            '2024-06-21T20:02:21+02:00', 'links': [{'rel': 'self', 'type': 'GET', 'href':
            'http://localhost:8081/v1/fixed/subscriptions/178867/databases/51412930/tags'}]}

    Attributes:
        links (Union[Unset, list['CloudTagLinksItem']]):
        key (Union[Unset, str]):
        value (Union[Unset, str]):
        created_at (Union[Unset, str]):
        updated_at (Union[Unset, str]):
    """

    links: Union[Unset, list["CloudTagLinksItem"]] = UNSET
    key: Union[Unset, str] = UNSET
    value: Union[Unset, str] = UNSET
    created_at: Union[Unset, str] = UNSET
    updated_at: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        key = self.key

        value = self.value

        created_at = self.created_at

        updated_at = self.updated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if links is not UNSET:
            field_dict["links"] = links
        if key is not UNSET:
            field_dict["key"] = key
        if value is not UNSET:
            field_dict["value"] = value
        if created_at is not UNSET:
            field_dict["createdAt"] = created_at
        if updated_at is not UNSET:
            field_dict["updatedAt"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cloud_tag_links_item import CloudTagLinksItem

        d = dict(src_dict)
        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = CloudTagLinksItem.from_dict(links_item_data)

            links.append(links_item)

        key = d.pop("key", UNSET)

        value = d.pop("value", UNSET)

        created_at = d.pop("createdAt", UNSET)

        updated_at = d.pop("updatedAt", UNSET)

        cloud_tag = cls(
            links=links,
            key=key,
            value=value,
            created_at=created_at,
            updated_at=updated_at,
        )

        cloud_tag.additional_properties = d
        return cloud_tag

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

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.cloud_tags_links_item import CloudTagsLinksItem


T = TypeVar("T", bound="CloudTags")


@_attrs_define
class CloudTags:
    """Redis list of database tags

    Example:
        {'accountId': 40131, 'tags': [{'key': 'environment', 'value': 'production', 'createdAt':
            '2024-05-21T20:02:21+02:00', 'updatedAt': '2024-06-21T20:02:21+02:00', 'links': []}, {'key': 'owner', 'value':
            "Clifford O'neill", 'createdAt': '2024-05-21T20:02:21+02:00', 'updatedAt': '2024-06-21T20:02:21+02:00', 'links':
            []}], 'links': [{'rel': 'self', 'href':
            'http://localhost:8081/v1/fixed/subscriptions/178867/databases/51412930/tags', 'type': 'GET'}]}

    Attributes:
        links (Union[Unset, list['CloudTagsLinksItem']]):
        account_id (Union[Unset, int]):
    """

    links: Union[Unset, list["CloudTagsLinksItem"]] = UNSET
    account_id: Union[Unset, int] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        account_id = self.account_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if links is not UNSET:
            field_dict["links"] = links
        if account_id is not UNSET:
            field_dict["accountId"] = account_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cloud_tags_links_item import CloudTagsLinksItem

        d = dict(src_dict)
        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = CloudTagsLinksItem.from_dict(links_item_data)

            links.append(links_item)

        account_id = d.pop("accountId", UNSET)

        cloud_tags = cls(
            links=links,
            account_id=account_id,
        )

        cloud_tags.additional_properties = d
        return cloud_tags

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

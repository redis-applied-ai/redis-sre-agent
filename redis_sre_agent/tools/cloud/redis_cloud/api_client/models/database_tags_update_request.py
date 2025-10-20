from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tag import Tag


T = TypeVar("T", bound="DatabaseTagsUpdateRequest")


@_attrs_define
class DatabaseTagsUpdateRequest:
    """Database tags update request message

    Attributes:
        tags (list['Tag']): List of database tags.
        subscription_id (Union[Unset, int]):
        database_id (Union[Unset, int]):
        command_type (Union[Unset, str]):
    """

    tags: list["Tag"]
    subscription_id: Union[Unset, int] = UNSET
    database_id: Union[Unset, int] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tags = []
        for tags_item_data in self.tags:
            tags_item = tags_item_data.to_dict()
            tags.append(tags_item)

        subscription_id = self.subscription_id

        database_id = self.database_id

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tags": tags,
            }
        )
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if database_id is not UNSET:
            field_dict["databaseId"] = database_id
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tag import Tag

        d = dict(src_dict)
        tags = []
        _tags = d.pop("tags")
        for tags_item_data in _tags:
            tags_item = Tag.from_dict(tags_item_data)

            tags.append(tags_item)

        subscription_id = d.pop("subscriptionId", UNSET)

        database_id = d.pop("databaseId", UNSET)

        command_type = d.pop("commandType", UNSET)

        database_tags_update_request = cls(
            tags=tags,
            subscription_id=subscription_id,
            database_id=database_id,
            command_type=command_type,
        )

        database_tags_update_request.additional_properties = d
        return database_tags_update_request

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

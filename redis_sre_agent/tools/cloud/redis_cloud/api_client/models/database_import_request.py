from collections.abc import Mapping
from typing import Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.database_import_request_source_type import DatabaseImportRequestSourceType
from ..types import UNSET, Unset

T = TypeVar("T", bound="DatabaseImportRequest")


@_attrs_define
class DatabaseImportRequest:
    """Database import request

    Attributes:
        source_type (DatabaseImportRequestSourceType): Type of storage from which to import the database RDB file or
            Redis data. Example: http.
        import_from_uri (list[str]): One or more paths to source data files or Redis databases, as appropriate to
            specified source type.
        subscription_id (Union[Unset, int]):
        database_id (Union[Unset, int]):
        command_type (Union[Unset, str]):
    """

    source_type: DatabaseImportRequestSourceType
    import_from_uri: list[str]
    subscription_id: Union[Unset, int] = UNSET
    database_id: Union[Unset, int] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source_type = self.source_type.value

        import_from_uri = self.import_from_uri

        subscription_id = self.subscription_id

        database_id = self.database_id

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sourceType": source_type,
                "importFromUri": import_from_uri,
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
        d = dict(src_dict)
        source_type = DatabaseImportRequestSourceType(d.pop("sourceType"))

        import_from_uri = cast(list[str], d.pop("importFromUri"))

        subscription_id = d.pop("subscriptionId", UNSET)

        database_id = d.pop("databaseId", UNSET)

        command_type = d.pop("commandType", UNSET)

        database_import_request = cls(
            source_type=source_type,
            import_from_uri=import_from_uri,
            subscription_id=subscription_id,
            database_id=database_id,
            command_type=command_type,
        )

        database_import_request.additional_properties = d
        return database_import_request

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

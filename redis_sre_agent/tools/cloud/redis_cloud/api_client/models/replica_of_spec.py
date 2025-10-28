from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.database_sync_source_spec import DatabaseSyncSourceSpec


T = TypeVar("T", bound="ReplicaOfSpec")


@_attrs_define
class ReplicaOfSpec:
    """Optional. Changes Replica Of (also known as Active-Passive) configuration details.

    Attributes:
        sync_sources (list['DatabaseSyncSourceSpec']): Optional. This database will be a replica of the specified Redis
            databases, provided as a list of objects with endpoint and certificate details.
    """

    sync_sources: list["DatabaseSyncSourceSpec"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        sync_sources = []
        for sync_sources_item_data in self.sync_sources:
            sync_sources_item = sync_sources_item_data.to_dict()
            sync_sources.append(sync_sources_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "syncSources": sync_sources,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.database_sync_source_spec import DatabaseSyncSourceSpec

        d = dict(src_dict)
        sync_sources = []
        _sync_sources = d.pop("syncSources")
        for sync_sources_item_data in _sync_sources:
            sync_sources_item = DatabaseSyncSourceSpec.from_dict(sync_sources_item_data)

            sync_sources.append(sync_sources_item)

        replica_of_spec = cls(
            sync_sources=sync_sources,
        )

        replica_of_spec.additional_properties = d
        return replica_of_spec

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

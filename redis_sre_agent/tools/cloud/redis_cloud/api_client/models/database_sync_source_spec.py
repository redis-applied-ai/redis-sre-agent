from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="DatabaseSyncSourceSpec")


@_attrs_define
class DatabaseSyncSourceSpec:
    """Optional. This database will be a replica of the specified Redis databases, provided as a list of objects with
    endpoint and certificate details.

        Attributes:
            endpoint (str): Redis URI of a source database. Example format: 'redis://user:password@host:port'. If the URI
                provided is a Redis Cloud database, only host and port should be provided. Example: 'redis://endpoint1:6379'.
            encryption (Union[Unset, bool]): Defines if encryption should be used to connect to the sync source. If not set
                the source is a Redis Cloud database, it will automatically detect if the source uses encryption.
            server_cert (Union[Unset, str]): TLS/SSL certificate chain of the sync source. If not set and the source is a
                Redis Cloud database, it will automatically detect the certificate to use.
    """

    endpoint: str
    encryption: Union[Unset, bool] = UNSET
    server_cert: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        endpoint = self.endpoint

        encryption = self.encryption

        server_cert = self.server_cert

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "endpoint": endpoint,
            }
        )
        if encryption is not UNSET:
            field_dict["encryption"] = encryption
        if server_cert is not UNSET:
            field_dict["serverCert"] = server_cert

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        endpoint = d.pop("endpoint")

        encryption = d.pop("encryption", UNSET)

        server_cert = d.pop("serverCert", UNSET)

        database_sync_source_spec = cls(
            endpoint=endpoint,
            encryption=encryption,
            server_cert=server_cert,
        )

        database_sync_source_spec.additional_properties = d
        return database_sync_source_spec

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

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="DatabaseCertificateSpec")


@_attrs_define
class DatabaseCertificateSpec:
    r"""Optional. A list of client TLS/SSL certificates. If specified, mTLS authentication will be required to authenticate
    user connections. If set to an empty list, TLS client certificates will be removed and mTLS will not be required.
    TLS connection may still apply, depending on the value of 'enableTls'.

        Attributes:
            public_certificate_pem_string (str): Client certificate public key in PEM format, with new line characters
                replaced with '\n'.
    """

    public_certificate_pem_string: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        public_certificate_pem_string = self.public_certificate_pem_string

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "publicCertificatePEMString": public_certificate_pem_string,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        public_certificate_pem_string = d.pop("publicCertificatePEMString")

        database_certificate_spec = cls(
            public_certificate_pem_string=public_certificate_pem_string,
        )

        database_certificate_spec.additional_properties = d
        return database_certificate_spec

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

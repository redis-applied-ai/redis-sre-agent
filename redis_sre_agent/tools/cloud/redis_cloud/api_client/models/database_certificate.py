from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="DatabaseCertificate")


@_attrs_define
class DatabaseCertificate:
    r"""Database certificate

    Attributes:
        public_certificate_pem_string (Union[Unset, str]): An X.509 PEM (base64) encoded server certificate with new
            line characters replaced by '\n'.
    """

    public_certificate_pem_string: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        public_certificate_pem_string = self.public_certificate_pem_string

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if public_certificate_pem_string is not UNSET:
            field_dict["publicCertificatePEMString"] = public_certificate_pem_string

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        public_certificate_pem_string = d.pop("publicCertificatePEMString", UNSET)

        database_certificate = cls(
            public_certificate_pem_string=public_certificate_pem_string,
        )

        database_certificate.additional_properties = d
        return database_certificate

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

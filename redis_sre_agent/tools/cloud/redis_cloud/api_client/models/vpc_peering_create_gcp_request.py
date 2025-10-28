from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="VpcPeeringCreateGcpRequest")


@_attrs_define
class VpcPeeringCreateGcpRequest:
    """Vpc peering creation request message

    Attributes:
        vpc_project_uid (str): VPC project ID. Example: <vpc-identifer>.
        vpc_network_name (str): VPC network name. Example: <name>.
        provider (Union[Unset, str]):
        command_type (Union[Unset, str]):
    """

    vpc_project_uid: str
    vpc_network_name: str
    provider: Union[Unset, str] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        vpc_project_uid = self.vpc_project_uid

        vpc_network_name = self.vpc_network_name

        provider = self.provider

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "vpcProjectUid": vpc_project_uid,
                "vpcNetworkName": vpc_network_name,
            }
        )
        if provider is not UNSET:
            field_dict["provider"] = provider
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        vpc_project_uid = d.pop("vpcProjectUid")

        vpc_network_name = d.pop("vpcNetworkName")

        provider = d.pop("provider", UNSET)

        command_type = d.pop("commandType", UNSET)

        vpc_peering_create_gcp_request = cls(
            vpc_project_uid=vpc_project_uid,
            vpc_network_name=vpc_network_name,
            provider=provider,
            command_type=command_type,
        )

        vpc_peering_create_gcp_request.additional_properties = d
        return vpc_peering_create_gcp_request

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

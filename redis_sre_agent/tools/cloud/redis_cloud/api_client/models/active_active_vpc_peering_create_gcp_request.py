from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ActiveActiveVpcPeeringCreateGcpRequest")


@_attrs_define
class ActiveActiveVpcPeeringCreateGcpRequest:
    """VPC peering creation request message

    Attributes:
        source_region (str): Name of region to create a VPC peering from.
        vpc_project_uid (str): VPC project ID. Example: <vpc-identifer>.
        vpc_network_name (str): VPC network name. Example: <name>.
        provider (Union[Unset, str]):
        subscription_id (Union[Unset, int]):
        command_type (Union[Unset, str]):
    """

    source_region: str
    vpc_project_uid: str
    vpc_network_name: str
    provider: Union[Unset, str] = UNSET
    subscription_id: Union[Unset, int] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source_region = self.source_region

        vpc_project_uid = self.vpc_project_uid

        vpc_network_name = self.vpc_network_name

        provider = self.provider

        subscription_id = self.subscription_id

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sourceRegion": source_region,
                "vpcProjectUid": vpc_project_uid,
                "vpcNetworkName": vpc_network_name,
            }
        )
        if provider is not UNSET:
            field_dict["provider"] = provider
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        source_region = d.pop("sourceRegion")

        vpc_project_uid = d.pop("vpcProjectUid")

        vpc_network_name = d.pop("vpcNetworkName")

        provider = d.pop("provider", UNSET)

        subscription_id = d.pop("subscriptionId", UNSET)

        command_type = d.pop("commandType", UNSET)

        active_active_vpc_peering_create_gcp_request = cls(
            source_region=source_region,
            vpc_project_uid=vpc_project_uid,
            vpc_network_name=vpc_network_name,
            provider=provider,
            subscription_id=subscription_id,
            command_type=command_type,
        )

        active_active_vpc_peering_create_gcp_request.additional_properties = d
        return active_active_vpc_peering_create_gcp_request

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

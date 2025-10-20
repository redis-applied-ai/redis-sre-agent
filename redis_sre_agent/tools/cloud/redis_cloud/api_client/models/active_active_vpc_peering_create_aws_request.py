from collections.abc import Mapping
from typing import Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ActiveActiveVpcPeeringCreateAwsRequest")


@_attrs_define
class ActiveActiveVpcPeeringCreateAwsRequest:
    """VPC peering creation request message

    Attributes:
        source_region (str): Name of region to create a VPC peering from.
        destination_region (str): Name of region to create a VPC peering to. Example: us-east-1.
        aws_account_id (str): AWS Account ID. Example: <aws-account-id>.
        vpc_id (str): VPC ID. Example: <vpc-identifier>.
        provider (Union[Unset, str]):
        subscription_id (Union[Unset, int]):
        vpc_cidr (Union[Unset, str]): Optional. VPC CIDR. Example: <10.10.10.0/24>.
        vpc_cidrs (Union[Unset, list[str]]): Optional. List of VPC CIDRs. Example: ['<10.10.10.0/24>',
            '<10.10.20.0/24>'].
        command_type (Union[Unset, str]):
    """

    source_region: str
    destination_region: str
    aws_account_id: str
    vpc_id: str
    provider: Union[Unset, str] = UNSET
    subscription_id: Union[Unset, int] = UNSET
    vpc_cidr: Union[Unset, str] = UNSET
    vpc_cidrs: Union[Unset, list[str]] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source_region = self.source_region

        destination_region = self.destination_region

        aws_account_id = self.aws_account_id

        vpc_id = self.vpc_id

        provider = self.provider

        subscription_id = self.subscription_id

        vpc_cidr = self.vpc_cidr

        vpc_cidrs: Union[Unset, list[str]] = UNSET
        if not isinstance(self.vpc_cidrs, Unset):
            vpc_cidrs = self.vpc_cidrs

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sourceRegion": source_region,
                "destinationRegion": destination_region,
                "awsAccountId": aws_account_id,
                "vpcId": vpc_id,
            }
        )
        if provider is not UNSET:
            field_dict["provider"] = provider
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if vpc_cidr is not UNSET:
            field_dict["vpcCidr"] = vpc_cidr
        if vpc_cidrs is not UNSET:
            field_dict["vpcCidrs"] = vpc_cidrs
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        source_region = d.pop("sourceRegion")

        destination_region = d.pop("destinationRegion")

        aws_account_id = d.pop("awsAccountId")

        vpc_id = d.pop("vpcId")

        provider = d.pop("provider", UNSET)

        subscription_id = d.pop("subscriptionId", UNSET)

        vpc_cidr = d.pop("vpcCidr", UNSET)

        vpc_cidrs = cast(list[str], d.pop("vpcCidrs", UNSET))

        command_type = d.pop("commandType", UNSET)

        active_active_vpc_peering_create_aws_request = cls(
            source_region=source_region,
            destination_region=destination_region,
            aws_account_id=aws_account_id,
            vpc_id=vpc_id,
            provider=provider,
            subscription_id=subscription_id,
            vpc_cidr=vpc_cidr,
            vpc_cidrs=vpc_cidrs,
            command_type=command_type,
        )

        active_active_vpc_peering_create_aws_request.additional_properties = d
        return active_active_vpc_peering_create_aws_request

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

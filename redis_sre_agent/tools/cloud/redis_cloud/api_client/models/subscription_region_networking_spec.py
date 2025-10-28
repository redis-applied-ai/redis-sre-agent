from collections.abc import Mapping
from typing import Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SubscriptionRegionNetworkingSpec")


@_attrs_define
class SubscriptionRegionNetworkingSpec:
    """Optional. Cloud networking details, per region. Required if creating an Active-Active subscription.

    Attributes:
        deployment_cidr (Union[Unset, str]): Optional. Deployment CIDR mask. Must be a valid CIDR format with a range of
            256 IP addresses. Default for single-region subscriptions: If using Redis internal cloud account, 192.168.0.0/24
            Example: 10.0.0.0/24.
        vpc_id (Union[Unset, str]): Optional. Enter a VPC identifier that exists in the hosted AWS account. Creates a
            new VPC if not set. VPC Identifier must be in a valid format (for example: 'vpc-0125be68a4625884ad') and must
            exist within the hosting account. Example: <vpc-identifier>.
        subnet_ids (Union[Unset, list[str]]): Optional. Enter a list of subnets identifiers that exists in the hosted
            AWS account. Subnet Identifier must exist within the hosting account.
        security_group_id (Union[Unset, str]): Optional. Enter a security group identifier that exists in the hosted AWS
            account. Security group Identifier must be in a valid format (for example: 'sg-0125be68a4625884ad') and must
            exist within the hosting account.
    """

    deployment_cidr: Union[Unset, str] = UNSET
    vpc_id: Union[Unset, str] = UNSET
    subnet_ids: Union[Unset, list[str]] = UNSET
    security_group_id: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        deployment_cidr = self.deployment_cidr

        vpc_id = self.vpc_id

        subnet_ids: Union[Unset, list[str]] = UNSET
        if not isinstance(self.subnet_ids, Unset):
            subnet_ids = self.subnet_ids

        security_group_id = self.security_group_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if deployment_cidr is not UNSET:
            field_dict["deploymentCIDR"] = deployment_cidr
        if vpc_id is not UNSET:
            field_dict["vpcId"] = vpc_id
        if subnet_ids is not UNSET:
            field_dict["subnetIds"] = subnet_ids
        if security_group_id is not UNSET:
            field_dict["securityGroupId"] = security_group_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        deployment_cidr = d.pop("deploymentCIDR", UNSET)

        vpc_id = d.pop("vpcId", UNSET)

        subnet_ids = cast(list[str], d.pop("subnetIds", UNSET))

        security_group_id = d.pop("securityGroupId", UNSET)

        subscription_region_networking_spec = cls(
            deployment_cidr=deployment_cidr,
            vpc_id=vpc_id,
            subnet_ids=subnet_ids,
            security_group_id=security_group_id,
        )

        subscription_region_networking_spec.additional_properties = d
        return subscription_region_networking_spec

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

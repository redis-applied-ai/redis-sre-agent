from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.active_active_region_create_request_resp_version import ActiveActiveRegionCreateRequestRespVersion
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.crdb_region_spec import CrdbRegionSpec


T = TypeVar("T", bound="ActiveActiveRegionCreateRequest")


@_attrs_define
class ActiveActiveRegionCreateRequest:
    """Active active region creation request message

    Attributes:
        subscription_id (Union[Unset, int]):
        region (Union[Unset, str]): Name of region to add as defined by the cloud provider.
        vpc_id (Union[Unset, str]): Optional. Enter a VPC identifier that exists in the hosted AWS account. Creates a
            new VPC if not set. VPC Identifier must be in a valid format and must exist within the hosting account. Example:
            vpc-0125be68a4625884ad.
        deployment_cidr (Union[Unset, str]): Deployment CIDR mask. Must be a valid CIDR format with a range of 256 IP
            addresses. Example: 10.0.0.0/24.
        subnet_ids (Union[Unset, list[str]]): Optional. Enter a list of subnets identifiers that exists in the hosted
            AWS account. Subnet Identifier must exist within the hosting account. Example: ['subnet-0125be68a4625884ad',
            'subnet-0125be68a4625884ad','subnet-0125be68a4625884ad'].
        security_group_id (Union[Unset, str]): Optional. Enter a security group identifier that exists in the hosted AWS
            account. Security group Identifier must be in a valid format (for example: 'sg-0125be68a4625884ad') and must
            exist within the hosting account. Example: sg-0125be68a4625884ad.
        dry_run (Union[Unset, bool]): Optional. When 'false': Creates a deployment plan and deploys it, creating any
            resources required by the plan. When 'true': creates a read-only deployment plan, and does not create any
            resources. Default: 'false'
        databases (Union[Unset, list['CrdbRegionSpec']]): List of databases in the subscription with local throughput
            details. Default: 1000 read and write ops/sec for each database
        resp_version (Union[Unset, ActiveActiveRegionCreateRequestRespVersion]): Optional. RESP version must be
            compatible with Redis version. Example: resp3.
        customer_managed_key_resource_name (Union[Unset, str]): Optional. Resource name of the customer managed key as
            defined by the cloud provider for customer managed subscriptions. Example:
            projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME.
        command_type (Union[Unset, str]):
    """

    subscription_id: Union[Unset, int] = UNSET
    region: Union[Unset, str] = UNSET
    vpc_id: Union[Unset, str] = UNSET
    deployment_cidr: Union[Unset, str] = UNSET
    subnet_ids: Union[Unset, list[str]] = UNSET
    security_group_id: Union[Unset, str] = UNSET
    dry_run: Union[Unset, bool] = UNSET
    databases: Union[Unset, list["CrdbRegionSpec"]] = UNSET
    resp_version: Union[Unset, ActiveActiveRegionCreateRequestRespVersion] = UNSET
    customer_managed_key_resource_name: Union[Unset, str] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        region = self.region

        vpc_id = self.vpc_id

        deployment_cidr = self.deployment_cidr

        subnet_ids: Union[Unset, list[str]] = UNSET
        if not isinstance(self.subnet_ids, Unset):
            subnet_ids = self.subnet_ids

        security_group_id = self.security_group_id

        dry_run = self.dry_run

        databases: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.databases, Unset):
            databases = []
            for databases_item_data in self.databases:
                databases_item = databases_item_data.to_dict()
                databases.append(databases_item)

        resp_version: Union[Unset, str] = UNSET
        if not isinstance(self.resp_version, Unset):
            resp_version = self.resp_version.value

        customer_managed_key_resource_name = self.customer_managed_key_resource_name

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if region is not UNSET:
            field_dict["region"] = region
        if vpc_id is not UNSET:
            field_dict["vpcId"] = vpc_id
        if deployment_cidr is not UNSET:
            field_dict["deploymentCIDR"] = deployment_cidr
        if subnet_ids is not UNSET:
            field_dict["subnetIds"] = subnet_ids
        if security_group_id is not UNSET:
            field_dict["securityGroupId"] = security_group_id
        if dry_run is not UNSET:
            field_dict["dryRun"] = dry_run
        if databases is not UNSET:
            field_dict["databases"] = databases
        if resp_version is not UNSET:
            field_dict["respVersion"] = resp_version
        if customer_managed_key_resource_name is not UNSET:
            field_dict["customerManagedKeyResourceName"] = customer_managed_key_resource_name
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.crdb_region_spec import CrdbRegionSpec

        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId", UNSET)

        region = d.pop("region", UNSET)

        vpc_id = d.pop("vpcId", UNSET)

        deployment_cidr = d.pop("deploymentCIDR", UNSET)

        subnet_ids = cast(list[str], d.pop("subnetIds", UNSET))

        security_group_id = d.pop("securityGroupId", UNSET)

        dry_run = d.pop("dryRun", UNSET)

        databases = []
        _databases = d.pop("databases", UNSET)
        for databases_item_data in _databases or []:
            databases_item = CrdbRegionSpec.from_dict(databases_item_data)

            databases.append(databases_item)

        _resp_version = d.pop("respVersion", UNSET)
        resp_version: Union[Unset, ActiveActiveRegionCreateRequestRespVersion]
        if isinstance(_resp_version, Unset):
            resp_version = UNSET
        else:
            resp_version = ActiveActiveRegionCreateRequestRespVersion(_resp_version)

        customer_managed_key_resource_name = d.pop("customerManagedKeyResourceName", UNSET)

        command_type = d.pop("commandType", UNSET)

        active_active_region_create_request = cls(
            subscription_id=subscription_id,
            region=region,
            vpc_id=vpc_id,
            deployment_cidr=deployment_cidr,
            subnet_ids=subnet_ids,
            security_group_id=security_group_id,
            dry_run=dry_run,
            databases=databases,
            resp_version=resp_version,
            customer_managed_key_resource_name=customer_managed_key_resource_name,
            command_type=command_type,
        )

        active_active_region_create_request.additional_properties = d
        return active_active_region_create_request

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

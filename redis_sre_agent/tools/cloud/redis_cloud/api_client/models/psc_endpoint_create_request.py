from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PscEndpointCreateRequest")


@_attrs_define
class PscEndpointCreateRequest:
    """Private Service Connect endpoint create request

    Attributes:
        subscription_id (int):
        psc_service_id (int):
        gcp_project_id (str): Google Cloud project ID. Example: my-gcp-project.
        gcp_vpc_name (str): Name of the Google Cloud VPC that hosts your application. Example: my-vpc.
        gcp_vpc_subnet_name (str): Name of your VPC's subnet of IP address ranges. Example: my-vpc-subnet.
        endpoint_connection_name (str): Prefix used to create PSC endpoints in the consumer application VPC. Endpoint
            names appear in Google Cloud as endpoint name prefix + endpoint number. Example: my-endpoint-connection.
        command_type (Union[Unset, str]):
    """

    subscription_id: int
    psc_service_id: int
    gcp_project_id: str
    gcp_vpc_name: str
    gcp_vpc_subnet_name: str
    endpoint_connection_name: str
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        psc_service_id = self.psc_service_id

        gcp_project_id = self.gcp_project_id

        gcp_vpc_name = self.gcp_vpc_name

        gcp_vpc_subnet_name = self.gcp_vpc_subnet_name

        endpoint_connection_name = self.endpoint_connection_name

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "subscriptionId": subscription_id,
                "pscServiceId": psc_service_id,
                "gcpProjectId": gcp_project_id,
                "gcpVpcName": gcp_vpc_name,
                "gcpVpcSubnetName": gcp_vpc_subnet_name,
                "endpointConnectionName": endpoint_connection_name,
            }
        )
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId")

        psc_service_id = d.pop("pscServiceId")

        gcp_project_id = d.pop("gcpProjectId")

        gcp_vpc_name = d.pop("gcpVpcName")

        gcp_vpc_subnet_name = d.pop("gcpVpcSubnetName")

        endpoint_connection_name = d.pop("endpointConnectionName")

        command_type = d.pop("commandType", UNSET)

        psc_endpoint_create_request = cls(
            subscription_id=subscription_id,
            psc_service_id=psc_service_id,
            gcp_project_id=gcp_project_id,
            gcp_vpc_name=gcp_vpc_name,
            gcp_vpc_subnet_name=gcp_vpc_subnet_name,
            endpoint_connection_name=endpoint_connection_name,
            command_type=command_type,
        )

        psc_endpoint_create_request.additional_properties = d
        return psc_endpoint_create_request

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

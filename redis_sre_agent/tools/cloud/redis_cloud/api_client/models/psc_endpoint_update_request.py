from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.psc_endpoint_update_request_action import PscEndpointUpdateRequestAction
from ..types import UNSET, Unset

T = TypeVar("T", bound="PscEndpointUpdateRequest")


@_attrs_define
class PscEndpointUpdateRequest:
    """Private Service Connect endpoint update request

    Attributes:
        subscription_id (int):
        psc_service_id (int):
        endpoint_id (int):
        gcp_project_id (Union[Unset, str]): Google Cloud project ID. Example: my-gcp-project.
        gcp_vpc_name (Union[Unset, str]): Name of the Google Cloud VPC that hosts your application. Example: my-vpc.
        gcp_vpc_subnet_name (Union[Unset, str]): Name of your VPC's subnet of IP address ranges. Example: my-vpc-subnet.
        endpoint_connection_name (Union[Unset, str]): Prefix used to create PSC endpoints in the consumer application
            VPC. Endpoint names appear in Google Cloud as endpoint name prefix + endpoint number. Example: my-endpoint-
            connection.
        action (Union[Unset, PscEndpointUpdateRequestAction]): Action to perform on the endpoint.
        command_type (Union[Unset, str]):
    """

    subscription_id: int
    psc_service_id: int
    endpoint_id: int
    gcp_project_id: Union[Unset, str] = UNSET
    gcp_vpc_name: Union[Unset, str] = UNSET
    gcp_vpc_subnet_name: Union[Unset, str] = UNSET
    endpoint_connection_name: Union[Unset, str] = UNSET
    action: Union[Unset, PscEndpointUpdateRequestAction] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        psc_service_id = self.psc_service_id

        endpoint_id = self.endpoint_id

        gcp_project_id = self.gcp_project_id

        gcp_vpc_name = self.gcp_vpc_name

        gcp_vpc_subnet_name = self.gcp_vpc_subnet_name

        endpoint_connection_name = self.endpoint_connection_name

        action: Union[Unset, str] = UNSET
        if not isinstance(self.action, Unset):
            action = self.action.value

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "subscriptionId": subscription_id,
                "pscServiceId": psc_service_id,
                "endpointId": endpoint_id,
            }
        )
        if gcp_project_id is not UNSET:
            field_dict["gcpProjectId"] = gcp_project_id
        if gcp_vpc_name is not UNSET:
            field_dict["gcpVpcName"] = gcp_vpc_name
        if gcp_vpc_subnet_name is not UNSET:
            field_dict["gcpVpcSubnetName"] = gcp_vpc_subnet_name
        if endpoint_connection_name is not UNSET:
            field_dict["endpointConnectionName"] = endpoint_connection_name
        if action is not UNSET:
            field_dict["action"] = action
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId")

        psc_service_id = d.pop("pscServiceId")

        endpoint_id = d.pop("endpointId")

        gcp_project_id = d.pop("gcpProjectId", UNSET)

        gcp_vpc_name = d.pop("gcpVpcName", UNSET)

        gcp_vpc_subnet_name = d.pop("gcpVpcSubnetName", UNSET)

        endpoint_connection_name = d.pop("endpointConnectionName", UNSET)

        _action = d.pop("action", UNSET)
        action: Union[Unset, PscEndpointUpdateRequestAction]
        if isinstance(_action, Unset):
            action = UNSET
        else:
            action = PscEndpointUpdateRequestAction(_action)

        command_type = d.pop("commandType", UNSET)

        psc_endpoint_update_request = cls(
            subscription_id=subscription_id,
            psc_service_id=psc_service_id,
            endpoint_id=endpoint_id,
            gcp_project_id=gcp_project_id,
            gcp_vpc_name=gcp_vpc_name,
            gcp_vpc_subnet_name=gcp_vpc_subnet_name,
            endpoint_connection_name=endpoint_connection_name,
            action=action,
            command_type=command_type,
        )

        psc_endpoint_update_request.additional_properties = d
        return psc_endpoint_update_request

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

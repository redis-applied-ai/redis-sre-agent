from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.private_link_active_active_create_request_type import PrivateLinkActiveActiveCreateRequestType
from ..types import UNSET, Unset

T = TypeVar("T", bound="PrivateLinkActiveActiveCreateRequest")


@_attrs_define
class PrivateLinkActiveActiveCreateRequest:
    """Request to create a private link for Active-Active subscription

    Attributes:
        region_id (int): Deployment region id as defined by cloud provider Example: 27.
        share_name (str): Name for the resource share Example: my-private-link-share.
        principal (str): AWS account ID or ARN of the principal (IAM user, role, or account) Example: 123456789012.
        type_ (PrivateLinkActiveActiveCreateRequestType): Type of the principal Example: aws_account.
        subscription_id (Union[Unset, int]):
        alias (Union[Unset, str]): Alias or friendly name for the principal Example: Production Account.
        command_type (Union[Unset, str]):
    """

    region_id: int
    share_name: str
    principal: str
    type_: PrivateLinkActiveActiveCreateRequestType
    subscription_id: Union[Unset, int] = UNSET
    alias: Union[Unset, str] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        region_id = self.region_id

        share_name = self.share_name

        principal = self.principal

        type_ = self.type_.value

        subscription_id = self.subscription_id

        alias = self.alias

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "regionId": region_id,
                "shareName": share_name,
                "principal": principal,
                "type": type_,
            }
        )
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if alias is not UNSET:
            field_dict["alias"] = alias
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        region_id = d.pop("regionId")

        share_name = d.pop("shareName")

        principal = d.pop("principal")

        type_ = PrivateLinkActiveActiveCreateRequestType(d.pop("type"))

        subscription_id = d.pop("subscriptionId", UNSET)

        alias = d.pop("alias", UNSET)

        command_type = d.pop("commandType", UNSET)

        private_link_active_active_create_request = cls(
            region_id=region_id,
            share_name=share_name,
            principal=principal,
            type_=type_,
            subscription_id=subscription_id,
            alias=alias,
            command_type=command_type,
        )

        private_link_active_active_create_request.additional_properties = d
        return private_link_active_active_create_request

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

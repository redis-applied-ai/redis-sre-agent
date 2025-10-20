from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.private_link_active_active_principals_create_request_type import (
    PrivateLinkActiveActivePrincipalsCreateRequestType,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="PrivateLinkActiveActivePrincipalsCreateRequest")


@_attrs_define
class PrivateLinkActiveActivePrincipalsCreateRequest:
    """Request to add a principal to private link for Active-Active subscription

    Attributes:
        region_id (int): Deployment region id as defined by cloud provider Example: 27.
        principal (str): AWS account ID or ARN of the principal (IAM user, role, or account) Example: 123456789012.
        subscription_id (Union[Unset, int]):
        type_ (Union[Unset, PrivateLinkActiveActivePrincipalsCreateRequestType]): Type of the principal Example:
            aws_account.
        alias (Union[Unset, str]): Alias or friendly name for the principal Example: Production Account.
        command_type (Union[Unset, str]):
    """

    region_id: int
    principal: str
    subscription_id: Union[Unset, int] = UNSET
    type_: Union[Unset, PrivateLinkActiveActivePrincipalsCreateRequestType] = UNSET
    alias: Union[Unset, str] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        region_id = self.region_id

        principal = self.principal

        subscription_id = self.subscription_id

        type_: Union[Unset, str] = UNSET
        if not isinstance(self.type_, Unset):
            type_ = self.type_.value

        alias = self.alias

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "regionId": region_id,
                "principal": principal,
            }
        )
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if type_ is not UNSET:
            field_dict["type"] = type_
        if alias is not UNSET:
            field_dict["alias"] = alias
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        region_id = d.pop("regionId")

        principal = d.pop("principal")

        subscription_id = d.pop("subscriptionId", UNSET)

        _type_ = d.pop("type", UNSET)
        type_: Union[Unset, PrivateLinkActiveActivePrincipalsCreateRequestType]
        if isinstance(_type_, Unset):
            type_ = UNSET
        else:
            type_ = PrivateLinkActiveActivePrincipalsCreateRequestType(_type_)

        alias = d.pop("alias", UNSET)

        command_type = d.pop("commandType", UNSET)

        private_link_active_active_principals_create_request = cls(
            region_id=region_id,
            principal=principal,
            subscription_id=subscription_id,
            type_=type_,
            alias=alias,
            command_type=command_type,
        )

        private_link_active_active_principals_create_request.additional_properties = d
        return private_link_active_active_principals_create_request

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

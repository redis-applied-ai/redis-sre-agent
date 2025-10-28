from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.private_link_principals_create_request_type import PrivateLinkPrincipalsCreateRequestType
from ..types import UNSET, Unset

T = TypeVar("T", bound="PrivateLinkPrincipalsCreateRequest")


@_attrs_define
class PrivateLinkPrincipalsCreateRequest:
    """Private Link principals create request

    Attributes:
        principal (str): AWS account ID or ARN of the principal (IAM user, role, or account) Example: 123456789012.
        subscription_id (Union[Unset, int]):
        type_ (Union[Unset, PrivateLinkPrincipalsCreateRequestType]): Type of the principal Example: aws_account.
        alias (Union[Unset, str]): Alias or friendly name for the principal Example: Production Account.
        command_type (Union[Unset, str]):
    """

    principal: str
    subscription_id: Union[Unset, int] = UNSET
    type_: Union[Unset, PrivateLinkPrincipalsCreateRequestType] = UNSET
    alias: Union[Unset, str] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
        principal = d.pop("principal")

        subscription_id = d.pop("subscriptionId", UNSET)

        _type_ = d.pop("type", UNSET)
        type_: Union[Unset, PrivateLinkPrincipalsCreateRequestType]
        if isinstance(_type_, Unset):
            type_ = UNSET
        else:
            type_ = PrivateLinkPrincipalsCreateRequestType(_type_)

        alias = d.pop("alias", UNSET)

        command_type = d.pop("commandType", UNSET)

        private_link_principals_create_request = cls(
            principal=principal,
            subscription_id=subscription_id,
            type_=type_,
            alias=alias,
            command_type=command_type,
        )

        private_link_principals_create_request.additional_properties = d
        return private_link_principals_create_request

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

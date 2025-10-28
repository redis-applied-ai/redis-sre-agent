from collections.abc import Mapping
from typing import Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CidrWhiteListUpdateRequest")


@_attrs_define
class CidrWhiteListUpdateRequest:
    """Update Pro subscription

    Attributes:
        subscription_id (Union[Unset, int]):
        cidr_ips (Union[Unset, list[str]]): List of CIDR values. Example: ['10.1.1.0/32']
        security_group_ids (Union[Unset, list[str]]): List of AWS Security group IDs.
        command_type (Union[Unset, str]):
    """

    subscription_id: Union[Unset, int] = UNSET
    cidr_ips: Union[Unset, list[str]] = UNSET
    security_group_ids: Union[Unset, list[str]] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        cidr_ips: Union[Unset, list[str]] = UNSET
        if not isinstance(self.cidr_ips, Unset):
            cidr_ips = self.cidr_ips

        security_group_ids: Union[Unset, list[str]] = UNSET
        if not isinstance(self.security_group_ids, Unset):
            security_group_ids = self.security_group_ids

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if subscription_id is not UNSET:
            field_dict["subscriptionId"] = subscription_id
        if cidr_ips is not UNSET:
            field_dict["cidrIps"] = cidr_ips
        if security_group_ids is not UNSET:
            field_dict["securityGroupIds"] = security_group_ids
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId", UNSET)

        cidr_ips = cast(list[str], d.pop("cidrIps", UNSET))

        security_group_ids = cast(list[str], d.pop("securityGroupIds", UNSET))

        command_type = d.pop("commandType", UNSET)

        cidr_white_list_update_request = cls(
            subscription_id=subscription_id,
            cidr_ips=cidr_ips,
            security_group_ids=security_group_ids,
            command_type=command_type,
        )

        cidr_white_list_update_request.additional_properties = d
        return cidr_white_list_update_request

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

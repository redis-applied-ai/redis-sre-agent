import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="AccountSystemLogEntry")


@_attrs_define
class AccountSystemLogEntry:
    """Account system log entry

    Attributes:
        id (Union[Unset, int]):
        time (Union[Unset, datetime.datetime]):
        originator (Union[Unset, str]):
        api_key_name (Union[Unset, str]):
        resource (Union[Unset, str]):
        resource_id (Union[Unset, int]):
        type_ (Union[Unset, str]):
        description (Union[Unset, str]):
    """

    id: Union[Unset, int] = UNSET
    time: Union[Unset, datetime.datetime] = UNSET
    originator: Union[Unset, str] = UNSET
    api_key_name: Union[Unset, str] = UNSET
    resource: Union[Unset, str] = UNSET
    resource_id: Union[Unset, int] = UNSET
    type_: Union[Unset, str] = UNSET
    description: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        time: Union[Unset, str] = UNSET
        if not isinstance(self.time, Unset):
            time = self.time.isoformat()

        originator = self.originator

        api_key_name = self.api_key_name

        resource = self.resource

        resource_id = self.resource_id

        type_ = self.type_

        description = self.description

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if time is not UNSET:
            field_dict["time"] = time
        if originator is not UNSET:
            field_dict["originator"] = originator
        if api_key_name is not UNSET:
            field_dict["apiKeyName"] = api_key_name
        if resource is not UNSET:
            field_dict["resource"] = resource
        if resource_id is not UNSET:
            field_dict["resourceId"] = resource_id
        if type_ is not UNSET:
            field_dict["type"] = type_
        if description is not UNSET:
            field_dict["description"] = description

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id", UNSET)

        _time = d.pop("time", UNSET)
        time: Union[Unset, datetime.datetime]
        if isinstance(_time, Unset):
            time = UNSET
        else:
            time = isoparse(_time)

        originator = d.pop("originator", UNSET)

        api_key_name = d.pop("apiKeyName", UNSET)

        resource = d.pop("resource", UNSET)

        resource_id = d.pop("resourceId", UNSET)

        type_ = d.pop("type", UNSET)

        description = d.pop("description", UNSET)

        account_system_log_entry = cls(
            id=id,
            time=time,
            originator=originator,
            api_key_name=api_key_name,
            resource=resource,
            resource_id=resource_id,
            type_=type_,
            description=description,
        )

        account_system_log_entry.additional_properties = d
        return account_system_log_entry

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

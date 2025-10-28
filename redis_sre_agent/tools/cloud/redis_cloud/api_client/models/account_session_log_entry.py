import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="AccountSessionLogEntry")


@_attrs_define
class AccountSessionLogEntry:
    """Account session log entry

    Attributes:
        id (Union[Unset, str]):
        time (Union[Unset, datetime.datetime]):
        user (Union[Unset, str]):
        user_agent (Union[Unset, str]):
        ip_address (Union[Unset, str]):
        user_role (Union[Unset, str]):
        type_ (Union[Unset, str]):
        action (Union[Unset, str]):
    """

    id: Union[Unset, str] = UNSET
    time: Union[Unset, datetime.datetime] = UNSET
    user: Union[Unset, str] = UNSET
    user_agent: Union[Unset, str] = UNSET
    ip_address: Union[Unset, str] = UNSET
    user_role: Union[Unset, str] = UNSET
    type_: Union[Unset, str] = UNSET
    action: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        time: Union[Unset, str] = UNSET
        if not isinstance(self.time, Unset):
            time = self.time.isoformat()

        user = self.user

        user_agent = self.user_agent

        ip_address = self.ip_address

        user_role = self.user_role

        type_ = self.type_

        action = self.action

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if time is not UNSET:
            field_dict["time"] = time
        if user is not UNSET:
            field_dict["user"] = user
        if user_agent is not UNSET:
            field_dict["userAgent"] = user_agent
        if ip_address is not UNSET:
            field_dict["ipAddress"] = ip_address
        if user_role is not UNSET:
            field_dict["userRole"] = user_role
        if type_ is not UNSET:
            field_dict["type"] = type_
        if action is not UNSET:
            field_dict["action"] = action

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

        user = d.pop("user", UNSET)

        user_agent = d.pop("userAgent", UNSET)

        ip_address = d.pop("ipAddress", UNSET)

        user_role = d.pop("userRole", UNSET)

        type_ = d.pop("type", UNSET)

        action = d.pop("action", UNSET)

        account_session_log_entry = cls(
            id=id,
            time=time,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
            user_role=user_role,
            type_=type_,
            action=action,
        )

        account_session_log_entry.additional_properties = d
        return account_session_log_entry

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

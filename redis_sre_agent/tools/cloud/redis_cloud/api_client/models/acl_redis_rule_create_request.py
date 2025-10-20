from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AclRedisRuleCreateRequest")


@_attrs_define
class AclRedisRuleCreateRequest:
    """ACL redis rule create request

    Attributes:
        name (str): Redis ACL rule name. Example: ACL-rule-example.
        redis_rule (str): Redis ACL rule pattern. See [ACL
            syntax](https://redis.io/docs/latest/operate/rc/security/access-control/data-access-control/configure-
            acls/#define-permissions-with-acl-syntax) to learn how to define rules. Example: +set allkeys allchannels.
        command_type (Union[Unset, str]):
    """

    name: str
    redis_rule: str
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        redis_rule = self.redis_rule

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "redisRule": redis_rule,
            }
        )
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        redis_rule = d.pop("redisRule")

        command_type = d.pop("commandType", UNSET)

        acl_redis_rule_create_request = cls(
            name=name,
            redis_rule=redis_rule,
            command_type=command_type,
        )

        acl_redis_rule_create_request.additional_properties = d
        return acl_redis_rule_create_request

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

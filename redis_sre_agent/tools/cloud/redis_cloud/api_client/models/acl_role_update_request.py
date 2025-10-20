from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.acl_role_redis_rule_spec import AclRoleRedisRuleSpec


T = TypeVar("T", bound="AclRoleUpdateRequest")


@_attrs_define
class AclRoleUpdateRequest:
    """ACL role update request

    Attributes:
        name (Union[Unset, str]): Optional. Changes the database access role name. Example: ACL-role-example.
        redis_rules (Union[Unset, list['AclRoleRedisRuleSpec']]): Optional. Changes the Redis ACL rules to assign to
            this database access role.
        role_id (Union[Unset, int]):
        command_type (Union[Unset, str]):
    """

    name: Union[Unset, str] = UNSET
    redis_rules: Union[Unset, list["AclRoleRedisRuleSpec"]] = UNSET
    role_id: Union[Unset, int] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        redis_rules: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.redis_rules, Unset):
            redis_rules = []
            for redis_rules_item_data in self.redis_rules:
                redis_rules_item = redis_rules_item_data.to_dict()
                redis_rules.append(redis_rules_item)

        role_id = self.role_id

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if redis_rules is not UNSET:
            field_dict["redisRules"] = redis_rules
        if role_id is not UNSET:
            field_dict["roleId"] = role_id
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.acl_role_redis_rule_spec import AclRoleRedisRuleSpec

        d = dict(src_dict)
        name = d.pop("name", UNSET)

        redis_rules = []
        _redis_rules = d.pop("redisRules", UNSET)
        for redis_rules_item_data in _redis_rules or []:
            redis_rules_item = AclRoleRedisRuleSpec.from_dict(redis_rules_item_data)

            redis_rules.append(redis_rules_item)

        role_id = d.pop("roleId", UNSET)

        command_type = d.pop("commandType", UNSET)

        acl_role_update_request = cls(
            name=name,
            redis_rules=redis_rules,
            role_id=role_id,
            command_type=command_type,
        )

        acl_role_update_request.additional_properties = d
        return acl_role_update_request

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

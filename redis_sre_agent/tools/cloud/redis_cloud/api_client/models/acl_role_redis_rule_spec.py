from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.acl_role_database_spec import AclRoleDatabaseSpec


T = TypeVar("T", bound="AclRoleRedisRuleSpec")


@_attrs_define
class AclRoleRedisRuleSpec:
    """Optional. Changes the Redis ACL rules to assign to this database access role.

    Attributes:
        rule_name (str): The name of a Redis ACL rule to assign to the role. Use 'GET /acl/redisRules' to get a list of
            available rules for your account. Example: Read-Only.
        databases (list['AclRoleDatabaseSpec']): A list of databases where the specified rule applies for this role.
    """

    rule_name: str
    databases: list["AclRoleDatabaseSpec"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rule_name = self.rule_name

        databases = []
        for databases_item_data in self.databases:
            databases_item = databases_item_data.to_dict()
            databases.append(databases_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ruleName": rule_name,
                "databases": databases,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.acl_role_database_spec import AclRoleDatabaseSpec

        d = dict(src_dict)
        rule_name = d.pop("ruleName")

        databases = []
        _databases = d.pop("databases")
        for databases_item_data in _databases:
            databases_item = AclRoleDatabaseSpec.from_dict(databases_item_data)

            databases.append(databases_item)

        acl_role_redis_rule_spec = cls(
            rule_name=rule_name,
            databases=databases,
        )

        acl_role_redis_rule_spec.additional_properties = d
        return acl_role_redis_rule_spec

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

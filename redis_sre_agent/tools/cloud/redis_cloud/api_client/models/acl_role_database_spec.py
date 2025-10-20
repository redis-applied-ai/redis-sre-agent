from collections.abc import Mapping
from typing import Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AclRoleDatabaseSpec")


@_attrs_define
class AclRoleDatabaseSpec:
    """A list of databases where the specified rule applies for this role.

    Attributes:
        subscription_id (int): Subscription ID for the database's subscription. Use 'GET /subscriptions' or 'GET
            /fixed/subscriptions' to get a list of available subscriptions and their IDs.
        database_id (int): The database's ID. Use 'GET /subscriptions/{subscriptionId}/databases' or 'GET
            /fixed/subscriptions/{subscriptionId}/databases' to get a list of databases in a subscription and their IDs.
        regions (Union[Unset, list[str]]): (Active-Active databases only) Optional. A list of regions where this rule
            applies for this role.
    """

    subscription_id: int
    database_id: int
    regions: Union[Unset, list[str]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        subscription_id = self.subscription_id

        database_id = self.database_id

        regions: Union[Unset, list[str]] = UNSET
        if not isinstance(self.regions, Unset):
            regions = self.regions

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "subscriptionId": subscription_id,
                "databaseId": database_id,
            }
        )
        if regions is not UNSET:
            field_dict["regions"] = regions

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        subscription_id = d.pop("subscriptionId")

        database_id = d.pop("databaseId")

        regions = cast(list[str], d.pop("regions", UNSET))

        acl_role_database_spec = cls(
            subscription_id=subscription_id,
            database_id=database_id,
            regions=regions,
        )

        acl_role_database_spec.additional_properties = d
        return acl_role_database_spec

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

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.database_alert_spec_name import DatabaseAlertSpecName

T = TypeVar("T", bound="DatabaseAlertSpec")


@_attrs_define
class DatabaseAlertSpec:
    """Optional. Changes Redis database alert details.

    Attributes:
        name (DatabaseAlertSpecName): Alert type. Available options depend on Plan type. See [Configure
            alerts](https://redis.io/docs/latest/operate/rc/databases/monitor-performance/#configure-metric-alerts) for more
            information. Example: dataset-size.
        value (int): Value over which an alert will be sent. Default values and range depend on the alert type. See
            [Configure alerts](https://redis.io/docs/latest/operate/rc/databases/monitor-performance/#configure-metric-
            alerts) for more information. Example: 80.
    """

    name: DatabaseAlertSpecName
    value: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name.value

        value = self.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "value": value,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = DatabaseAlertSpecName(d.pop("name"))

        value = d.pop("value")

        database_alert_spec = cls(
            name=name,
            value=value,
        )

        database_alert_spec.additional_properties = d
        return database_alert_spec

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

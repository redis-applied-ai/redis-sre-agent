from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.database_module_spec_parameters import DatabaseModuleSpecParameters


T = TypeVar("T", bound="DatabaseModuleSpec")


@_attrs_define
class DatabaseModuleSpec:
    """Optional. Redis advanced capabilities (also known as modules) to be provisioned in the database. Use GET /database-
    modules to get a list of available advanced capabilities.

        Attributes:
            name (str): Redis advanced capability name. Use GET /database-modules for a list of available capabilities.
            parameters (Union[Unset, DatabaseModuleSpecParameters]): Optional. Redis advanced capability parameters. Use GET
                /database-modules to get the available capabilities and their parameters.
    """

    name: str
    parameters: Union[Unset, "DatabaseModuleSpecParameters"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        parameters: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.parameters, Unset):
            parameters = self.parameters.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
            }
        )
        if parameters is not UNSET:
            field_dict["parameters"] = parameters

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.database_module_spec_parameters import DatabaseModuleSpecParameters

        d = dict(src_dict)
        name = d.pop("name")

        _parameters = d.pop("parameters", UNSET)
        parameters: Union[Unset, DatabaseModuleSpecParameters]
        if isinstance(_parameters, Unset):
            parameters = UNSET
        else:
            parameters = DatabaseModuleSpecParameters.from_dict(_parameters)

        database_module_spec = cls(
            name=name,
            parameters=parameters,
        )

        database_module_spec.additional_properties = d
        return database_module_spec

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

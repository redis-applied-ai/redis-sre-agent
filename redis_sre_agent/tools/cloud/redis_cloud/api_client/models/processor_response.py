from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.processor_response_error import ProcessorResponseError
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.processor_response_resource import ProcessorResponseResource


T = TypeVar("T", bound="ProcessorResponse")


@_attrs_define
class ProcessorResponse:
    """
    Attributes:
        resource_id (Union[Unset, int]):
        additional_resource_id (Union[Unset, int]):
        resource (Union[Unset, ProcessorResponseResource]):
        error (Union[Unset, ProcessorResponseError]):
        additional_info (Union[Unset, str]):
    """

    resource_id: Union[Unset, int] = UNSET
    additional_resource_id: Union[Unset, int] = UNSET
    resource: Union[Unset, "ProcessorResponseResource"] = UNSET
    error: Union[Unset, ProcessorResponseError] = UNSET
    additional_info: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        resource_id = self.resource_id

        additional_resource_id = self.additional_resource_id

        resource: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.resource, Unset):
            resource = self.resource.to_dict()

        error: Union[Unset, str] = UNSET
        if not isinstance(self.error, Unset):
            error = self.error.value

        additional_info = self.additional_info

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if resource_id is not UNSET:
            field_dict["resourceId"] = resource_id
        if additional_resource_id is not UNSET:
            field_dict["additionalResourceId"] = additional_resource_id
        if resource is not UNSET:
            field_dict["resource"] = resource
        if error is not UNSET:
            field_dict["error"] = error
        if additional_info is not UNSET:
            field_dict["additionalInfo"] = additional_info

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.processor_response_resource import ProcessorResponseResource

        d = dict(src_dict)
        resource_id = d.pop("resourceId", UNSET)

        additional_resource_id = d.pop("additionalResourceId", UNSET)

        _resource = d.pop("resource", UNSET)
        resource: Union[Unset, ProcessorResponseResource]
        if isinstance(_resource, Unset):
            resource = UNSET
        else:
            resource = ProcessorResponseResource.from_dict(_resource)

        _error = d.pop("error", UNSET)
        error: Union[Unset, ProcessorResponseError]
        if isinstance(_error, Unset):
            error = UNSET
        else:
            error = ProcessorResponseError(_error)

        additional_info = d.pop("additionalInfo", UNSET)

        processor_response = cls(
            resource_id=resource_id,
            additional_resource_id=additional_resource_id,
            resource=resource,
            error=error,
            additional_info=additional_info,
        )

        processor_response.additional_properties = d
        return processor_response

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

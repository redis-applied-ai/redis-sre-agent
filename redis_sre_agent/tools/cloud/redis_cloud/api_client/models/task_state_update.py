import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.task_state_update_status import TaskStateUpdateStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.processor_response import ProcessorResponse
    from ..models.task_state_update_links_item import TaskStateUpdateLinksItem


T = TypeVar("T", bound="TaskStateUpdate")


@_attrs_define
class TaskStateUpdate:
    """
    Attributes:
        task_id (Union[Unset, UUID]):
        command_type (Union[Unset, str]):
        status (Union[Unset, TaskStateUpdateStatus]):
        description (Union[Unset, str]):
        timestamp (Union[Unset, datetime.datetime]):
        response (Union[Unset, ProcessorResponse]):
        links (Union[Unset, list['TaskStateUpdateLinksItem']]):
    """

    task_id: Union[Unset, UUID] = UNSET
    command_type: Union[Unset, str] = UNSET
    status: Union[Unset, TaskStateUpdateStatus] = UNSET
    description: Union[Unset, str] = UNSET
    timestamp: Union[Unset, datetime.datetime] = UNSET
    response: Union[Unset, "ProcessorResponse"] = UNSET
    links: Union[Unset, list["TaskStateUpdateLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_id: Union[Unset, str] = UNSET
        if not isinstance(self.task_id, Unset):
            task_id = str(self.task_id)

        command_type = self.command_type

        status: Union[Unset, str] = UNSET
        if not isinstance(self.status, Unset):
            status = self.status.value

        description = self.description

        timestamp: Union[Unset, str] = UNSET
        if not isinstance(self.timestamp, Unset):
            timestamp = self.timestamp.isoformat()

        response: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.response, Unset):
            response = self.response.to_dict()

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if task_id is not UNSET:
            field_dict["taskId"] = task_id
        if command_type is not UNSET:
            field_dict["commandType"] = command_type
        if status is not UNSET:
            field_dict["status"] = status
        if description is not UNSET:
            field_dict["description"] = description
        if timestamp is not UNSET:
            field_dict["timestamp"] = timestamp
        if response is not UNSET:
            field_dict["response"] = response
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.processor_response import ProcessorResponse
        from ..models.task_state_update_links_item import TaskStateUpdateLinksItem

        d = dict(src_dict)
        _task_id = d.pop("taskId", UNSET)
        task_id: Union[Unset, UUID]
        if isinstance(_task_id, Unset):
            task_id = UNSET
        else:
            task_id = UUID(_task_id)

        command_type = d.pop("commandType", UNSET)

        _status = d.pop("status", UNSET)
        status: Union[Unset, TaskStateUpdateStatus]
        if isinstance(_status, Unset):
            status = UNSET
        else:
            status = TaskStateUpdateStatus(_status)

        description = d.pop("description", UNSET)

        _timestamp = d.pop("timestamp", UNSET)
        timestamp: Union[Unset, datetime.datetime]
        if isinstance(_timestamp, Unset):
            timestamp = UNSET
        else:
            timestamp = isoparse(_timestamp)

        _response = d.pop("response", UNSET)
        response: Union[Unset, ProcessorResponse]
        if isinstance(_response, Unset):
            response = UNSET
        else:
            response = ProcessorResponse.from_dict(_response)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = TaskStateUpdateLinksItem.from_dict(links_item_data)

            links.append(links_item)

        task_state_update = cls(
            task_id=task_id,
            command_type=command_type,
            status=status,
            description=description,
            timestamp=timestamp,
            response=response,
            links=links,
        )

        task_state_update.additional_properties = d
        return task_state_update

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

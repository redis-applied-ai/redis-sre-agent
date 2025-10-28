from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.account_system_log_entries_links_item import AccountSystemLogEntriesLinksItem
    from ..models.account_system_log_entry import AccountSystemLogEntry


T = TypeVar("T", bound="AccountSystemLogEntries")


@_attrs_define
class AccountSystemLogEntries:
    """
    Example:
        {'entries': [{'id': 2900349, 'time': '2022-10-12T10:54:31Z', 'originator': 'example-value', 'type': 'Account',
            'description': "example-value (example.value@redis.com)'s user name was changed to Example Value"}, {'id':
            2900348, 'time': '2022-10-12T10:54:11Z', 'originator': 'invalid-name', 'type': 'Account', 'description':
            'Invited invalid-name (cab@fufu.com) to join team'}]}

    Attributes:
        entries (Union[Unset, list['AccountSystemLogEntry']]):
        links (Union[Unset, list['AccountSystemLogEntriesLinksItem']]):
    """

    entries: Union[Unset, list["AccountSystemLogEntry"]] = UNSET
    links: Union[Unset, list["AccountSystemLogEntriesLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        entries: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.entries, Unset):
            entries = []
            for entries_item_data in self.entries:
                entries_item = entries_item_data.to_dict()
                entries.append(entries_item)

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if entries is not UNSET:
            field_dict["entries"] = entries
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.account_system_log_entries_links_item import AccountSystemLogEntriesLinksItem
        from ..models.account_system_log_entry import AccountSystemLogEntry

        d = dict(src_dict)
        entries = []
        _entries = d.pop("entries", UNSET)
        for entries_item_data in _entries or []:
            entries_item = AccountSystemLogEntry.from_dict(entries_item_data)

            entries.append(entries_item)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = AccountSystemLogEntriesLinksItem.from_dict(links_item_data)

            links.append(links_item)

        account_system_log_entries = cls(
            entries=entries,
            links=links,
        )

        account_system_log_entries.additional_properties = d
        return account_system_log_entries

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

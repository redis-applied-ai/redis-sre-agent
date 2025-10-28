from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.search_scaling_factors_data_links_item import SearchScalingFactorsDataLinksItem


T = TypeVar("T", bound="SearchScalingFactorsData")


@_attrs_define
class SearchScalingFactorsData:
    """
    Attributes:
        query_performance_factors (Union[Unset, list[str]]):
        links (Union[Unset, list['SearchScalingFactorsDataLinksItem']]):
    """

    query_performance_factors: Union[Unset, list[str]] = UNSET
    links: Union[Unset, list["SearchScalingFactorsDataLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        query_performance_factors: Union[Unset, list[str]] = UNSET
        if not isinstance(self.query_performance_factors, Unset):
            query_performance_factors = self.query_performance_factors

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if query_performance_factors is not UNSET:
            field_dict["queryPerformanceFactors"] = query_performance_factors
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.search_scaling_factors_data_links_item import SearchScalingFactorsDataLinksItem

        d = dict(src_dict)
        query_performance_factors = cast(list[str], d.pop("queryPerformanceFactors", UNSET))

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = SearchScalingFactorsDataLinksItem.from_dict(links_item_data)

            links.append(links_item)

        search_scaling_factors_data = cls(
            query_performance_factors=query_performance_factors,
            links=links,
        )

        search_scaling_factors_data.additional_properties = d
        return search_scaling_factors_data

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

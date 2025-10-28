from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.region import Region
    from ..models.regions_links_item import RegionsLinksItem


T = TypeVar("T", bound="Regions")


@_attrs_define
class Regions:
    """
    Example:
        {'regions': [{'name': 'us-east-1', 'provider': 'AWS'}, {'name': 'us-west-1', 'provider': 'AWS'}, {'name': 'us-
            west-2', 'provider': 'AWS'}, {'name': 'eu-west-1', 'provider': 'AWS'}, {'name': 'eu-central-1', 'provider':
            'AWS'}, {'name': 'ap-northeast-1', 'provider': 'AWS'}, {'name': 'ap-southeast-1', 'provider': 'AWS'}, {'name':
            'ap-southeast-2', 'provider': 'AWS'}, {'name': 'sa-east-1', 'provider': 'AWS'}, {'name': 'us-east-2',
            'provider': 'AWS'}, {'name': 'eu-west-2', 'provider': 'AWS'}, {'name': 'eu-west-3', 'provider': 'AWS'}, {'name':
            'eu-north-1', 'provider': 'AWS'}, {'name': 'ca-central-1', 'provider': 'AWS'}, {'name': 'ap-east-1', 'provider':
            'AWS'}, {'name': 'ap-south-1', 'provider': 'AWS'}, {'name': 'asia-east1', 'provider': 'GCP'}, {'name': 'asia-
            east2', 'provider': 'GCP'}, {'name': 'asia-northeast1', 'provider': 'GCP'}, {'name': 'asia-northeast2',
            'provider': 'GCP'}, {'name': 'asia-south1', 'provider': 'GCP'}, {'name': 'asia-southeast1', 'provider': 'GCP'},
            {'name': 'australia-southeast1', 'provider': 'GCP'}, {'name': 'europe-north1', 'provider': 'GCP'}, {'name':
            'europe-west1', 'provider': 'GCP'}, {'name': 'europe-west2', 'provider': 'GCP'}, {'name': 'europe-west3',
            'provider': 'GCP'}, {'name': 'europe-west4', 'provider': 'GCP'}, {'name': 'europe-west6', 'provider': 'GCP'},
            {'name': 'northamerica-northeast1', 'provider': 'GCP'}, {'name': 'southamerica-east1', 'provider': 'GCP'},
            {'name': 'us-central1', 'provider': 'GCP'}, {'name': 'us-east1', 'provider': 'GCP'}, {'name': 'us-east4',
            'provider': 'GCP'}, {'name': 'us-west1', 'provider': 'GCP'}, {'name': 'us-west2', 'provider': 'GCP'}]}

    Attributes:
        regions (Union[Unset, list['Region']]):
        links (Union[Unset, list['RegionsLinksItem']]):
    """

    regions: Union[Unset, list["Region"]] = UNSET
    links: Union[Unset, list["RegionsLinksItem"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        regions: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.regions, Unset):
            regions = []
            for regions_item_data in self.regions:
                regions_item = regions_item_data.to_dict()
                regions.append(regions_item)

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if regions is not UNSET:
            field_dict["regions"] = regions
        if links is not UNSET:
            field_dict["links"] = links

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.region import Region
        from ..models.regions_links_item import RegionsLinksItem

        d = dict(src_dict)
        regions = []
        _regions = d.pop("regions", UNSET)
        for regions_item_data in _regions or []:
            regions_item = Region.from_dict(regions_item_data)

            regions.append(regions_item)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = RegionsLinksItem.from_dict(links_item_data)

            links.append(links_item)

        regions = cls(
            regions=regions,
            links=links,
        )

        regions.additional_properties = d
        return regions

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

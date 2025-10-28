from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.cloud_account_provider import CloudAccountProvider
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.cloud_account_links_item import CloudAccountLinksItem


T = TypeVar("T", bound="CloudAccount")


@_attrs_define
class CloudAccount:
    """RedisLabs Cloud Account information

    Example:
        {'id': 1, 'name': 'Redis Internal Resources', 'provider': 'AWS', 'status': 'active', 'links': [{'rel': 'self',
            'href': 'https://api-cloudapi.qa.redislabs.com/v1/cloud-accounts/1', 'type': 'GET'}]}

    Attributes:
        id (Union[Unset, int]):
        name (Union[Unset, str]):
        status (Union[Unset, str]):
        access_key_id (Union[Unset, str]):
        sign_in_login_url (Union[Unset, str]):
        aws_user_arn (Union[Unset, str]):
        aws_console_role_arn (Union[Unset, str]):
        links (Union[Unset, list['CloudAccountLinksItem']]):
        provider (Union[Unset, CloudAccountProvider]):
    """

    id: Union[Unset, int] = UNSET
    name: Union[Unset, str] = UNSET
    status: Union[Unset, str] = UNSET
    access_key_id: Union[Unset, str] = UNSET
    sign_in_login_url: Union[Unset, str] = UNSET
    aws_user_arn: Union[Unset, str] = UNSET
    aws_console_role_arn: Union[Unset, str] = UNSET
    links: Union[Unset, list["CloudAccountLinksItem"]] = UNSET
    provider: Union[Unset, CloudAccountProvider] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        status = self.status

        access_key_id = self.access_key_id

        sign_in_login_url = self.sign_in_login_url

        aws_user_arn = self.aws_user_arn

        aws_console_role_arn = self.aws_console_role_arn

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        provider: Union[Unset, str] = UNSET
        if not isinstance(self.provider, Unset):
            provider = self.provider.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if name is not UNSET:
            field_dict["name"] = name
        if status is not UNSET:
            field_dict["status"] = status
        if access_key_id is not UNSET:
            field_dict["accessKeyId"] = access_key_id
        if sign_in_login_url is not UNSET:
            field_dict["signInLoginUrl"] = sign_in_login_url
        if aws_user_arn is not UNSET:
            field_dict["awsUserArn"] = aws_user_arn
        if aws_console_role_arn is not UNSET:
            field_dict["awsConsoleRoleArn"] = aws_console_role_arn
        if links is not UNSET:
            field_dict["links"] = links
        if provider is not UNSET:
            field_dict["provider"] = provider

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cloud_account_links_item import CloudAccountLinksItem

        d = dict(src_dict)
        id = d.pop("id", UNSET)

        name = d.pop("name", UNSET)

        status = d.pop("status", UNSET)

        access_key_id = d.pop("accessKeyId", UNSET)

        sign_in_login_url = d.pop("signInLoginUrl", UNSET)

        aws_user_arn = d.pop("awsUserArn", UNSET)

        aws_console_role_arn = d.pop("awsConsoleRoleArn", UNSET)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = CloudAccountLinksItem.from_dict(links_item_data)

            links.append(links_item)

        _provider = d.pop("provider", UNSET)
        provider: Union[Unset, CloudAccountProvider]
        if isinstance(_provider, Unset):
            provider = UNSET
        else:
            provider = CloudAccountProvider(_provider)

        cloud_account = cls(
            id=id,
            name=name,
            status=status,
            access_key_id=access_key_id,
            sign_in_login_url=sign_in_login_url,
            aws_user_arn=aws_user_arn,
            aws_console_role_arn=aws_console_role_arn,
            links=links,
            provider=provider,
        )

        cloud_account.additional_properties = d
        return cloud_account

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

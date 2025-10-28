from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.cloud_account_create_request_provider import CloudAccountCreateRequestProvider
from ..types import UNSET, Unset

T = TypeVar("T", bound="CloudAccountCreateRequest")


@_attrs_define
class CloudAccountCreateRequest:
    """Cloud Account definition

    Attributes:
        name (str): Cloud account display name. Example: My new Cloud Account.
        access_key_id (str): Cloud provider access key. Example: ****.
        access_secret_key (str): Cloud provider secret key. Example: ****.
        console_username (str): Cloud provider management console username. Example: me@mycompany.com.
        console_password (str): Cloud provider management console password. Example: ****.
        sign_in_login_url (str): Cloud provider management console login URL. Example: https://<aws-account-
            identifier>.signin.aws.amazon.com/console.
        provider (Union[Unset, CloudAccountCreateRequestProvider]): Optional. Cloud provider. Default: 'AWS' Example:
            AWS.
        command_type (Union[Unset, str]):
    """

    name: str
    access_key_id: str
    access_secret_key: str
    console_username: str
    console_password: str
    sign_in_login_url: str
    provider: Union[Unset, CloudAccountCreateRequestProvider] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        access_key_id = self.access_key_id

        access_secret_key = self.access_secret_key

        console_username = self.console_username

        console_password = self.console_password

        sign_in_login_url = self.sign_in_login_url

        provider: Union[Unset, str] = UNSET
        if not isinstance(self.provider, Unset):
            provider = self.provider.value

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "accessKeyId": access_key_id,
                "accessSecretKey": access_secret_key,
                "consoleUsername": console_username,
                "consolePassword": console_password,
                "signInLoginUrl": sign_in_login_url,
            }
        )
        if provider is not UNSET:
            field_dict["provider"] = provider
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        access_key_id = d.pop("accessKeyId")

        access_secret_key = d.pop("accessSecretKey")

        console_username = d.pop("consoleUsername")

        console_password = d.pop("consolePassword")

        sign_in_login_url = d.pop("signInLoginUrl")

        _provider = d.pop("provider", UNSET)
        provider: Union[Unset, CloudAccountCreateRequestProvider]
        if isinstance(_provider, Unset):
            provider = UNSET
        else:
            provider = CloudAccountCreateRequestProvider(_provider)

        command_type = d.pop("commandType", UNSET)

        cloud_account_create_request = cls(
            name=name,
            access_key_id=access_key_id,
            access_secret_key=access_secret_key,
            console_username=console_username,
            console_password=console_password,
            sign_in_login_url=sign_in_login_url,
            provider=provider,
            command_type=command_type,
        )

        cloud_account_create_request.additional_properties = d
        return cloud_account_create_request

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

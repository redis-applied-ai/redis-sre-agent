from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CloudAccountUpdateRequest")


@_attrs_define
class CloudAccountUpdateRequest:
    """Cloud Account definition

    Attributes:
        access_key_id (str): Cloud provider access key. Example: ****.
        access_secret_key (str): Cloud provider secret key. Example: ****.
        console_username (str): Cloud provider management console username. Example: me@mycompany.com.
        console_password (str): Cloud provider management console password. Example: ****.
        name (Union[Unset, str]): name Example: My new Cloud Account.
        cloud_account_id (Union[Unset, int]):
        sign_in_login_url (Union[Unset, str]): Optional. Cloud provider management console login URL. Example:
            https://<aws-account-identifier>.signin.aws.amazon.com/console.
        command_type (Union[Unset, str]):
    """

    access_key_id: str
    access_secret_key: str
    console_username: str
    console_password: str
    name: Union[Unset, str] = UNSET
    cloud_account_id: Union[Unset, int] = UNSET
    sign_in_login_url: Union[Unset, str] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        access_key_id = self.access_key_id

        access_secret_key = self.access_secret_key

        console_username = self.console_username

        console_password = self.console_password

        name = self.name

        cloud_account_id = self.cloud_account_id

        sign_in_login_url = self.sign_in_login_url

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "accessKeyId": access_key_id,
                "accessSecretKey": access_secret_key,
                "consoleUsername": console_username,
                "consolePassword": console_password,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name
        if cloud_account_id is not UNSET:
            field_dict["cloudAccountId"] = cloud_account_id
        if sign_in_login_url is not UNSET:
            field_dict["signInLoginUrl"] = sign_in_login_url
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        access_key_id = d.pop("accessKeyId")

        access_secret_key = d.pop("accessSecretKey")

        console_username = d.pop("consoleUsername")

        console_password = d.pop("consolePassword")

        name = d.pop("name", UNSET)

        cloud_account_id = d.pop("cloudAccountId", UNSET)

        sign_in_login_url = d.pop("signInLoginUrl", UNSET)

        command_type = d.pop("commandType", UNSET)

        cloud_account_update_request = cls(
            access_key_id=access_key_id,
            access_secret_key=access_secret_key,
            console_username=console_username,
            console_password=console_password,
            name=name,
            cloud_account_id=cloud_account_id,
            sign_in_login_url=sign_in_login_url,
            command_type=command_type,
        )

        cloud_account_update_request.additional_properties = d
        return cloud_account_update_request

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

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.account_user_options import AccountUserOptions


T = TypeVar("T", bound="AccountUser")


@_attrs_define
class AccountUser:
    """RedisLabs User information

    Example:
        {'id': 60192, 'name': "Clifford O'neill", 'email': 'clifford.mail@gmail.com', 'role': 'Viewer', 'userType':
            'Local', 'hasApiKey': False, 'options': {'billing': False, 'emailAlerts': False, 'operationalEmails': False,
            'mfaEnabled': False}}

    Attributes:
        id (Union[Unset, int]):
        name (Union[Unset, str]):
        email (Union[Unset, str]):
        role (Union[Unset, str]):
        sign_up (Union[Unset, str]):
        user_type (Union[Unset, str]):
        has_api_key (Union[Unset, bool]):
        options (Union[Unset, AccountUserOptions]): RedisLabs User options information
    """

    id: Union[Unset, int] = UNSET
    name: Union[Unset, str] = UNSET
    email: Union[Unset, str] = UNSET
    role: Union[Unset, str] = UNSET
    sign_up: Union[Unset, str] = UNSET
    user_type: Union[Unset, str] = UNSET
    has_api_key: Union[Unset, bool] = UNSET
    options: Union[Unset, "AccountUserOptions"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        email = self.email

        role = self.role

        sign_up = self.sign_up

        user_type = self.user_type

        has_api_key = self.has_api_key

        options: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.options, Unset):
            options = self.options.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if name is not UNSET:
            field_dict["name"] = name
        if email is not UNSET:
            field_dict["email"] = email
        if role is not UNSET:
            field_dict["role"] = role
        if sign_up is not UNSET:
            field_dict["signUp"] = sign_up
        if user_type is not UNSET:
            field_dict["userType"] = user_type
        if has_api_key is not UNSET:
            field_dict["hasApiKey"] = has_api_key
        if options is not UNSET:
            field_dict["options"] = options

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.account_user_options import AccountUserOptions

        d = dict(src_dict)
        id = d.pop("id", UNSET)

        name = d.pop("name", UNSET)

        email = d.pop("email", UNSET)

        role = d.pop("role", UNSET)

        sign_up = d.pop("signUp", UNSET)

        user_type = d.pop("userType", UNSET)

        has_api_key = d.pop("hasApiKey", UNSET)

        _options = d.pop("options", UNSET)
        options: Union[Unset, AccountUserOptions]
        if isinstance(_options, Unset):
            options = UNSET
        else:
            options = AccountUserOptions.from_dict(_options)

        account_user = cls(
            id=id,
            name=name,
            email=email,
            role=role,
            sign_up=sign_up,
            user_type=user_type,
            has_api_key=has_api_key,
            options=options,
        )

        account_user.additional_properties = d
        return account_user

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

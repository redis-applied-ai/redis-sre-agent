from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.subscription_create_request_deployment_type import SubscriptionCreateRequestDeploymentType
from ..models.subscription_create_request_memory_storage import SubscriptionCreateRequestMemoryStorage
from ..models.subscription_create_request_payment_method import SubscriptionCreateRequestPaymentMethod
from ..models.subscription_create_request_persistent_storage_encryption_type import (
    SubscriptionCreateRequestPersistentStorageEncryptionType,
)
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.customer_managed_key_properties import CustomerManagedKeyProperties
    from ..models.subscription_database_spec import SubscriptionDatabaseSpec
    from ..models.subscription_spec import SubscriptionSpec


T = TypeVar("T", bound="SubscriptionCreateRequest")


@_attrs_define
class SubscriptionCreateRequest:
    """Subscription create request

    Attributes:
        cloud_providers (list['SubscriptionSpec']): Cloud provider, region, and networking details.
        databases (list['SubscriptionDatabaseSpec']): One or more database specification(s) to create in this
            subscription.
        name (Union[Unset, str]): Optional. New subscription name. Example: My new subscription.
        dry_run (Union[Unset, bool]): Optional. When 'false': Creates a deployment plan and deploys it, creating any
            resources required by the plan. When 'true': creates a read-only deployment plan and does not create any
            resources. Default: 'false'
        deployment_type (Union[Unset, SubscriptionCreateRequestDeploymentType]): Optional. When 'single-region' or not
            set: Creates a single region subscription. When 'active-active': creates an Active-Active (multi-region)
            subscription. Example: single-region.
        payment_method (Union[Unset, SubscriptionCreateRequestPaymentMethod]): Optional. The payment method for the
            subscription. If set to ‘credit-card’, ‘paymentMethodId’ must be defined. Default: 'credit-card'
        payment_method_id (Union[Unset, int]): Optional. A valid payment method ID for this account. Use GET /payment-
            methods to get a list of all payment methods for your account. This value is optional if ‘paymentMethod’ is
            ‘marketplace’, but required for all other account types.
        memory_storage (Union[Unset, SubscriptionCreateRequestMemoryStorage]): Optional. Memory storage preference:
            either 'ram' or a combination of 'ram-and-flash' (also known as Auto Tiering). Default: 'ram' Example: ram.
        persistent_storage_encryption_type (Union[Unset, SubscriptionCreateRequestPersistentStorageEncryptionType]):
            Optional. Persistent storage encryption secures data-at-rest for database persistence. You can use 'cloud-
            provider-managed-key' or 'customer-managed-key'.  Default: 'cloud-provider-managed-key' Example: cloud-provider-
            managed-key.
        persistent_storage_encryption_keys (Union[Unset, CustomerManagedKeyProperties]): Optional. Contains information
            about the keys used for each region. Can be used only with external cloud account
        redis_version (Union[Unset, str]): Optional. Defines the Redis version of the databases created in this specific
            request. It doesn't determine future databases associated with this subscription. If not set, databases will use
            the default Redis version. This field is deprecated and will be removed in a future API version - use the
            database-level redisVersion property instead. Example: 7.2.
        command_type (Union[Unset, str]):
    """

    cloud_providers: list["SubscriptionSpec"]
    databases: list["SubscriptionDatabaseSpec"]
    name: Union[Unset, str] = UNSET
    dry_run: Union[Unset, bool] = UNSET
    deployment_type: Union[Unset, SubscriptionCreateRequestDeploymentType] = UNSET
    payment_method: Union[Unset, SubscriptionCreateRequestPaymentMethod] = UNSET
    payment_method_id: Union[Unset, int] = UNSET
    memory_storage: Union[Unset, SubscriptionCreateRequestMemoryStorage] = UNSET
    persistent_storage_encryption_type: Union[Unset, SubscriptionCreateRequestPersistentStorageEncryptionType] = UNSET
    persistent_storage_encryption_keys: Union[Unset, "CustomerManagedKeyProperties"] = UNSET
    redis_version: Union[Unset, str] = UNSET
    command_type: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cloud_providers = []
        for cloud_providers_item_data in self.cloud_providers:
            cloud_providers_item = cloud_providers_item_data.to_dict()
            cloud_providers.append(cloud_providers_item)

        databases = []
        for databases_item_data in self.databases:
            databases_item = databases_item_data.to_dict()
            databases.append(databases_item)

        name = self.name

        dry_run = self.dry_run

        deployment_type: Union[Unset, str] = UNSET
        if not isinstance(self.deployment_type, Unset):
            deployment_type = self.deployment_type.value

        payment_method: Union[Unset, str] = UNSET
        if not isinstance(self.payment_method, Unset):
            payment_method = self.payment_method.value

        payment_method_id = self.payment_method_id

        memory_storage: Union[Unset, str] = UNSET
        if not isinstance(self.memory_storage, Unset):
            memory_storage = self.memory_storage.value

        persistent_storage_encryption_type: Union[Unset, str] = UNSET
        if not isinstance(self.persistent_storage_encryption_type, Unset):
            persistent_storage_encryption_type = self.persistent_storage_encryption_type.value

        persistent_storage_encryption_keys: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.persistent_storage_encryption_keys, Unset):
            persistent_storage_encryption_keys = self.persistent_storage_encryption_keys.to_dict()

        redis_version = self.redis_version

        command_type = self.command_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cloudProviders": cloud_providers,
                "databases": databases,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name
        if dry_run is not UNSET:
            field_dict["dryRun"] = dry_run
        if deployment_type is not UNSET:
            field_dict["deploymentType"] = deployment_type
        if payment_method is not UNSET:
            field_dict["paymentMethod"] = payment_method
        if payment_method_id is not UNSET:
            field_dict["paymentMethodId"] = payment_method_id
        if memory_storage is not UNSET:
            field_dict["memoryStorage"] = memory_storage
        if persistent_storage_encryption_type is not UNSET:
            field_dict["persistentStorageEncryptionType"] = persistent_storage_encryption_type
        if persistent_storage_encryption_keys is not UNSET:
            field_dict["persistentStorageEncryptionKeys"] = persistent_storage_encryption_keys
        if redis_version is not UNSET:
            field_dict["redisVersion"] = redis_version
        if command_type is not UNSET:
            field_dict["commandType"] = command_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.customer_managed_key_properties import CustomerManagedKeyProperties
        from ..models.subscription_database_spec import SubscriptionDatabaseSpec
        from ..models.subscription_spec import SubscriptionSpec

        d = dict(src_dict)
        cloud_providers = []
        _cloud_providers = d.pop("cloudProviders")
        for cloud_providers_item_data in _cloud_providers:
            cloud_providers_item = SubscriptionSpec.from_dict(cloud_providers_item_data)

            cloud_providers.append(cloud_providers_item)

        databases = []
        _databases = d.pop("databases")
        for databases_item_data in _databases:
            databases_item = SubscriptionDatabaseSpec.from_dict(databases_item_data)

            databases.append(databases_item)

        name = d.pop("name", UNSET)

        dry_run = d.pop("dryRun", UNSET)

        _deployment_type = d.pop("deploymentType", UNSET)
        deployment_type: Union[Unset, SubscriptionCreateRequestDeploymentType]
        if isinstance(_deployment_type, Unset):
            deployment_type = UNSET
        else:
            deployment_type = SubscriptionCreateRequestDeploymentType(_deployment_type)

        _payment_method = d.pop("paymentMethod", UNSET)
        payment_method: Union[Unset, SubscriptionCreateRequestPaymentMethod]
        if isinstance(_payment_method, Unset):
            payment_method = UNSET
        else:
            payment_method = SubscriptionCreateRequestPaymentMethod(_payment_method)

        payment_method_id = d.pop("paymentMethodId", UNSET)

        _memory_storage = d.pop("memoryStorage", UNSET)
        memory_storage: Union[Unset, SubscriptionCreateRequestMemoryStorage]
        if isinstance(_memory_storage, Unset):
            memory_storage = UNSET
        else:
            memory_storage = SubscriptionCreateRequestMemoryStorage(_memory_storage)

        _persistent_storage_encryption_type = d.pop("persistentStorageEncryptionType", UNSET)
        persistent_storage_encryption_type: Union[Unset, SubscriptionCreateRequestPersistentStorageEncryptionType]
        if isinstance(_persistent_storage_encryption_type, Unset):
            persistent_storage_encryption_type = UNSET
        else:
            persistent_storage_encryption_type = SubscriptionCreateRequestPersistentStorageEncryptionType(
                _persistent_storage_encryption_type
            )

        _persistent_storage_encryption_keys = d.pop("persistentStorageEncryptionKeys", UNSET)
        persistent_storage_encryption_keys: Union[Unset, CustomerManagedKeyProperties]
        if isinstance(_persistent_storage_encryption_keys, Unset):
            persistent_storage_encryption_keys = UNSET
        else:
            persistent_storage_encryption_keys = CustomerManagedKeyProperties.from_dict(
                _persistent_storage_encryption_keys
            )

        redis_version = d.pop("redisVersion", UNSET)

        command_type = d.pop("commandType", UNSET)

        subscription_create_request = cls(
            cloud_providers=cloud_providers,
            databases=databases,
            name=name,
            dry_run=dry_run,
            deployment_type=deployment_type,
            payment_method=payment_method,
            payment_method_id=payment_method_id,
            memory_storage=memory_storage,
            persistent_storage_encryption_type=persistent_storage_encryption_type,
            persistent_storage_encryption_keys=persistent_storage_encryption_keys,
            redis_version=redis_version,
            command_type=command_type,
        )

        subscription_create_request.additional_properties = d
        return subscription_create_request

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

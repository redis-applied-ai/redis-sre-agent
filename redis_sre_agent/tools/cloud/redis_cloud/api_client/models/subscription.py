from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.subscription_memory_storage import SubscriptionMemoryStorage
from ..models.subscription_payment_method_type import SubscriptionPaymentMethodType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.customer_managed_key_access_details import CustomerManagedKeyAccessDetails
    from ..models.subscription_links_item import SubscriptionLinksItem


T = TypeVar("T", bound="Subscription")


@_attrs_define
class Subscription:
    """RedisLabs Subscription information

    Example:
        {'id': 1206, 'name': 'updated new name', 'status': 'active', 'deploymentType': 'single-region',
            'paymentMethodId': 2, 'memoryStorage': 'ram', 'numberOfDatabases': 6, 'paymentMethodType': 'credit-card',
            'storageEncryption': False, 'subscriptionPricing': [{'type': 'Shards', 'typeDetails': 'high-throughput',
            'quantity': 7, 'quantityMeasurement': 'shards', 'pricePerUnit': 0.124, 'priceCurrency': 'USD', 'pricePeriod':
            'hour'}], 'cloudDetails': [{'provider': 'AWS', 'cloudAccountId': 2, 'totalSizeInGb': 0.0272, 'regions':
            [{'region': 'us-east-1', 'networking': [{'deploymentCIDR': '10.0.0.0/24', 'subnetId':
            'subnet-009ce004ed90da8a6'}], 'preferredAvailabilityZones': ['us-east-1a'], 'multipleAvailabilityZones':
            False}], 'links': []}], 'links': [{'rel': 'self', 'href': 'https://api-
            cloudapi.qa.redislabs.com/v1/subscriptions/120416', 'type': 'GET'}]}

    Attributes:
        id (Union[Unset, int]):
        name (Union[Unset, str]):
        payment_method_id (Union[Unset, int]):
        status (Union[Unset, str]):
        memory_storage (Union[Unset, SubscriptionMemoryStorage]):
        number_of_databases (Union[Unset, int]):
        payment_method_type (Union[Unset, SubscriptionPaymentMethodType]):
        links (Union[Unset, list['SubscriptionLinksItem']]):
        persistent_storage_encryption_type (Union[Unset, str]):
        deletion_grace_period (Union[Unset, str]):
        customer_managed_key_access_details (Union[Unset, CustomerManagedKeyAccessDetails]): Configuration regarding
            customer managed persistent storage encryption
    """

    id: Union[Unset, int] = UNSET
    name: Union[Unset, str] = UNSET
    payment_method_id: Union[Unset, int] = UNSET
    status: Union[Unset, str] = UNSET
    memory_storage: Union[Unset, SubscriptionMemoryStorage] = UNSET
    number_of_databases: Union[Unset, int] = UNSET
    payment_method_type: Union[Unset, SubscriptionPaymentMethodType] = UNSET
    links: Union[Unset, list["SubscriptionLinksItem"]] = UNSET
    persistent_storage_encryption_type: Union[Unset, str] = UNSET
    deletion_grace_period: Union[Unset, str] = UNSET
    customer_managed_key_access_details: Union[Unset, "CustomerManagedKeyAccessDetails"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        name = self.name

        payment_method_id = self.payment_method_id

        status = self.status

        memory_storage: Union[Unset, str] = UNSET
        if not isinstance(self.memory_storage, Unset):
            memory_storage = self.memory_storage.value

        number_of_databases = self.number_of_databases

        payment_method_type: Union[Unset, str] = UNSET
        if not isinstance(self.payment_method_type, Unset):
            payment_method_type = self.payment_method_type.value

        links: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.links, Unset):
            links = []
            for links_item_data in self.links:
                links_item = links_item_data.to_dict()
                links.append(links_item)

        persistent_storage_encryption_type = self.persistent_storage_encryption_type

        deletion_grace_period = self.deletion_grace_period

        customer_managed_key_access_details: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.customer_managed_key_access_details, Unset):
            customer_managed_key_access_details = self.customer_managed_key_access_details.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if name is not UNSET:
            field_dict["name"] = name
        if payment_method_id is not UNSET:
            field_dict["paymentMethodId"] = payment_method_id
        if status is not UNSET:
            field_dict["status"] = status
        if memory_storage is not UNSET:
            field_dict["memoryStorage"] = memory_storage
        if number_of_databases is not UNSET:
            field_dict["numberOfDatabases"] = number_of_databases
        if payment_method_type is not UNSET:
            field_dict["paymentMethodType"] = payment_method_type
        if links is not UNSET:
            field_dict["links"] = links
        if persistent_storage_encryption_type is not UNSET:
            field_dict["persistentStorageEncryptionType"] = persistent_storage_encryption_type
        if deletion_grace_period is not UNSET:
            field_dict["deletionGracePeriod"] = deletion_grace_period
        if customer_managed_key_access_details is not UNSET:
            field_dict["customerManagedKeyAccessDetails"] = customer_managed_key_access_details

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.customer_managed_key_access_details import CustomerManagedKeyAccessDetails
        from ..models.subscription_links_item import SubscriptionLinksItem

        d = dict(src_dict)
        id = d.pop("id", UNSET)

        name = d.pop("name", UNSET)

        payment_method_id = d.pop("paymentMethodId", UNSET)

        status = d.pop("status", UNSET)

        _memory_storage = d.pop("memoryStorage", UNSET)
        memory_storage: Union[Unset, SubscriptionMemoryStorage]
        if isinstance(_memory_storage, Unset):
            memory_storage = UNSET
        else:
            memory_storage = SubscriptionMemoryStorage(_memory_storage)

        number_of_databases = d.pop("numberOfDatabases", UNSET)

        _payment_method_type = d.pop("paymentMethodType", UNSET)
        payment_method_type: Union[Unset, SubscriptionPaymentMethodType]
        if isinstance(_payment_method_type, Unset):
            payment_method_type = UNSET
        else:
            payment_method_type = SubscriptionPaymentMethodType(_payment_method_type)

        links = []
        _links = d.pop("links", UNSET)
        for links_item_data in _links or []:
            links_item = SubscriptionLinksItem.from_dict(links_item_data)

            links.append(links_item)

        persistent_storage_encryption_type = d.pop("persistentStorageEncryptionType", UNSET)

        deletion_grace_period = d.pop("deletionGracePeriod", UNSET)

        _customer_managed_key_access_details = d.pop("customerManagedKeyAccessDetails", UNSET)
        customer_managed_key_access_details: Union[Unset, CustomerManagedKeyAccessDetails]
        if isinstance(_customer_managed_key_access_details, Unset):
            customer_managed_key_access_details = UNSET
        else:
            customer_managed_key_access_details = CustomerManagedKeyAccessDetails.from_dict(
                _customer_managed_key_access_details
            )

        subscription = cls(
            id=id,
            name=name,
            payment_method_id=payment_method_id,
            status=status,
            memory_storage=memory_storage,
            number_of_databases=number_of_databases,
            payment_method_type=payment_method_type,
            links=links,
            persistent_storage_encryption_type=persistent_storage_encryption_type,
            deletion_grace_period=deletion_grace_period,
            customer_managed_key_access_details=customer_managed_key_access_details,
        )

        subscription.additional_properties = d
        return subscription

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

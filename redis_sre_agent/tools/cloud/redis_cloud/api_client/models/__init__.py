"""Contains all the data models used in inputs/outputs"""

from .account_acl_redis_rules import AccountACLRedisRules
from .account_acl_redis_rules_links_item import AccountACLRedisRulesLinksItem
from .account_acl_redis_rules_links_item_additional_property import AccountACLRedisRulesLinksItemAdditionalProperty
from .account_acl_roles import AccountACLRoles
from .account_acl_roles_links_item import AccountACLRolesLinksItem
from .account_acl_roles_links_item_additional_property import AccountACLRolesLinksItemAdditionalProperty
from .account_acl_users import AccountACLUsers
from .account_acl_users_links_item import AccountACLUsersLinksItem
from .account_acl_users_links_item_additional_property import AccountACLUsersLinksItemAdditionalProperty
from .account_fixed_subscription_databases import AccountFixedSubscriptionDatabases
from .account_fixed_subscription_databases_links_item import AccountFixedSubscriptionDatabasesLinksItem
from .account_fixed_subscription_databases_links_item_additional_property import (
    AccountFixedSubscriptionDatabasesLinksItemAdditionalProperty,
)
from .account_session_log_entries import AccountSessionLogEntries
from .account_session_log_entries_links_item import AccountSessionLogEntriesLinksItem
from .account_session_log_entries_links_item_additional_property import (
    AccountSessionLogEntriesLinksItemAdditionalProperty,
)
from .account_session_log_entry import AccountSessionLogEntry
from .account_subscription_databases import AccountSubscriptionDatabases
from .account_subscription_databases_links_item import AccountSubscriptionDatabasesLinksItem
from .account_subscription_databases_links_item_additional_property import (
    AccountSubscriptionDatabasesLinksItemAdditionalProperty,
)
from .account_subscriptions import AccountSubscriptions
from .account_subscriptions_links_item import AccountSubscriptionsLinksItem
from .account_subscriptions_links_item_additional_property import AccountSubscriptionsLinksItemAdditionalProperty
from .account_system_log_entries import AccountSystemLogEntries
from .account_system_log_entries_links_item import AccountSystemLogEntriesLinksItem
from .account_system_log_entries_links_item_additional_property import (
    AccountSystemLogEntriesLinksItemAdditionalProperty,
)
from .account_system_log_entry import AccountSystemLogEntry
from .account_user import AccountUser
from .account_user_options import AccountUserOptions
from .account_user_update_request import AccountUserUpdateRequest
from .account_user_update_request_role import AccountUserUpdateRequestRole
from .account_users import AccountUsers
from .acl_redis_rule_create_request import AclRedisRuleCreateRequest
from .acl_redis_rule_update_request import AclRedisRuleUpdateRequest
from .acl_role_create_request import AclRoleCreateRequest
from .acl_role_database_spec import AclRoleDatabaseSpec
from .acl_role_redis_rule_spec import AclRoleRedisRuleSpec
from .acl_role_update_request import AclRoleUpdateRequest
from .acl_user import ACLUser
from .acl_user_create_request import AclUserCreateRequest
from .acl_user_links_item import ACLUserLinksItem
from .acl_user_links_item_additional_property import ACLUserLinksItemAdditionalProperty
from .acl_user_update_request import AclUserUpdateRequest
from .active_active_psc_endpoint_create_request import ActiveActivePscEndpointCreateRequest
from .active_active_psc_endpoint_update_request import ActiveActivePscEndpointUpdateRequest
from .active_active_psc_endpoint_update_request_action import ActiveActivePscEndpointUpdateRequestAction
from .active_active_region_create_request import ActiveActiveRegionCreateRequest
from .active_active_region_create_request_resp_version import ActiveActiveRegionCreateRequestRespVersion
from .active_active_region_delete_request import ActiveActiveRegionDeleteRequest
from .active_active_region_to_delete import ActiveActiveRegionToDelete
from .active_active_subscription_regions import ActiveActiveSubscriptionRegions
from .active_active_subscription_regions_links_item import ActiveActiveSubscriptionRegionsLinksItem
from .active_active_subscription_regions_links_item_additional_property import (
    ActiveActiveSubscriptionRegionsLinksItemAdditionalProperty,
)
from .active_active_tgw_update_cidrs_request import ActiveActiveTgwUpdateCidrsRequest
from .active_active_vpc_peering_create_aws_request import ActiveActiveVpcPeeringCreateAwsRequest
from .active_active_vpc_peering_create_gcp_request import ActiveActiveVpcPeeringCreateGcpRequest
from .active_active_vpc_peering_update_aws_request import ActiveActiveVpcPeeringUpdateAwsRequest
from .bdb_version_upgrade_status import BdbVersionUpgradeStatus
from .bdb_version_upgrade_status_upgrade_status import BdbVersionUpgradeStatusUpgradeStatus
from .cidr import Cidr
from .cidr_white_list_update_request import CidrWhiteListUpdateRequest
from .cloud_account import CloudAccount
from .cloud_account_create_request import CloudAccountCreateRequest
from .cloud_account_create_request_provider import CloudAccountCreateRequestProvider
from .cloud_account_links_item import CloudAccountLinksItem
from .cloud_account_links_item_additional_property import CloudAccountLinksItemAdditionalProperty
from .cloud_account_provider import CloudAccountProvider
from .cloud_account_update_request import CloudAccountUpdateRequest
from .cloud_accounts import CloudAccounts
from .cloud_accounts_links_item import CloudAccountsLinksItem
from .cloud_accounts_links_item_additional_property import CloudAccountsLinksItemAdditionalProperty
from .cloud_tag import CloudTag
from .cloud_tag_links_item import CloudTagLinksItem
from .cloud_tag_links_item_additional_property import CloudTagLinksItemAdditionalProperty
from .cloud_tags import CloudTags
from .cloud_tags_links_item import CloudTagsLinksItem
from .cloud_tags_links_item_additional_property import CloudTagsLinksItemAdditionalProperty
from .crdb_flush_request import CrdbFlushRequest
from .crdb_region_spec import CrdbRegionSpec
from .crdb_update_properties_request import CrdbUpdatePropertiesRequest
from .crdb_update_properties_request_data_eviction_policy import CrdbUpdatePropertiesRequestDataEvictionPolicy
from .crdb_update_properties_request_global_data_persistence import CrdbUpdatePropertiesRequestGlobalDataPersistence
from .customer_managed_key import CustomerManagedKey
from .customer_managed_key_access_details import CustomerManagedKeyAccessDetails
from .customer_managed_key_access_details_required_key_policy_statements import (
    CustomerManagedKeyAccessDetailsRequiredKeyPolicyStatements,
)
from .customer_managed_key_properties import CustomerManagedKeyProperties
from .customer_managed_key_properties_deletion_grace_period import CustomerManagedKeyPropertiesDeletionGracePeriod
from .data_persistence_entry import DataPersistenceEntry
from .data_persistence_options import DataPersistenceOptions
from .data_persistence_options_links_item import DataPersistenceOptionsLinksItem
from .data_persistence_options_links_item_additional_property import DataPersistenceOptionsLinksItemAdditionalProperty
from .database import Database
from .database_alert_spec import DatabaseAlertSpec
from .database_alert_spec_name import DatabaseAlertSpecName
from .database_backup_config import DatabaseBackupConfig
from .database_backup_config_backup_interval import DatabaseBackupConfigBackupInterval
from .database_backup_config_backup_storage_type import DatabaseBackupConfigBackupStorageType
from .database_backup_config_database_backup_time_utc import DatabaseBackupConfigDatabaseBackupTimeUTC
from .database_backup_request import DatabaseBackupRequest
from .database_certificate import DatabaseCertificate
from .database_certificate_spec import DatabaseCertificateSpec
from .database_create_request import DatabaseCreateRequest
from .database_create_request_data_eviction_policy import DatabaseCreateRequestDataEvictionPolicy
from .database_create_request_data_persistence import DatabaseCreateRequestDataPersistence
from .database_create_request_protocol import DatabaseCreateRequestProtocol
from .database_create_request_resp_version import DatabaseCreateRequestRespVersion
from .database_create_request_sharding_type import DatabaseCreateRequestShardingType
from .database_import_request import DatabaseImportRequest
from .database_import_request_source_type import DatabaseImportRequestSourceType
from .database_links_item import DatabaseLinksItem
from .database_links_item_additional_property import DatabaseLinksItemAdditionalProperty
from .database_module_spec import DatabaseModuleSpec
from .database_module_spec_parameters import DatabaseModuleSpecParameters
from .database_module_spec_parameters_additional_property import DatabaseModuleSpecParametersAdditionalProperty
from .database_slow_log_entries import DatabaseSlowLogEntries
from .database_slow_log_entries_links_item import DatabaseSlowLogEntriesLinksItem
from .database_slow_log_entries_links_item_additional_property import DatabaseSlowLogEntriesLinksItemAdditionalProperty
from .database_slow_log_entry import DatabaseSlowLogEntry
from .database_sync_source_spec import DatabaseSyncSourceSpec
from .database_tag_create_request import DatabaseTagCreateRequest
from .database_tag_update_request import DatabaseTagUpdateRequest
from .database_tags_update_request import DatabaseTagsUpdateRequest
from .database_throughput_spec import DatabaseThroughputSpec
from .database_throughput_spec_by import DatabaseThroughputSpecBy
from .database_update_request import DatabaseUpdateRequest
from .database_update_request_data_eviction_policy import DatabaseUpdateRequestDataEvictionPolicy
from .database_update_request_data_persistence import DatabaseUpdateRequestDataPersistence
from .database_update_request_resp_version import DatabaseUpdateRequestRespVersion
from .database_upgrade_redis_version_request import DatabaseUpgradeRedisVersionRequest
from .delete_tag_1_response_200 import DeleteTag1Response200
from .delete_tag_response_200 import DeleteTagResponse200
from .dynamic_endpoints import DynamicEndpoints
from .fixed_database import FixedDatabase
from .fixed_database_backup_request import FixedDatabaseBackupRequest
from .fixed_database_create_request import FixedDatabaseCreateRequest
from .fixed_database_create_request_data_eviction_policy import FixedDatabaseCreateRequestDataEvictionPolicy
from .fixed_database_create_request_data_persistence import FixedDatabaseCreateRequestDataPersistence
from .fixed_database_create_request_protocol import FixedDatabaseCreateRequestProtocol
from .fixed_database_create_request_resp_version import FixedDatabaseCreateRequestRespVersion
from .fixed_database_data_eviction_policy import FixedDatabaseDataEvictionPolicy
from .fixed_database_data_persistence import FixedDatabaseDataPersistence
from .fixed_database_import_request import FixedDatabaseImportRequest
from .fixed_database_import_request_source_type import FixedDatabaseImportRequestSourceType
from .fixed_database_links_item import FixedDatabaseLinksItem
from .fixed_database_links_item_additional_property import FixedDatabaseLinksItemAdditionalProperty
from .fixed_database_memory_storage import FixedDatabaseMemoryStorage
from .fixed_database_protocol import FixedDatabaseProtocol
from .fixed_database_resp_version import FixedDatabaseRespVersion
from .fixed_database_update_request import FixedDatabaseUpdateRequest
from .fixed_database_update_request_data_eviction_policy import FixedDatabaseUpdateRequestDataEvictionPolicy
from .fixed_database_update_request_data_persistence import FixedDatabaseUpdateRequestDataPersistence
from .fixed_database_update_request_resp_version import FixedDatabaseUpdateRequestRespVersion
from .fixed_subscription import FixedSubscription
from .fixed_subscription_create_request import FixedSubscriptionCreateRequest
from .fixed_subscription_create_request_payment_method import FixedSubscriptionCreateRequestPaymentMethod
from .fixed_subscription_links_item import FixedSubscriptionLinksItem
from .fixed_subscription_links_item_additional_property import FixedSubscriptionLinksItemAdditionalProperty
from .fixed_subscription_update_request import FixedSubscriptionUpdateRequest
from .fixed_subscription_update_request_payment_method import FixedSubscriptionUpdateRequestPaymentMethod
from .fixed_subscriptions import FixedSubscriptions
from .fixed_subscriptions_links_item import FixedSubscriptionsLinksItem
from .fixed_subscriptions_links_item_additional_property import FixedSubscriptionsLinksItemAdditionalProperty
from .fixed_subscriptions_plan import FixedSubscriptionsPlan
from .fixed_subscriptions_plan_links_item import FixedSubscriptionsPlanLinksItem
from .fixed_subscriptions_plan_links_item_additional_property import FixedSubscriptionsPlanLinksItemAdditionalProperty
from .fixed_subscriptions_plans import FixedSubscriptionsPlans
from .fixed_subscriptions_plans_links_item import FixedSubscriptionsPlansLinksItem
from .fixed_subscriptions_plans_links_item_additional_property import FixedSubscriptionsPlansLinksItemAdditionalProperty
from .get_all_fixed_subscriptions_plans_provider import GetAllFixedSubscriptionsPlansProvider
from .get_supported_regions_provider import GetSupportedRegionsProvider
from .local_region_properties import LocalRegionProperties
from .local_region_properties_data_persistence import LocalRegionPropertiesDataPersistence
from .local_region_properties_resp_version import LocalRegionPropertiesRespVersion
from .local_throughput import LocalThroughput
from .maintenance_window import MaintenanceWindow
from .maintenance_window_skip_status import MaintenanceWindowSkipStatus
from .maintenance_window_spec import MaintenanceWindowSpec
from .module import Module
from .modules_data import ModulesData
from .modules_data_links_item import ModulesDataLinksItem
from .modules_data_links_item_additional_property import ModulesDataLinksItemAdditionalProperty
from .payment_methods import PaymentMethods
from .payment_methods_links_item import PaymentMethodsLinksItem
from .payment_methods_links_item_additional_property import PaymentMethodsLinksItemAdditionalProperty
from .private_link_active_active_create_request import PrivateLinkActiveActiveCreateRequest
from .private_link_active_active_create_request_type import PrivateLinkActiveActiveCreateRequestType
from .private_link_active_active_principals_create_request import PrivateLinkActiveActivePrincipalsCreateRequest
from .private_link_active_active_principals_create_request_type import (
    PrivateLinkActiveActivePrincipalsCreateRequestType,
)
from .private_link_active_active_principals_delete_request import PrivateLinkActiveActivePrincipalsDeleteRequest
from .private_link_create_request import PrivateLinkCreateRequest
from .private_link_create_request_type import PrivateLinkCreateRequestType
from .private_link_principals_create_request import PrivateLinkPrincipalsCreateRequest
from .private_link_principals_create_request_type import PrivateLinkPrincipalsCreateRequestType
from .private_link_principals_delete_request import PrivateLinkPrincipalsDeleteRequest
from .processor_response import ProcessorResponse
from .processor_response_error import ProcessorResponseError
from .processor_response_resource import ProcessorResponseResource
from .psc_endpoint_create_request import PscEndpointCreateRequest
from .psc_endpoint_update_request import PscEndpointUpdateRequest
from .psc_endpoint_update_request_action import PscEndpointUpdateRequestAction
from .redis_version import RedisVersion
from .redis_versions import RedisVersions
from .region import Region
from .region_provider import RegionProvider
from .regions import Regions
from .regions_links_item import RegionsLinksItem
from .regions_links_item_additional_property import RegionsLinksItemAdditionalProperty
from .replica_of_spec import ReplicaOfSpec
from .root_account import RootAccount
from .root_account_links_item import RootAccountLinksItem
from .root_account_links_item_additional_property import RootAccountLinksItemAdditionalProperty
from .search_scaling_factors_data import SearchScalingFactorsData
from .search_scaling_factors_data_links_item import SearchScalingFactorsDataLinksItem
from .search_scaling_factors_data_links_item_additional_property import (
    SearchScalingFactorsDataLinksItemAdditionalProperty,
)
from .subscription import Subscription
from .subscription_create_request import SubscriptionCreateRequest
from .subscription_create_request_deployment_type import SubscriptionCreateRequestDeploymentType
from .subscription_create_request_memory_storage import SubscriptionCreateRequestMemoryStorage
from .subscription_create_request_payment_method import SubscriptionCreateRequestPaymentMethod
from .subscription_create_request_persistent_storage_encryption_type import (
    SubscriptionCreateRequestPersistentStorageEncryptionType,
)
from .subscription_database_spec import SubscriptionDatabaseSpec
from .subscription_database_spec_data_persistence import SubscriptionDatabaseSpecDataPersistence
from .subscription_database_spec_protocol import SubscriptionDatabaseSpecProtocol
from .subscription_database_spec_resp_version import SubscriptionDatabaseSpecRespVersion
from .subscription_database_spec_sharding_type import SubscriptionDatabaseSpecShardingType
from .subscription_links_item import SubscriptionLinksItem
from .subscription_links_item_additional_property import SubscriptionLinksItemAdditionalProperty
from .subscription_maintenance_windows import SubscriptionMaintenanceWindows
from .subscription_maintenance_windows_mode import SubscriptionMaintenanceWindowsMode
from .subscription_maintenance_windows_spec import SubscriptionMaintenanceWindowsSpec
from .subscription_maintenance_windows_spec_mode import SubscriptionMaintenanceWindowsSpecMode
from .subscription_memory_storage import SubscriptionMemoryStorage
from .subscription_payment_method_type import SubscriptionPaymentMethodType
from .subscription_pricing import SubscriptionPricing
from .subscription_pricings import SubscriptionPricings
from .subscription_region_networking_spec import SubscriptionRegionNetworkingSpec
from .subscription_region_spec import SubscriptionRegionSpec
from .subscription_spec import SubscriptionSpec
from .subscription_spec_provider import SubscriptionSpecProvider
from .subscription_update_cmk_request import SubscriptionUpdateCMKRequest
from .subscription_update_cmk_request_deletion_grace_period import SubscriptionUpdateCMKRequestDeletionGracePeriod
from .subscription_update_request import SubscriptionUpdateRequest
from .subscription_update_request_payment_method import SubscriptionUpdateRequestPaymentMethod
from .tag import Tag
from .task_state_update import TaskStateUpdate
from .task_state_update_links_item import TaskStateUpdateLinksItem
from .task_state_update_links_item_additional_property import TaskStateUpdateLinksItemAdditionalProperty
from .task_state_update_status import TaskStateUpdateStatus
from .tasks_state_update import TasksStateUpdate
from .tgw_update_cidrs_request import TgwUpdateCidrsRequest
from .vpc_peering_create_aws_request import VpcPeeringCreateAwsRequest
from .vpc_peering_create_gcp_request import VpcPeeringCreateGcpRequest
from .vpc_peering_update_aws_request import VpcPeeringUpdateAwsRequest

__all__ = (
    "AccountACLRedisRules",
    "AccountACLRedisRulesLinksItem",
    "AccountACLRedisRulesLinksItemAdditionalProperty",
    "AccountACLRoles",
    "AccountACLRolesLinksItem",
    "AccountACLRolesLinksItemAdditionalProperty",
    "AccountACLUsers",
    "AccountACLUsersLinksItem",
    "AccountACLUsersLinksItemAdditionalProperty",
    "AccountFixedSubscriptionDatabases",
    "AccountFixedSubscriptionDatabasesLinksItem",
    "AccountFixedSubscriptionDatabasesLinksItemAdditionalProperty",
    "AccountSessionLogEntries",
    "AccountSessionLogEntriesLinksItem",
    "AccountSessionLogEntriesLinksItemAdditionalProperty",
    "AccountSessionLogEntry",
    "AccountSubscriptionDatabases",
    "AccountSubscriptionDatabasesLinksItem",
    "AccountSubscriptionDatabasesLinksItemAdditionalProperty",
    "AccountSubscriptions",
    "AccountSubscriptionsLinksItem",
    "AccountSubscriptionsLinksItemAdditionalProperty",
    "AccountSystemLogEntries",
    "AccountSystemLogEntriesLinksItem",
    "AccountSystemLogEntriesLinksItemAdditionalProperty",
    "AccountSystemLogEntry",
    "AccountUser",
    "AccountUserOptions",
    "AccountUsers",
    "AccountUserUpdateRequest",
    "AccountUserUpdateRequestRole",
    "AclRedisRuleCreateRequest",
    "AclRedisRuleUpdateRequest",
    "AclRoleCreateRequest",
    "AclRoleDatabaseSpec",
    "AclRoleRedisRuleSpec",
    "AclRoleUpdateRequest",
    "ACLUser",
    "AclUserCreateRequest",
    "ACLUserLinksItem",
    "ACLUserLinksItemAdditionalProperty",
    "AclUserUpdateRequest",
    "ActiveActivePscEndpointCreateRequest",
    "ActiveActivePscEndpointUpdateRequest",
    "ActiveActivePscEndpointUpdateRequestAction",
    "ActiveActiveRegionCreateRequest",
    "ActiveActiveRegionCreateRequestRespVersion",
    "ActiveActiveRegionDeleteRequest",
    "ActiveActiveRegionToDelete",
    "ActiveActiveSubscriptionRegions",
    "ActiveActiveSubscriptionRegionsLinksItem",
    "ActiveActiveSubscriptionRegionsLinksItemAdditionalProperty",
    "ActiveActiveTgwUpdateCidrsRequest",
    "ActiveActiveVpcPeeringCreateAwsRequest",
    "ActiveActiveVpcPeeringCreateGcpRequest",
    "ActiveActiveVpcPeeringUpdateAwsRequest",
    "BdbVersionUpgradeStatus",
    "BdbVersionUpgradeStatusUpgradeStatus",
    "Cidr",
    "CidrWhiteListUpdateRequest",
    "CloudAccount",
    "CloudAccountCreateRequest",
    "CloudAccountCreateRequestProvider",
    "CloudAccountLinksItem",
    "CloudAccountLinksItemAdditionalProperty",
    "CloudAccountProvider",
    "CloudAccounts",
    "CloudAccountsLinksItem",
    "CloudAccountsLinksItemAdditionalProperty",
    "CloudAccountUpdateRequest",
    "CloudTag",
    "CloudTagLinksItem",
    "CloudTagLinksItemAdditionalProperty",
    "CloudTags",
    "CloudTagsLinksItem",
    "CloudTagsLinksItemAdditionalProperty",
    "CrdbFlushRequest",
    "CrdbRegionSpec",
    "CrdbUpdatePropertiesRequest",
    "CrdbUpdatePropertiesRequestDataEvictionPolicy",
    "CrdbUpdatePropertiesRequestGlobalDataPersistence",
    "CustomerManagedKey",
    "CustomerManagedKeyAccessDetails",
    "CustomerManagedKeyAccessDetailsRequiredKeyPolicyStatements",
    "CustomerManagedKeyProperties",
    "CustomerManagedKeyPropertiesDeletionGracePeriod",
    "Database",
    "DatabaseAlertSpec",
    "DatabaseAlertSpecName",
    "DatabaseBackupConfig",
    "DatabaseBackupConfigBackupInterval",
    "DatabaseBackupConfigBackupStorageType",
    "DatabaseBackupConfigDatabaseBackupTimeUTC",
    "DatabaseBackupRequest",
    "DatabaseCertificate",
    "DatabaseCertificateSpec",
    "DatabaseCreateRequest",
    "DatabaseCreateRequestDataEvictionPolicy",
    "DatabaseCreateRequestDataPersistence",
    "DatabaseCreateRequestProtocol",
    "DatabaseCreateRequestRespVersion",
    "DatabaseCreateRequestShardingType",
    "DatabaseImportRequest",
    "DatabaseImportRequestSourceType",
    "DatabaseLinksItem",
    "DatabaseLinksItemAdditionalProperty",
    "DatabaseModuleSpec",
    "DatabaseModuleSpecParameters",
    "DatabaseModuleSpecParametersAdditionalProperty",
    "DatabaseSlowLogEntries",
    "DatabaseSlowLogEntriesLinksItem",
    "DatabaseSlowLogEntriesLinksItemAdditionalProperty",
    "DatabaseSlowLogEntry",
    "DatabaseSyncSourceSpec",
    "DatabaseTagCreateRequest",
    "DatabaseTagsUpdateRequest",
    "DatabaseTagUpdateRequest",
    "DatabaseThroughputSpec",
    "DatabaseThroughputSpecBy",
    "DatabaseUpdateRequest",
    "DatabaseUpdateRequestDataEvictionPolicy",
    "DatabaseUpdateRequestDataPersistence",
    "DatabaseUpdateRequestRespVersion",
    "DatabaseUpgradeRedisVersionRequest",
    "DataPersistenceEntry",
    "DataPersistenceOptions",
    "DataPersistenceOptionsLinksItem",
    "DataPersistenceOptionsLinksItemAdditionalProperty",
    "DeleteTag1Response200",
    "DeleteTagResponse200",
    "DynamicEndpoints",
    "FixedDatabase",
    "FixedDatabaseBackupRequest",
    "FixedDatabaseCreateRequest",
    "FixedDatabaseCreateRequestDataEvictionPolicy",
    "FixedDatabaseCreateRequestDataPersistence",
    "FixedDatabaseCreateRequestProtocol",
    "FixedDatabaseCreateRequestRespVersion",
    "FixedDatabaseDataEvictionPolicy",
    "FixedDatabaseDataPersistence",
    "FixedDatabaseImportRequest",
    "FixedDatabaseImportRequestSourceType",
    "FixedDatabaseLinksItem",
    "FixedDatabaseLinksItemAdditionalProperty",
    "FixedDatabaseMemoryStorage",
    "FixedDatabaseProtocol",
    "FixedDatabaseRespVersion",
    "FixedDatabaseUpdateRequest",
    "FixedDatabaseUpdateRequestDataEvictionPolicy",
    "FixedDatabaseUpdateRequestDataPersistence",
    "FixedDatabaseUpdateRequestRespVersion",
    "FixedSubscription",
    "FixedSubscriptionCreateRequest",
    "FixedSubscriptionCreateRequestPaymentMethod",
    "FixedSubscriptionLinksItem",
    "FixedSubscriptionLinksItemAdditionalProperty",
    "FixedSubscriptions",
    "FixedSubscriptionsLinksItem",
    "FixedSubscriptionsLinksItemAdditionalProperty",
    "FixedSubscriptionsPlan",
    "FixedSubscriptionsPlanLinksItem",
    "FixedSubscriptionsPlanLinksItemAdditionalProperty",
    "FixedSubscriptionsPlans",
    "FixedSubscriptionsPlansLinksItem",
    "FixedSubscriptionsPlansLinksItemAdditionalProperty",
    "FixedSubscriptionUpdateRequest",
    "FixedSubscriptionUpdateRequestPaymentMethod",
    "GetAllFixedSubscriptionsPlansProvider",
    "GetSupportedRegionsProvider",
    "LocalRegionProperties",
    "LocalRegionPropertiesDataPersistence",
    "LocalRegionPropertiesRespVersion",
    "LocalThroughput",
    "MaintenanceWindow",
    "MaintenanceWindowSkipStatus",
    "MaintenanceWindowSpec",
    "Module",
    "ModulesData",
    "ModulesDataLinksItem",
    "ModulesDataLinksItemAdditionalProperty",
    "PaymentMethods",
    "PaymentMethodsLinksItem",
    "PaymentMethodsLinksItemAdditionalProperty",
    "PrivateLinkActiveActiveCreateRequest",
    "PrivateLinkActiveActiveCreateRequestType",
    "PrivateLinkActiveActivePrincipalsCreateRequest",
    "PrivateLinkActiveActivePrincipalsCreateRequestType",
    "PrivateLinkActiveActivePrincipalsDeleteRequest",
    "PrivateLinkCreateRequest",
    "PrivateLinkCreateRequestType",
    "PrivateLinkPrincipalsCreateRequest",
    "PrivateLinkPrincipalsCreateRequestType",
    "PrivateLinkPrincipalsDeleteRequest",
    "ProcessorResponse",
    "ProcessorResponseError",
    "ProcessorResponseResource",
    "PscEndpointCreateRequest",
    "PscEndpointUpdateRequest",
    "PscEndpointUpdateRequestAction",
    "RedisVersion",
    "RedisVersions",
    "Region",
    "RegionProvider",
    "Regions",
    "RegionsLinksItem",
    "RegionsLinksItemAdditionalProperty",
    "ReplicaOfSpec",
    "RootAccount",
    "RootAccountLinksItem",
    "RootAccountLinksItemAdditionalProperty",
    "SearchScalingFactorsData",
    "SearchScalingFactorsDataLinksItem",
    "SearchScalingFactorsDataLinksItemAdditionalProperty",
    "Subscription",
    "SubscriptionCreateRequest",
    "SubscriptionCreateRequestDeploymentType",
    "SubscriptionCreateRequestMemoryStorage",
    "SubscriptionCreateRequestPaymentMethod",
    "SubscriptionCreateRequestPersistentStorageEncryptionType",
    "SubscriptionDatabaseSpec",
    "SubscriptionDatabaseSpecDataPersistence",
    "SubscriptionDatabaseSpecProtocol",
    "SubscriptionDatabaseSpecRespVersion",
    "SubscriptionDatabaseSpecShardingType",
    "SubscriptionLinksItem",
    "SubscriptionLinksItemAdditionalProperty",
    "SubscriptionMaintenanceWindows",
    "SubscriptionMaintenanceWindowsMode",
    "SubscriptionMaintenanceWindowsSpec",
    "SubscriptionMaintenanceWindowsSpecMode",
    "SubscriptionMemoryStorage",
    "SubscriptionPaymentMethodType",
    "SubscriptionPricing",
    "SubscriptionPricings",
    "SubscriptionRegionNetworkingSpec",
    "SubscriptionRegionSpec",
    "SubscriptionSpec",
    "SubscriptionSpecProvider",
    "SubscriptionUpdateCMKRequest",
    "SubscriptionUpdateCMKRequestDeletionGracePeriod",
    "SubscriptionUpdateRequest",
    "SubscriptionUpdateRequestPaymentMethod",
    "Tag",
    "TasksStateUpdate",
    "TaskStateUpdate",
    "TaskStateUpdateLinksItem",
    "TaskStateUpdateLinksItemAdditionalProperty",
    "TaskStateUpdateStatus",
    "TgwUpdateCidrsRequest",
    "VpcPeeringCreateAwsRequest",
    "VpcPeeringCreateGcpRequest",
    "VpcPeeringUpdateAwsRequest",
)

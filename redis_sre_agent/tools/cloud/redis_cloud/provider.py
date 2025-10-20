"""Redis Cloud Management API tool provider.

This provider uses the Redis Cloud Management API to inspect and manage
Redis Cloud subscriptions, databases, users, and other resources.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

from .api_client.api.account import get_current_account, get_supported_regions
from .api_client.api.databases_essentials import (
    get_fixed_subscription_databases as ess_get_subscription_databases,
)
from .api_client.api.databases_essentials import (
    get_subscription_database_by_id_1 as ess_get_subscription_database_by_id,
)
from .api_client.api.databases_pro import (
    get_subscription_database_by_id as pro_get_subscription_database_by_id,
)
from .api_client.api.databases_pro import (
    get_subscription_databases as pro_get_subscription_databases,
)
from .api_client.api.subscriptions_essentials import (
    get_subscription_by_id_1 as ess_get_subscription_by_id,
)
from .api_client.api.subscriptions_pro import (
    get_all_subscriptions as pro_list_subscriptions,
)
from .api_client.api.subscriptions_pro import (
    get_subscription_by_id as pro_get_subscription_by_id,
)

# Use the generated Redis Cloud API client directly
from .api_client.client import Client as GeneratedClient

logger = logging.getLogger(__name__)


class RedisCloudConfig(BaseSettings):
    """Configuration for Redis Cloud Management API provider.

    Automatically loads from environment variables with TOOLS_REDIS_CLOUD_ prefix:
    - TOOLS_REDIS_CLOUD_API_KEY: Redis Cloud API key
    - TOOLS_REDIS_CLOUD_API_SECRET_KEY: Redis Cloud API secret key
    - TOOLS_REDIS_CLOUD_BASE_URL: Base URL (default: https://api.redislabs.com/v1)

    Example:
        # Loads from environment automatically
        config = RedisCloudConfig()

        # Or override with explicit values
        config = RedisCloudConfig(
            api_key="your-key",
            api_secret_key="your-secret"
        )
    """

    model_config = SettingsConfigDict(env_prefix="tools_redis_cloud_")

    api_key: SecretStr = Field(description="Redis Cloud API key (x-api-key header)")
    api_secret_key: SecretStr = Field(
        description="Redis Cloud API secret key (x-api-secret-key header)"
    )
    base_url: str = Field(
        default="https://api.redislabs.com/v1", description="Base URL for Redis Cloud API"
    )
    timeout: float = Field(default=30.0, description="Request timeout in seconds")


class RedisCloudToolProvider(ToolProvider):
    """Redis Cloud Management API provider.

    Provides tools for managing Redis Cloud resources, including:
    - Account information
    - Subscriptions (Pro and Essentials)
    - Databases (Pro and Essentials)
    - Users and RBAC
    - Cloud accounts
    - Tasks

    Authentication requires API key and secret key from Redis Cloud console.
    See: https://docs.redislabs.com/latest/rc/api/get-started/enable-the-api/
    """

    def __init__(
        self,
        redis_instance: Optional[Any] = None,
        config: Optional[RedisCloudConfig] = None,
    ):
        """Initialize the Redis Cloud API provider.

        Args:
            redis_instance: Optional Redis instance. When instance_type='redis_cloud',
                this instance may include redis_cloud_subscription_id and
                redis_cloud_database_id that will be used as defaults for tool calls.
            config: Optional config for API credentials (loaded from env if not provided)

        Raises:
            ValueError: If API credentials are not provided
        """
        super().__init__(redis_instance)

        # Load config from environment if not provided
        if config is None:
            config = RedisCloudConfig()

        self.config = config
        self._client: Optional[GeneratedClient] = None
        # Default identifiers from redis_instance (if provided)
        self._subscription_id: Optional[int] = None
        self._database_id: Optional[int] = None
        self._subscription_type: Optional[str] = None  # 'pro' | 'essentials'
        self._database_name: Optional[str] = None
        if redis_instance is not None:
            try:
                if getattr(redis_instance, "instance_type", None) == "redis_cloud":
                    self._subscription_id = getattr(
                        redis_instance, "redis_cloud_subscription_id", None
                    )
                    self._database_id = getattr(redis_instance, "redis_cloud_database_id", None)
                    self._subscription_type = getattr(
                        redis_instance, "redis_cloud_subscription_type", None
                    )
                    self._database_name = getattr(redis_instance, "redis_cloud_database_name", None)
            except Exception:
                # Be defensive; absence of attributes shouldn't break provider init
                pass

    @property
    def provider_name(self) -> str:
        return "redis_cloud"

    def get_client(self) -> GeneratedClient:
        """Get or create the generated Redis Cloud API client (lazy initialization)."""
        if self._client is None:
            # Initialize the generated client with auth headers
            headers = {
                "x-api-key": self.config.api_key.get_secret_value(),
                "x-api-secret-key": self.config.api_secret_key.get_secret_value(),
                "Content-Type": "application/json",
            }
            self._client = GeneratedClient(
                base_url=self.config.base_url,
                headers=headers,
            )
            logger.info(f"Connected to Redis Cloud API at {self.config.base_url}")
        return self._client

    async def __aenter__(self):
        """Support async context manager (no-op, client is lazily initialized)."""
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Support async context manager - cleanup HTTP client."""
        if self._client:
            try:
                await self.get_client().get_async_httpx_client().aclose()
            except Exception:
                pass
        self._client = None

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Create tool schemas for Redis Cloud API operations."""
        return [
            # Account operations
            ToolDefinition(
                name=self._make_tool_name("get_account"),
                description=(
                    "Get current Redis Cloud account details including account ID, name, "
                    "and other account-level information."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_regions"),
                description=(
                    "Get list of available regions for Redis Cloud Pro subscriptions. "
                    "Returns region names, cloud providers, and availability zones."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            # Subscription operations
            ToolDefinition(
                name=self._make_tool_name("list_subscriptions"),
                description=(
                    "List all Redis Cloud Pro subscriptions in the account. "
                    "Returns subscription IDs, names, status, regions, and configuration."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_subscription"),
                description=(
                    "Get detailed information about the configured Redis Cloud subscription for this instance. "
                    "Includes configuration, status, pricing, and resource details."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            # Database operations
            ToolDefinition(
                name=self._make_tool_name("list_databases"),
                description=(
                    "List all databases in the configured Redis Cloud subscription for this instance. "
                    "Returns database IDs, names, status, endpoints, and configuration."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_database"),
                description=(
                    "Get detailed information about the configured Redis Cloud database for this instance. "
                    "Includes endpoints, memory size, throughput, modules, and status."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            # User operations
            ToolDefinition(
                name=self._make_tool_name("list_users"),
                description=(
                    "List all users in the Redis Cloud account. "
                    "Returns user IDs, names, emails, roles, and status."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_user"),
                description=("Get detailed information about a specific user in the account."),
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "integer",
                            "description": "User ID to retrieve",
                        },
                    },
                    "required": ["user_id"],
                },
            ),
            # Task operations
            ToolDefinition(
                name=self._make_tool_name("list_tasks"),
                description=(
                    "List all asynchronous tasks in the account. "
                    "Tasks track background operations like creating/updating resources. "
                    "Returns task IDs, status, progress, and resource information."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_task"),
                description=(
                    "Get detailed information about a specific task. "
                    "Use this to check the status of asynchronous operations."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "Task ID to retrieve",
                        },
                    },
                    "required": ["task_id"],
                },
            ),
            # Cloud account operations
            ToolDefinition(
                name=self._make_tool_name("list_cloud_accounts"),
                description=(
                    "List all cloud accounts (AWS) linked to the Redis Cloud account. "
                    "Returns cloud account IDs, provider, credentials status, and regions."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a Redis Cloud API tool call.

        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments

        Returns:
            Tool execution result
        """
        # Parse operation from tool_name
        # Format: redis_cloud_{hash}_operation -> operation
        # The hash is 6 characters (from hex(id(self))[2:8])
        # So we need to skip "redis_cloud_" (12 chars) + hash (6 chars) + "_" (1 char) = 19 chars
        prefix = f"{self.provider_name}_{self._instance_hash}_"
        if tool_name.startswith(prefix):
            operation = tool_name[len(prefix) :]
        else:
            # Fallback: try to extract operation from the end
            parts = tool_name.split("_")
            if len(parts) >= 3:
                # Skip provider name and hash, take the rest
                operation = "_".join(parts[2:])
            else:
                operation = tool_name

        client = self.get_client()

        # Account operations
        if operation == "get_account":
            obj = await get_current_account.asyncio(client=client)
            return obj.to_dict() if hasattr(obj, "to_dict") else obj
        elif operation == "get_regions":
            obj = await get_supported_regions.asyncio(client=client)
            data = obj.to_dict() if hasattr(obj, "to_dict") else obj
            return data.get("regions", []) if isinstance(data, dict) else []

        # Subscription operations
        elif operation == "list_subscriptions":
            # Pro subscriptions (Essentials list is separate if needed)
            obj = await pro_list_subscriptions.asyncio(client=client)
            return obj.to_dict() if hasattr(obj, "to_dict") else obj
        elif operation == "get_subscription":
            if self._subscription_id is None:
                raise ValueError("Redis Cloud subscription ID is not configured for this instance.")
            stype = (self._subscription_type or "").lower() if self._subscription_type else None
            if stype == "essentials" or stype == "fixed":
                obj = await ess_get_subscription_by_id.asyncio(
                    subscription_id=self._subscription_id, client=client
                )
                if obj is not None:
                    return obj.to_dict() if hasattr(obj, "to_dict") else obj
                # Fallback to pro if not found
                obj = await pro_get_subscription_by_id.asyncio(
                    subscription_id=self._subscription_id, client=client
                )
                if obj is None:
                    raise ValueError(
                        f"Subscription {self._subscription_id} not found (essentials or pro)."
                    )
                return obj.to_dict() if hasattr(obj, "to_dict") else obj
            if stype == "pro":
                obj = await pro_get_subscription_by_id.asyncio(
                    subscription_id=self._subscription_id, client=client
                )
                if obj is None:
                    # Fallback to essentials in case type was incorrect
                    obj = await ess_get_subscription_by_id.asyncio(
                        subscription_id=self._subscription_id, client=client
                    )
                    if obj is None:
                        raise ValueError(
                            f"Subscription {self._subscription_id} not found (pro or essentials)."
                        )
                return obj.to_dict() if hasattr(obj, "to_dict") else obj
            # Unknown type: try essentials then pro
            obj = await ess_get_subscription_by_id.asyncio(
                subscription_id=self._subscription_id, client=client
            )
            if obj is None:
                obj = await pro_get_subscription_by_id.asyncio(
                    subscription_id=self._subscription_id, client=client
                )
                if obj is None:
                    raise ValueError(f"Subscription {self._subscription_id} not found.")
            return obj.to_dict() if hasattr(obj, "to_dict") else obj

        # Database operations
        elif operation == "list_databases":
            if self._subscription_id is None:
                raise ValueError("Redis Cloud subscription ID is not configured for this instance.")
            stype = (self._subscription_type or "").lower() if self._subscription_type else None

            # Helper to normalize Pro response shape
            def _extract_pro_dbs(payload: Any) -> list:
                data = payload.to_dict() if hasattr(payload, "to_dict") else payload
                subs = data.get("subscription") if isinstance(data, dict) else None
                if isinstance(subs, list) and subs:
                    return subs[0].get("databases", [])
                return []

            # Helper to normalize Essentials response shape
            def _extract_ess_dbs(payload: Any) -> list:
                data = payload.to_dict() if hasattr(payload, "to_dict") else payload
                return (
                    data.get("subscription", {}).get("databases", [])
                    if isinstance(data, dict)
                    else []
                )

            # If user specified a type, try that first but fall back to the other type on empty/None
            if stype == "pro":
                logger.debug(
                    f"Redis Cloud: listing databases (pro) for subscription {self._subscription_id}"
                )
                obj = await pro_get_subscription_databases.asyncio(
                    subscription_id=self._subscription_id, client=client
                )
                dbs = _extract_pro_dbs(obj) if obj is not None else []
                if dbs:
                    return dbs
                logger.debug(
                    "Redis Cloud: no results from pro endpoint, falling back to essentials"
                )
                obj = await ess_get_subscription_databases.asyncio(
                    subscription_id=self._subscription_id, client=client
                )
                return _extract_ess_dbs(obj) if obj is not None else []

            if stype == "essentials" or stype == "fixed":
                logger.debug(
                    f"Redis Cloud: listing databases (essentials) for subscription {self._subscription_id}"
                )
                obj = await ess_get_subscription_databases.asyncio(
                    subscription_id=self._subscription_id, client=client
                )
                dbs = _extract_ess_dbs(obj) if obj is not None else []
                if dbs:
                    return dbs
                logger.debug(
                    "Redis Cloud: no results from essentials endpoint, falling back to pro"
                )
                obj = await pro_get_subscription_databases.asyncio(
                    subscription_id=self._subscription_id, client=client
                )
                return _extract_pro_dbs(obj) if obj is not None else []

            # Unknown type: try essentials first; if empty, try pro
            logger.debug(
                f"Redis Cloud: listing databases (auto-detect) for subscription {self._subscription_id}"
            )
            obj = await ess_get_subscription_databases.asyncio(
                subscription_id=self._subscription_id, client=client
            )
            dbs = _extract_ess_dbs(obj) if obj is not None else []
            if dbs:
                return dbs
            obj = await pro_get_subscription_databases.asyncio(
                subscription_id=self._subscription_id, client=client
            )
            return _extract_pro_dbs(obj) if obj is not None else []
        elif operation == "get_database":
            if self._subscription_id is None:
                raise ValueError("Redis Cloud subscription ID is not configured for this instance.")
            stype = (self._subscription_type or "").lower() if self._subscription_type else None
            # Prefer ID; fallback to name if provided
            if self._database_id is not None:
                if stype == "essentials" or stype == "fixed":
                    logger.debug(
                        f"Redis Cloud: get database (essentials) sub={self._subscription_id} db={self._database_id}"
                    )
                    obj = await ess_get_subscription_database_by_id.asyncio(
                        subscription_id=self._subscription_id,
                        database_id=self._database_id,
                        client=client,
                    )
                    if obj is not None:
                        return obj.to_dict() if hasattr(obj, "to_dict") else obj
                    logger.debug("Redis Cloud: not found on essentials endpoint, trying pro")
                    obj = await pro_get_subscription_database_by_id.asyncio(
                        subscription_id=self._subscription_id,
                        database_id=self._database_id,
                        client=client,
                    )
                    if obj is None:
                        raise ValueError(
                            f"Database {self._database_id} not found in subscription {self._subscription_id}."
                        )
                    return obj.to_dict() if hasattr(obj, "to_dict") else obj
                if stype == "pro":
                    logger.debug(
                        f"Redis Cloud: get database (pro) sub={self._subscription_id} db={self._database_id}"
                    )
                    obj = await pro_get_subscription_database_by_id.asyncio(
                        subscription_id=self._subscription_id,
                        database_id=self._database_id,
                        client=client,
                    )
                    if obj is not None:
                        return obj.to_dict() if hasattr(obj, "to_dict") else obj
                    logger.debug("Redis Cloud: not found on pro endpoint, trying essentials")
                    obj = await ess_get_subscription_database_by_id.asyncio(
                        subscription_id=self._subscription_id,
                        database_id=self._database_id,
                        client=client,
                    )
                    if obj is None:
                        raise ValueError(
                            f"Database {self._database_id} not found in subscription {self._subscription_id}."
                        )
                    return obj.to_dict() if hasattr(obj, "to_dict") else obj
                # Unknown type: try essentials, then pro
                logger.debug(
                    f"Redis Cloud: get database (auto-detect) sub={self._subscription_id} db={self._database_id}"
                )
                obj = await ess_get_subscription_database_by_id.asyncio(
                    subscription_id=self._subscription_id,
                    database_id=self._database_id,
                    client=client,
                )
                if obj is None:
                    obj = await pro_get_subscription_database_by_id.asyncio(
                        subscription_id=self._subscription_id,
                        database_id=self._database_id,
                        client=client,
                    )
                    if obj is None:
                        raise ValueError(
                            f"Database {self._database_id} not found in subscription {self._subscription_id}."
                        )
                return obj.to_dict() if hasattr(obj, "to_dict") else obj

            if self._database_name:
                dbs = await self.resolve_tool_call(self._make_tool_name("list_databases"), {})
                matches = [d for d in dbs if str(d.get("name")) == str(self._database_name)]
                if not matches:
                    raise ValueError(
                        f"Database named '{self._database_name}' not found in subscription {self._subscription_id}."
                    )
                if len(matches) > 1:
                    raise ValueError(
                        f"Multiple databases named '{self._database_name}' found; please specify database ID."
                    )
                return matches[0]
            raise ValueError(
                "Redis Cloud database identifier is not configured for this instance (provide database ID or name)."
            )

        # User operations
        elif operation == "list_users":
            return await client.list_users()
        elif operation == "get_user":
            return await client.get_user(args["user_id"])

        # Task operations
        elif operation == "list_tasks":
            return await client.list_tasks()
        elif operation == "get_task":
            return await client.get_task(args["task_id"])

        # Cloud account operations
        elif operation == "list_cloud_accounts":
            return await client.list_cloud_accounts()

        else:
            raise ValueError(f"Unknown operation: {operation} (from tool: {tool_name})")

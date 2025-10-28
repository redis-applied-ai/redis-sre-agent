"""Redis Enterprise admin API tool provider.

This provider uses the Redis Enterprise REST API to inspect and manage clusters.
It provides read-only tools for cluster inspection, database information, node status,
and other administrative functions exposed by the Redis Enterprise admin API.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.tools.decorators import status_update
from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

logger = logging.getLogger(__name__)


class RedisEnterpriseAdminConfig(BaseSettings):
    """Configuration for Redis Enterprise admin API provider.

    This config is used for default/fallback values only. The actual admin URL,
    username, and password should come from the RedisInstance object's admin_url,
    admin_username, and admin_password fields.

    Automatically loads from environment variables with TOOLS_REDIS_ENTERPRISE_ADMIN_ prefix:
    - TOOLS_REDIS_ENTERPRISE_ADMIN_VERIFY_SSL

    Example:
        # Loads from environment automatically
        config = RedisEnterpriseAdminConfig()

        # Or override with explicit values
        config = RedisEnterpriseAdminConfig(verify_ssl=False)
    """

    model_config = SettingsConfigDict(env_prefix="tools_redis_enterprise_admin_")

    verify_ssl: bool = Field(
        default=False,
        description="Verify SSL certificates (default: False to support self-signed certs in Docker Compose)",
    )


class RedisEnterpriseAdminToolProvider(ToolProvider):
    """Redis Enterprise admin API provider.

    Provides tools for inspecting Redis Enterprise clusters, including:
    - Cluster information and settings
    - Database (BDB) listing and details
    - Node status and information
    - Module information
    - Statistics and metrics

    The admin API URL, username, and password are taken from the RedisInstance object:
    - redis_instance.admin_url: Cluster admin API URL (e.g., https://cluster.example.com:9443)
    - redis_instance.admin_username: Admin username
    - redis_instance.admin_password: Admin password

    The RedisInstance must have instance_type='redis_enterprise' and admin_url set.
    """

    # Also provide DIAGNOSTICS capability so HostTelemetry can use system_hosts()
    from redis_sre_agent.tools.protocols import ToolCapability

    capabilities = {ToolCapability.DIAGNOSTICS}

    def __init__(
        self,
        redis_instance: RedisInstance,
        config: Optional[RedisEnterpriseAdminConfig] = None,
    ):
        """Initialize the Redis Enterprise admin API provider.

        Args:
            redis_instance: Redis instance with admin_url, admin_username, and admin_password
            config: Optional config for SSL verification settings (loaded from env if not provided)

        Raises:
            ValueError: If redis_instance is None or missing required admin fields
        """
        super().__init__(redis_instance)

        if redis_instance is None:
            raise ValueError("RedisInstance is required for Redis Enterprise admin API provider")

        if not redis_instance.admin_url:
            raise ValueError(
                f"RedisInstance '{redis_instance.name}' must have admin_url set for Redis Enterprise admin API"
            )

        # Load config from environment if not provided (for SSL settings)
        if config is None:
            config = RedisEnterpriseAdminConfig()

        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        return "re_admin"  # Shortened to avoid OpenAI 64-char tool name limit

    def get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client (lazy initialization).

        Uses admin_url, admin_username, and admin_password from the RedisInstance.

        Returns:
            httpx.AsyncClient: Initialized HTTP client
        """
        if self._client is None:
            # Get credentials from the instance
            from pydantic import SecretStr

            admin_url = self.redis_instance.admin_url
            admin_username = self.redis_instance.admin_username or ""

            # Extract secret value if it's a SecretStr
            admin_password_field = self.redis_instance.admin_password
            if isinstance(admin_password_field, SecretStr):
                admin_password = admin_password_field.get_secret_value()
            else:
                admin_password = admin_password_field or ""

            # Create auth tuple only if username is provided
            auth = (admin_username, admin_password) if admin_username else None

            if not auth:
                logger.warning(
                    "No admin credentials provided - API calls will likely fail with 401"
                )

            self._client = httpx.AsyncClient(
                base_url=admin_url,
                auth=auth,
                verify=self.config.verify_ssl,
                timeout=30.0,
                headers={
                    # Be explicit to avoid 406 content negotiation issues on some endpoints
                    "Accept": "application/json",
                },
            )
            logger.info(f"Connected to Redis Enterprise admin API at {admin_url}")
        return self._client

    def resolve_operation(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        """Parse operation name from full tool name for status updates.

        Overrides the base implementation to handle operations with underscores,
        matching the provider's tool name scheme: {provider}_{hash}_{operation}.
        """
        try:
            import re

            match = re.search(r"_([0-9a-f]{6})_(.+)$", tool_name)
            return match.group(2) if match else None
        except Exception:
            return None

    async def __aenter__(self):
        """Support async context manager (no-op, client is lazily initialized)."""
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Support async context manager - cleanup HTTP client."""
        if self._client:
            await self._client.aclose()
        self._client = None

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Create tool schemas for Redis Enterprise admin API operations."""
        return [
            ToolDefinition(
                name=self._make_tool_name("get_cluster_info"),
                description=(
                    "Get Redis Enterprise cluster information including name, settings, "
                    "alert configuration, email settings, and rack awareness. "
                    "Use this to understand cluster-level configuration and status."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("list_databases"),
                description=(
                    "List all databases (BDBs) in the Redis Enterprise cluster. "
                    "Returns database UIDs, names, and optionally other fields. "
                    "Use this to discover what databases exist in the cluster."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "fields": {
                            "type": "string",
                            "description": (
                                "Comma-separated list of field names to return. "
                                "Examples: 'uid,name,memory_size,status'. "
                                "Leave empty to return all fields."
                            ),
                        }
                    },
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_database"),
                description=(
                    "Get detailed information about a specific database (BDB) by its UID. "
                    "Returns configuration, status, memory usage, replication settings, "
                    "persistence configuration, and more. Use this to inspect a specific database."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "uid": {
                            "type": "integer",
                            "description": "The unique ID of the database to retrieve",
                        },
                        "fields": {
                            "type": "string",
                            "description": (
                                "Comma-separated list of field names to return. "
                                "Leave empty to return all fields."
                            ),
                        },
                    },
                    "required": ["uid"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("list_nodes"),
                description=(
                    "List all nodes in the Redis Enterprise cluster. "
                    "Returns node information including status, addresses, resources, "
                    "and shard placement. Use this to understand cluster topology."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "fields": {
                            "type": "string",
                            "description": (
                                "Comma-separated list of field names to return. "
                                "Leave empty to return all fields."
                            ),
                        }
                    },
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_node"),
                description=(
                    "Get detailed information about a specific node by its UID. "
                    "Returns node status, resources, addresses, shards, and configuration. "
                    "Use this to inspect a specific cluster node."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "uid": {
                            "type": "integer",
                            "description": "The unique ID of the node to retrieve",
                        },
                        "fields": {
                            "type": "string",
                            "description": (
                                "Comma-separated list of field names to return. "
                                "Leave empty to return all fields."
                            ),
                        },
                    },
                    "required": ["uid"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("list_modules"),
                description=(
                    "List all Redis modules available in the cluster. "
                    "Returns module names, versions, capabilities, and semantic version. "
                    "Use this to see what Redis modules (RediSearch, RedisJSON, etc.) are available."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_database_stats"),
                description=(
                    "Get statistics for a specific database including throughput, latency, "
                    "memory usage, connections, and other performance metrics. "
                    "Use this to monitor database performance."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "uid": {
                            "type": "integer",
                            "description": "The unique ID of the database",
                        },
                        "interval": {
                            "type": "string",
                            "description": (
                                "Statistics interval: '1sec', '1hour', '1day', '1week'. "
                                "Default: '1sec'"
                            ),
                        },
                    },
                    "required": ["uid"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_cluster_stats"),
                description=(
                    "Get cluster-wide statistics including total throughput, memory usage, "
                    "CPU utilization, and network I/O across all nodes. "
                    "Use this to monitor overall cluster health and performance."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "interval": {
                            "type": "string",
                            "description": (
                                "Statistics interval: '1sec', '1hour', '1day', '1week'. "
                                "Default: '1sec'"
                            ),
                        },
                    },
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_logs"),
                description=(
                    "Get recent cluster event logs from the Admin API (/v1/logs). "
                    "Use this for an authoritative history of cluster events (maintenance, DB changes, etc.)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "order": {
                            "type": "string",
                            "enum": ["asc", "desc"],
                            "description": "Sort order (default: desc)",
                        },
                        "limit": {"type": "integer", "description": "Max number of log records"},
                        "offset": {"type": "integer", "description": "Offset for pagination"},
                        "stime": {"type": "string", "description": "Start time (RFC3339 or epoch)"},
                        "etime": {"type": "string", "description": "End time (RFC3339 or epoch)"},
                    },
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("list_actions"),
                description=(
                    "List all running, pending, or completed actions in the cluster. "
                    "Actions include database operations, node operations, and other long-running tasks. "
                    "Use this to identify stuck or long-running operations, monitor progress, "
                    "and troubleshoot issues with cluster operations."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_action"),
                description=(
                    "Get detailed status of a specific action by its UID. "
                    "Returns action progress, status, error messages, and pending operations. "
                    "Use this to monitor specific long-running operations or troubleshoot failed actions."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "action_uid": {
                            "type": "string",
                            "description": "The unique ID of the action to retrieve",
                        },
                    },
                    "required": ["action_uid"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("rebalance_status"),
                description=(
                    "Identify Redis Enterprise rebalance-related actions (including fast SMUpdateBDB cases). "
                    "Returns active and recently-completed rebalance actions. Optionally filter by database. "
                    "Automates fetching per-action details when needed to distinguish between generic SMUpdateBDB "
                    "and a true rebalance/reshard/migrate_shard operation."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "db_uid": {
                            "type": "integer",
                            "description": "Filter actions for a specific database UID (e.g., 1)",
                        },
                        "db_name": {
                            "type": "string",
                            "description": "Filter actions for a specific database name (e.g., 'test-db')",
                        },
                        "include_recent_completed": {
                            "type": "boolean",
                            "description": "Include recently-completed actions (default: true)",
                        },
                        "recent_seconds": {
                            "type": "integer",
                            "description": "How far back to look for completed actions (seconds, default: 300)",
                        },
                    },
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("list_shards"),
                description=(
                    "List all shards in the cluster with their placement, status, and role. "
                    "Returns information about which nodes host which shards, shard roles "
                    "(master/replica), and shard status. Use this to understand shard distribution "
                    "and identify shard placement issues."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "fields": {
                            "type": "string",
                            "description": (
                                "Comma-separated list of field names to return. "
                                "Leave empty to return all fields."
                            ),
                        }
                    },
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_shard"),
                description=(
                    "Get detailed information about a specific shard by its UID. "
                    "Returns shard configuration, status, assigned slots, role, and node placement. "
                    "Use this to inspect a specific shard's state."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "uid": {
                            "type": "integer",
                            "description": "The unique ID of the shard to retrieve",
                        },
                    },
                    "required": ["uid"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_cluster_alerts"),
                description=(
                    "Get cluster-level alert settings and configuration. "
                    "Returns information about which alerts are enabled and their thresholds. "
                    "Use this to understand cluster alerting configuration."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_database_alerts"),
                description=(
                    "Get alert configuration for a specific database. "
                    "Returns database-specific alert settings and thresholds. "
                    "Use this to check what alerts are configured for a database."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "uid": {
                            "type": "integer",
                            "description": "The unique ID of the database",
                        },
                    },
                    "required": ["uid"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_node_stats"),
                description=(
                    "Get statistics for a specific node including CPU, memory, network, "
                    "and disk I/O metrics. Use this to monitor individual node performance."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "uid": {
                            "type": "integer",
                            "description": "The unique ID of the node",
                        },
                        "interval": {
                            "type": "string",
                            "description": (
                                "Statistics interval: '1sec', '1hour', '1day', '1week'. "
                                "Default: '1sec'"
                            ),
                        },
                    },
                    "required": ["uid"],
                },
            ),
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a Redis Enterprise admin API tool call.

        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments

        Returns:
            Tool execution result
        """
        # Parse operation from tool_name
        # Format: {provider_name}_{instance_hash}_{operation}
        # Example: re_admin_ffffa3_get_cluster_info
        # The instance_hash is always 6 hex characters
        import re

        # Match the pattern: underscore + 6 hex chars + underscore + operation
        match = re.search(r"_([0-9a-f]{6})_(.+)$", tool_name)
        if match:
            operation = match.group(2)  # Everything after the hash
        else:
            # Fallback: couldn't parse, use the whole name
            operation = tool_name

        if operation == "get_cluster_info":
            return await self.get_cluster_info()
        elif operation == "list_databases":
            return await self.list_databases(**args)
        elif operation == "get_database":
            return await self.get_database(**args)
        elif operation == "list_nodes":
            return await self.list_nodes(**args)
        elif operation == "get_node":
            return await self.get_node(**args)
        elif operation == "list_modules":
            return await self.list_modules()
        elif operation == "get_database_stats":
            return await self.get_database_stats(**args)
        elif operation == "get_cluster_stats":
            return await self.get_cluster_stats(**args)
        elif operation == "get_logs":
            return await self.get_logs(**args)

        elif operation == "list_actions":
            return await self.list_actions()
        elif operation == "get_action":
            return await self.get_action(**args)
        elif operation == "rebalance_status":
            return await self.rebalance_status(**args)
        elif operation == "list_shards":
            return await self.list_shards(**args)
        elif operation == "get_shard":
            return await self.get_shard(**args)
        elif operation == "get_cluster_alerts":
            return await self.get_cluster_alerts()
        elif operation == "get_database_alerts":
            return await self.get_database_alerts(**args)
        elif operation == "get_node_stats":
            return await self.get_node_stats(**args)
        else:
            raise ValueError(f"Unknown operation: {operation} (from tool: {tool_name})")

    @status_update("I'm querying the Redis Enterprise Admin API for cluster info.")
    async def get_cluster_info(self) -> Dict[str, Any]:
        """Get cluster information.

        Returns:
            Cluster information including name, settings, and configuration
        """
        logger.info("Getting Redis Enterprise cluster info")
        try:
            client = self.get_client()
            response = await client.get("/v1/cluster")
            response.raise_for_status()

            return {
                "status": "success",
                "data": response.json(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting cluster info: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to get cluster info: {e}")

            # Provide helpful message for SSL errors
            if "CERTIFICATE_VERIFY_FAILED" in error_msg or "certificate verify failed" in error_msg:
                error_msg = (
                    f"SSL certificate verification failed: {e}. "
                    "This is common with self-signed certificates. "
                    "Set TOOLS_REDIS_ENTERPRISE_ADMIN_VERIFY_SSL=false in environment to disable SSL verification."
                )

            return {
                "status": "error",
                "error": error_msg,
            }

    @status_update("I'm listing databases via the Redis Enterprise Admin API.")
    async def list_databases(self, fields: Optional[str] = None) -> Dict[str, Any]:
        """List all databases in the cluster.

        Args:
            fields: Comma-separated list of fields to return

        Returns:
            List of databases with requested fields
        """
        logger.info(f"Listing databases (fields={fields})")
        try:
            client = self.get_client()
            params = {}
            if fields:
                params["fields"] = fields

            try:
                response = await client.get("/v1/bdbs", params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                # Some Redis Enterprise versions do not accept 'fields' on this endpoint
                if e.response.status_code in (406, 400) and fields:
                    logger.warning(
                        f"list_databases(fields={fields}) failed with {e.response.status_code}; retrying without fields"
                    )
                    response = await client.get("/v1/bdbs")
                    response.raise_for_status()
                else:
                    raise

            databases = response.json()
            return {
                "status": "success",
                "count": len(databases) if isinstance(databases, list) else 1,
                "databases": databases,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error listing databases: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except Exception as e:
            logger.error(f"Failed to list databases: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    @status_update(
        "I'm retrieving database details from the Redis Enterprise Admin API for database {uid}."
    )
    async def get_database(self, uid: int, fields: Optional[str] = None) -> Dict[str, Any]:
        """Get information about a specific database.

        Args:
            uid: Database unique ID
            fields: Comma-separated list of fields to return

        Returns:
            Database information
        """
        logger.info(f"Getting database {uid} (fields={fields})")
        try:
            client = self.get_client()
            params = {}
            if fields:
                params["fields"] = fields

            try:
                response = await client.get(f"/v1/bdbs/{uid}", params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                # Some Redis Enterprise versions return 406 when 'fields' is not supported on this endpoint
                if e.response.status_code in (406, 400) and fields:
                    logger.warning(
                        f"get_database({uid}) with fields failed ({e.response.status_code}); retrying without fields"
                    )
                    response = await client.get(f"/v1/bdbs/{uid}")
                    response.raise_for_status()
                else:
                    raise

            return {
                "status": "success",
                "database": response.json(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting database {uid}: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "uid": uid,
            }
        except Exception as e:
            logger.error(f"Failed to get database {uid}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "uid": uid,
            }

    @status_update("I'm listing cluster nodes via the Redis Enterprise Admin API.")
    async def list_nodes(self, fields: Optional[str] = None) -> Dict[str, Any]:
        """List all nodes in the cluster.

        Args:
            fields: Comma-separated list of fields to return

        Returns:
            List of nodes with requested fields
        """
        logger.info(f"Listing nodes (fields={fields})")
        try:
            client = self.get_client()
            params = {}
            if fields:
                params["fields"] = fields

            response = await client.get("/v1/nodes", params=params)
            response.raise_for_status()

            nodes = response.json()
            return {
                "status": "success",
                "count": len(nodes),
                "nodes": nodes,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error listing nodes: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except Exception as e:
            logger.error(f"Failed to list nodes: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    @status_update(
        "I'm retrieving node details from the Redis Enterprise Admin API for node {uid}."
    )
    async def get_node(self, uid: int, fields: Optional[str] = None) -> Dict[str, Any]:
        """Get information about a specific node.

        Args:
            uid: Node unique ID
            fields: Comma-separated list of fields to return

        Returns:
            Node information
        """
        logger.info(f"Getting node {uid} (fields={fields})")
        try:
            client = self.get_client()
            params = {}
            if fields:
                params["fields"] = fields

            response = await client.get(f"/v1/nodes/{uid}", params=params)
            response.raise_for_status()

            return {
                "status": "success",
                "node": response.json(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting node {uid}: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "uid": uid,
            }
        except Exception as e:
            logger.error(f"Failed to get node {uid}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "uid": uid,
            }

    @status_update("I'm listing available Redis modules via the Redis Enterprise Admin API.")
    async def list_modules(self) -> Dict[str, Any]:
        """List all available Redis modules.

        Returns:
            List of modules with their versions and capabilities
        """
        logger.info("Listing Redis modules")
        try:
            client = self.get_client()
            response = await client.get("/v1/modules")
            response.raise_for_status()

            modules = response.json()
            return {
                "status": "success",
                "count": len(modules),
                "modules": modules,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error listing modules: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except Exception as e:
            logger.error(f"Failed to list modules: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    @status_update(
        "I'm fetching database performance stats via the Admin API for database {uid} (interval={interval})."
    )
    async def get_database_stats(self, uid: int, interval: str = "1sec") -> Dict[str, Any]:
        """Get statistics for a specific database.

        Args:
            uid: Database unique ID
            interval: Statistics interval (1sec, 1hour, 1day, 1week)

        Returns:
            Database statistics
        """
        logger.info(f"Getting database {uid} stats (interval={interval})")
        try:
            client = self.get_client()
            params = {"interval": interval}

            response = await client.get(f"/v1/bdbs/stats/{uid}", params=params)
            response.raise_for_status()

            return {
                "status": "success",
                "uid": uid,
                "interval": interval,
                "stats": response.json(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting database {uid} stats: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "uid": uid,
            }
        except Exception as e:
            logger.error(f"Failed to get database {uid} stats: {e}")
            return {
                "status": "error",
                "error": str(e),
                "uid": uid,
            }

    @status_update(
        "I'm fetching cluster-wide performance stats via the Redis Enterprise Admin API (interval={interval})."
    )
    async def get_cluster_stats(self, interval: str = "1sec") -> Dict[str, Any]:
        """Get cluster-wide statistics.

        Args:
            interval: Statistics interval (1sec, 1hour, 1day, 1week)

        Returns:
            Cluster statistics
        """
        logger.info(f"Getting cluster stats (interval={interval})")
        try:
            client = self.get_client()
            params = {"interval": interval}
            response = await client.get("/v1/cluster/stats", params=params)
            response.raise_for_status()
            return {
                "status": "success",
                "interval": interval,
                "stats": response.json(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting cluster stats: {e}")
            return {"status": "error", "error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            logger.error(f"Failed to get cluster stats: {e}")
            return {"status": "error", "error": str(e)}

    def _normalize_time_param(self, value: Optional[str]) -> Optional[str]:
        """Normalize time parameters for Admin API.

        - "now" -> current UTC ISO8601
        - integer epoch seconds -> ISO8601 UTC
        - otherwise, pass through unchanged
        """
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        if s.lower() == "now":
            return datetime.now(timezone.utc).isoformat()
        if s.isdigit():
            try:
                return datetime.fromtimestamp(int(s), tz=timezone.utc).isoformat()
            except Exception:
                return None
        return s

    @status_update("I'm fetching cluster event logs via the Redis Enterprise Admin API.")
    async def get_logs(
        self,
        order: str = "desc",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        stime: Optional[str] = None,
        etime: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get cluster event logs from /v1/logs.

        Args:
            order: Sort order (asc|desc)
            limit: Max records to return
            offset: Pagination offset
            stime: Start time (RFC3339 or epoch)
            etime: End time (RFC3339 or epoch)
        """
        logger.info("Getting cluster logs")
        try:
            client = self.get_client()
            params: Dict[str, Any] = {}
            if order:
                params["order"] = order
            if limit is not None:
                params["limit"] = int(limit)
            if offset is not None:
                params["offset"] = int(offset)
            st = self._normalize_time_param(stime)
            et = self._normalize_time_param(etime)
            if st:
                params["stime"] = st
            if et:
                params["etime"] = et

            response = await client.get("/v1/logs", params=params)
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "count": len(data) if isinstance(data, list) else 1,
                "logs": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else 0
            msg = f"HTTP {code}: {e.response.text if e.response is not None else str(e)}"
            if 500 <= code < 600:
                logger.warning(f"Admin API /v1/logs unavailable: {msg}")
                return {"status": "unavailable", "error": msg}
            logger.warning(f"HTTP error getting cluster logs: {msg}")
            return {"status": "error", "error": msg}
        except Exception as e:
            logger.warning(f"Failed to get cluster logs: {e}")
            return {"status": "error", "error": str(e)}

    @status_update("I'm listing cluster actions via the Redis Enterprise Admin API.")
    async def list_actions(self) -> Dict[str, Any]:
        """List all actions in the cluster.

        Returns:
            List of all running, pending, or completed actions
        """
        logger.info("Listing cluster actions")
        try:
            client = self.get_client()
            # Use v2 API for more comprehensive action information
            response = await client.get("/v2/actions")
            response.raise_for_status()

            actions = response.json()
            return {
                "status": "success",
                "count": len(actions),
                "actions": actions,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error listing actions: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except Exception as e:
            logger.error(f"Failed to list actions: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    @status_update(
        "I'm checking the status of action {action_uid} via the Redis Enterprise Admin API."
    )
    async def get_action(self, action_uid: str) -> Dict[str, Any]:
        """Get information about a specific action.

        Args:
            action_uid: Action unique ID

        Returns:
            Action status and details
        """
        logger.info(f"Getting action {action_uid}")
        try:
            client = self.get_client()
            # Use v2 API for more comprehensive action information
            response = await client.get(f"/v2/actions/{action_uid}")
            response.raise_for_status()

            return {
                "status": "success",
                "action": response.json(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting action {action_uid}: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "action_uid": action_uid,
            }
        except Exception as e:
            logger.error(f"Failed to get action {action_uid}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "action_uid": action_uid,
            }

    @status_update("I'm listing shards and their placement via the Redis Enterprise Admin API.")
    async def list_shards(self, fields: Optional[str] = None) -> Dict[str, Any]:
        """List all shards in the cluster.

        Args:
            fields: Comma-separated list of fields to return

        Returns:
            List of shards with requested fields
        """
        logger.info(f"Listing shards (fields={fields})")
        try:
            client = self.get_client()
            params = {}
            if fields:
                params["fields"] = fields

            response = await client.get("/v1/shards", params=params)
            response.raise_for_status()

            shards = response.json()
            return {
                "status": "success",
                "count": len(shards),
                "shards": shards,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error listing shards: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except Exception as e:
            logger.error(f"Failed to list shards: {e}")
            return {"status": "error", "error": str(e)}

    async def system_hosts(self) -> List[Any]:
        """Discover Enterprise cluster node hosts via Admin API.

        Returns SystemHost entries using /v1/nodes 'addr' field.
        """
        from redis_sre_agent.tools.protocols import SystemHost

        try:
            client = self.get_client()
            resp = await client.get("/v1/nodes")
            resp.raise_for_status()
            nodes = resp.json() or []
            results: List[SystemHost] = []
            for n in nodes:
                try:
                    addr = n.get("addr") if isinstance(n, dict) else None
                    if isinstance(addr, str) and addr:
                        results.append(
                            SystemHost(
                                host=addr, role="enterprise-node", labels={"source": "admin_api"}
                            )
                        )
                except Exception:
                    continue
            return results
        except Exception:
            return []

    def _is_action_rebalance_like(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """Heuristically determine if an action is rebalance-related.

        Returns (is_rebalance, reason) where reason explains the match.
        """
        try:
            name = str(action.get("name") or "").lower()
            if any(k in name for k in ("rebalance", "migrate_shard", "reshard")):
                return True, f"name={action.get('name')}"

            if "smupdatebdb" in name:
                # Inspect nested details if present
                addl = action.get("additional_info") or {}
                pending = addl.get("pending_ops") or {}
                for _shard, op in pending.items() if isinstance(pending, dict) else []:
                    op_name = str((op or {}).get("op_name") or "").lower()
                    desc = str((op or {}).get("status_description") or "").lower()
                    if any(key in op_name for key in ("migrate", "reshard", "rebalance")) or any(
                        key in desc for key in ("migrate", "reshard", "rebalance")
                    ):
                        return True, f"SMUpdateBDB pending_ops={op_name or desc}"

                # Some APIs use a flat 'pending_ops' directly
                pending2 = action.get("pending_ops") or {}
                for _k, v in pending2.items() if isinstance(pending2, dict) else []:
                    op_name = str((v or {}).get("op_name") or "").lower()
                    if any(key in op_name for key in ("migrate", "reshard", "rebalance")):
                        return True, f"SMUpdateBDB pending_ops={op_name}"
        except Exception:
            pass
        return False, "no-match"

    @status_update(
        "I'm analyzing cluster actions to detect active or recent rebalances via the Admin API."
    )
    async def rebalance_status(
        self,
        db_uid: Optional[int] = None,
        db_name: Optional[str] = None,
        include_recent_completed: bool = True,
        recent_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Identify rebalance-related actions, including fast SMUpdateBDB cases.

        - Consumes /v2/actions
        - Optionally fetches /v2/actions/{uid} for ambiguous SMUpdateBDB actions
        - Optionally filters by database (db_uid or db_name)
        - Returns active and recently completed (within recent_seconds) results
        """
        import time as _time

        try:
            # Resolve db_uid from db_name when requested
            resolved_db_uid: Optional[int] = db_uid
            resolved_db_name: Optional[str] = None
            if db_name and not resolved_db_uid:
                dbs = await self.list_databases(fields="uid,name")
                for db in dbs.get("databases") or []:
                    if str(db.get("name") or "").lower() == str(db_name).lower():
                        resolved_db_uid = int(db.get("uid"))
                        resolved_db_name = db.get("name")
                        break

            # Fetch actions
            actions_env = await self.list_actions()
            actions = actions_env.get("actions") or []

            now = int(_time.time())
            active: List[Dict[str, Any]] = []
            recent_completed: List[Dict[str, Any]] = []

            # Helper to extract db_uid from object_name like 'bdb:1'
            def _extract_db_uid(obj_name: Optional[str]) -> Optional[int]:
                if not obj_name:
                    return None
                try:
                    s = str(obj_name)
                    if "bdb:" in s:
                        return int(s.split("bdb:")[-1].split()[0].strip())
                except Exception:
                    return None
                return None

            # Iterate and classify
            for a in actions:
                name = str(a.get("name") or "")
                status = str(a.get("status") or "").lower()
                creation_time = a.get("creation_time")  # epoch seconds (int)
                obj_name = a.get("object_name")
                action_uid = a.get("action_uid")

                # Filter by db if requested
                a_db_uid = _extract_db_uid(obj_name)
                if (
                    resolved_db_uid is not None
                    and a_db_uid is not None
                    and a_db_uid != resolved_db_uid
                ):
                    continue
                # If object_name missing and filter requested, we'll still try to classify (can't filter by db)

                is_reb, reason = self._is_action_rebalance_like(a)

                # If ambiguous SMUpdateBDB without clear ops, fetch details
                if not is_reb and name.lower().startswith("smupdatebdb") and action_uid:
                    detail = await self.get_action(action_uid)
                    if detail.get("status") == "success":
                        d_action = detail.get("action") or {}
                        is_reb, reason = self._is_action_rebalance_like(d_action)
                        if not obj_name:
                            obj_name = d_action.get("object_name") or obj_name
                            a_db_uid = _extract_db_uid(obj_name)

                if not is_reb:
                    continue

                row = {
                    "action_uid": action_uid,
                    "name": name,
                    "status": status,
                    "progress": a.get("progress"),
                    "object_name": obj_name,
                    "db_uid": a_db_uid,
                    "reason": reason,
                    "creation_time": creation_time,
                }

                if status in {"running", "queued", "active", "pending"}:
                    active.append(row)
                elif include_recent_completed and status == "completed":
                    try:
                        if isinstance(creation_time, (int, float)) and (
                            now - int(creation_time)
                        ) <= int(recent_seconds):
                            recent_completed.append(row)
                    except Exception:
                        # If timestamp missing/malformed, skip recent filter
                        pass

            result: Dict[str, Any] = {
                "status": "success",
                "active": active,
                "recent_completed": recent_completed if include_recent_completed else [],
                "filter": {
                    "db_uid": resolved_db_uid,
                    "db_name": resolved_db_name or db_name,
                    "recent_seconds": recent_seconds,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return result
        except Exception as e:
            logger.error(f"Failed to analyze rebalance status: {e}")
            return {"status": "error", "error": str(e)}

    @status_update(
        "I'm retrieving shard details from the Redis Enterprise Admin API for shard {uid}."
    )
    async def get_shard(self, uid: int) -> Dict[str, Any]:
        """Get information about a specific shard.

        Args:
            uid: Shard unique ID

        Returns:
            Shard information
        """
        logger.info(f"Getting shard {uid}")
        try:
            client = self.get_client()
            response = await client.get(f"/v1/shards/{uid}")
            response.raise_for_status()

            return {
                "status": "success",
                "shard": response.json(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting shard {uid}: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "uid": uid,
            }
        except Exception as e:
            logger.error(f"Failed to get shard {uid}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "uid": uid,
            }

    @status_update("I'm retrieving cluster alert settings via the Redis Enterprise Admin API.")
    async def get_cluster_alerts(self) -> Dict[str, Any]:
        """Get cluster alert settings.

        Returns:
            Cluster alert configuration
        """
        logger.info("Getting cluster alerts")
        try:
            client = self.get_client()
            # Get cluster info which includes alert_settings
            response = await client.get("/v1/cluster")
            response.raise_for_status()

            cluster_data = response.json()
            return {
                "status": "success",
                "alert_settings": cluster_data.get("alert_settings", {}),
                "email_alerts": cluster_data.get("email_alerts", False),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting cluster alerts: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except Exception as e:
            logger.error(f"Failed to get cluster alerts: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    @status_update(
        "I'm retrieving alert settings via the Redis Enterprise Admin API for database {uid}."
    )
    async def get_database_alerts(self, uid: int) -> Dict[str, Any]:
        """Get alert configuration for a specific database.

        Args:
            uid: Database unique ID

        Returns:
            Database alert configuration
        """
        logger.info(f"Getting database {uid} alerts")
        try:
            client = self.get_client()
            # Per docs, database alerts endpoints live under /v1/bdbs/alerts/{uid}
            response = await client.get(f"/v1/bdbs/alerts/{uid}")
            response.raise_for_status()

            return {
                "status": "success",
                "uid": uid,
                "alerts": response.json(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting database {uid} alerts: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "uid": uid,
            }
        except Exception as e:
            logger.error(f"Failed to get database {uid} alerts: {e}")
            return {
                "status": "error",
                "error": str(e),
                "uid": uid,
            }

    @status_update(
        "I'm fetching node performance stats via the Admin API for node {uid} (interval={interval})."
    )
    async def get_node_stats(self, uid: int, interval: str = "1sec") -> Dict[str, Any]:
        """Get statistics for a specific node.

        Args:
            uid: Node unique ID
            interval: Statistics interval (1sec, 1hour, 1day, 1week)

        Returns:
            Node statistics
        """
        logger.info(f"Getting node {uid} stats (interval={interval})")
        try:
            client = self.get_client()
            params = {"interval": interval}

            response = await client.get(f"/v1/nodes/stats/{uid}", params=params)
            response.raise_for_status()

            return {
                "status": "success",
                "uid": uid,
                "interval": interval,
                "stats": response.json(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting node {uid} stats: {e}")
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "uid": uid,
            }
        except Exception as e:
            logger.error(f"Failed to get node {uid} stats: {e}")
            return {
                "status": "error",
                "error": str(e),
                "uid": uid,
            }

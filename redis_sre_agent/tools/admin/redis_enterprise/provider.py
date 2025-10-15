"""Redis Enterprise admin API tool provider.

This provider uses the Redis Enterprise REST API to inspect and manage clusters.
It provides read-only tools for cluster inspection, database information, node status,
and other administrative functions exposed by the Redis Enterprise admin API.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

logger = logging.getLogger(__name__)


class RedisEnterpriseAdminConfig(BaseSettings):
    """Configuration for Redis Enterprise admin API provider.

    Automatically loads from environment variables with TOOLS_REDIS_ENTERPRISE_ADMIN_ prefix:
    - TOOLS_REDIS_ENTERPRISE_ADMIN_URL
    - TOOLS_REDIS_ENTERPRISE_ADMIN_USERNAME
    - TOOLS_REDIS_ENTERPRISE_ADMIN_PASSWORD
    - TOOLS_REDIS_ENTERPRISE_ADMIN_VERIFY_SSL

    Example:
        # Loads from environment automatically
        config = RedisEnterpriseAdminConfig()

        # Or override with explicit values
        config = RedisEnterpriseAdminConfig(
            url="https://cluster.example.com:9443",
            username="admin@example.com",
            password="secret"
        )
    """

    model_config = SettingsConfigDict(env_prefix="tools_redis_enterprise_admin_")

    url: str = Field(
        default="https://localhost:9443", description="Redis Enterprise cluster admin API URL"
    )
    username: str = Field(default="", description="Admin API username")
    password: str = Field(default="", description="Admin API password")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")


class RedisEnterpriseAdminToolProvider(ToolProvider):
    """Redis Enterprise admin API provider.

    Provides tools for inspecting Redis Enterprise clusters, including:
    - Cluster information and settings
    - Database (BDB) listing and details
    - Node status and information
    - Module information
    - Statistics and metrics

    Configuration is loaded from environment variables:
    - TOOLS_REDIS_ENTERPRISE_ADMIN_URL: Cluster admin API URL
    - TOOLS_REDIS_ENTERPRISE_ADMIN_USERNAME: Admin username
    - TOOLS_REDIS_ENTERPRISE_ADMIN_PASSWORD: Admin password
    - TOOLS_REDIS_ENTERPRISE_ADMIN_VERIFY_SSL: Verify SSL (default: true)
    """

    def __init__(
        self,
        redis_instance: Optional[RedisInstance] = None,
        config: Optional[RedisEnterpriseAdminConfig] = None,
    ):
        """Initialize the Redis Enterprise admin API provider.

        Args:
            redis_instance: Optional Redis instance for scoped queries
            config: Optional admin API configuration (loaded from env if not provided)
        """
        super().__init__(redis_instance)

        # Load config from environment if not provided
        if config is None:
            config = RedisEnterpriseAdminConfig()

        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        return "redis_enterprise_admin"

    def get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client (lazy initialization).

        Returns:
            httpx.AsyncClient: Initialized HTTP client
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.url,
                auth=(self.config.username, self.config.password),
                verify=self.config.verify_ssl,
                timeout=30.0,
            )
            logger.info(f"Connected to Redis Enterprise admin API at {self.config.url}")
        return self._client

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
        # Format: redis_enterprise_admin_{hash}_get_cluster_info -> get_cluster_info
        # The hash is 6 characters, so we need to skip it
        parts = tool_name.split("_")
        # Find where the hash ends (it's after "admin")
        # redis_enterprise_admin_{hash}_operation
        # So we need to skip the first 4 parts (redis, enterprise, admin, hash)
        if len(parts) >= 5:
            operation = "_".join(parts[4:])  # Everything after redis_enterprise_admin_{hash}
        else:
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
        elif operation == "list_actions":
            return await self.list_actions()
        elif operation == "get_action":
            return await self.get_action(**args)
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
            logger.error(f"Failed to get cluster info: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

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

            response = await client.get("/v1/bdbs", params=params)
            response.raise_for_status()

            databases = response.json()
            return {
                "status": "success",
                "count": len(databases),
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

            response = await client.get(f"/v1/bdbs/{uid}", params=params)
            response.raise_for_status()

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
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except Exception as e:
            logger.error(f"Failed to get cluster stats: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

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
            return {
                "status": "error",
                "error": str(e),
            }

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
            response = await client.get(f"/v1/bdbs/{uid}/alerts")
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

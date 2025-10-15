"""Redis CLI diagnostics tool provider.

This provider executes Redis diagnostic commands directly via redis-py.
All commands are read-only for safety.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from redis.asyncio import Redis

from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

logger = logging.getLogger(__name__)


class RedisCliConfig(BaseModel):
    """Configuration for Redis CLI diagnostics provider.

    Note: This provider does not use configuration. All tools require
    a connection_url parameter to be passed at runtime.
    """

    pass


class RedisCliToolProvider(ToolProvider):
    """Redis CLI diagnostics provider using redis-py.

    Provides read-only diagnostic tools for Redis troubleshooting:
    - INFO command (server, memory, clients, stats, etc.)
    - SLOWLOG (performance diagnostics)
    - ACL LOG (security diagnostics)
    - CONFIG GET (configuration inspection)
    - CLIENT LIST (connection diagnostics)
    - MEMORY DOCTOR (memory analysis)
    - LATENCY DOCTOR (latency analysis)
    - CLUSTER INFO (cluster diagnostics)
    - Replication info (replication diagnostics)
    - MEMORY STATS (detailed memory breakdown)

    The provider is initialized with a connection URL and manages the Redis client lifecycle.
    """

    def __init__(
        self,
        redis_instance: Optional[RedisInstance] = None,
        connection_url: Optional[str] = None,
        config: Optional[RedisCliConfig] = None,
    ):
        """Initialize the Redis CLI diagnostics provider.

        Args:
            redis_instance: Optional Redis instance for scoped diagnostics.
                           If provided, uses its connection_url.
            connection_url: Redis connection URL (e.g., redis://localhost:6379).
                           Required if redis_instance is not provided.
            config: Optional config (unused, kept for compatibility)
        """
        super().__init__(redis_instance)

        # Get connection URL from redis_instance or parameter
        if redis_instance:
            self.connection_url = redis_instance.connection_url
        elif connection_url:
            self.connection_url = connection_url
        else:
            raise ValueError("Either redis_instance or connection_url must be provided")

        self._client: Optional[Redis] = None

    @property
    def provider_name(self) -> str:
        return "redis_cli"

    async def __aenter__(self):
        """Initialize Redis client on context entry."""
        self._client = Redis.from_url(self.connection_url, decode_responses=True)
        logger.info(f"Connected to Redis at {self.connection_url}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up on context exit."""
        if self._client:
            await self._client.aclose()
        self._client = None

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Create tool schemas for Redis CLI diagnostic operations."""
        return [
            ToolDefinition(
                name=self._make_tool_name("info"),
                description=(
                    "Execute Redis INFO command to get server statistics and information. "
                    "Use this to check Redis server status, memory usage, client connections, "
                    "replication status, and performance metrics. Can query specific sections "
                    "or get all information."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "connection_url": {
                            "type": "string",
                            "description": "Redis connection URL (e.g., redis://localhost:6379)",
                        },
                        "section": {
                            "type": "string",
                            "description": (
                                "Optional INFO section to query. Examples: 'server', 'memory', "
                                "'clients', 'stats', 'replication', 'cpu', 'keyspace'. "
                                "Leave empty for all sections."
                            ),
                        },
                    },
                    "required": ["connection_url"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("slowlog"),
                description=(
                    "Query Redis SLOWLOG to find slow queries. Use this to diagnose "
                    "performance issues by identifying commands that took longer than "
                    "the configured slowlog threshold to execute."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of slowlog entries to retrieve (default: 10)",
                            "default": 10,
                        }
                    },
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("acl_log"),
                description=(
                    "Query Redis ACL LOG to find authentication and authorization failures. "
                    "Use this to diagnose security issues, permission denials, and "
                    "authentication problems."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of ACL log entries to retrieve (default: 10)",
                            "default": 10,
                        }
                    },
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("config_get"),
                description=(
                    "Get Redis configuration values using CONFIG GET. Use this to inspect "
                    "Redis configuration settings. Supports pattern matching with wildcards."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": (
                                "Configuration parameter pattern. Examples: 'maxmemory*', "
                                "'timeout', 'save', '*'. Use '*' to get all config values."
                            ),
                        }
                    },
                    "required": ["pattern"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("client_list"),
                description=(
                    "List connected Redis clients using CLIENT LIST. Use this to diagnose "
                    "connection issues, identify problematic clients, or check client "
                    "connection details."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "client_type": {
                            "type": "string",
                            "description": (
                                "Optional client type filter. Values: 'normal', 'master', "
                                "'replica', 'pubsub'. Leave empty for all clients."
                            ),
                        }
                    },
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("memory_doctor"),
                description=(
                    "Run Redis MEMORY DOCTOR to get memory usage analysis and recommendations. "
                    "Use this to diagnose memory issues and get Redis's own advice on "
                    "memory optimization."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("latency_doctor"),
                description=(
                    "Run Redis LATENCY DOCTOR to get latency analysis and recommendations. "
                    "Use this to diagnose latency issues and get Redis's own advice on "
                    "latency optimization."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("cluster_info"),
                description=(
                    "Get Redis cluster information using CLUSTER INFO. Use this to check "
                    "cluster state, slots distribution, and cluster health. Only works "
                    "if Redis is running in cluster mode."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("replication_info"),
                description=(
                    "Get Redis replication information including role, connected replicas, "
                    "and replication lag. Use this to diagnose replication issues."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("memory_stats"),
                description=(
                    "Get detailed Redis memory statistics using MEMORY STATS. Use this "
                    "for in-depth memory analysis including allocator stats, fragmentation, "
                    "and memory breakdown by category."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Route tool call to appropriate method.

        Args:
            tool_name: Tool name (e.g., "redis_cli_a3f2b1_info")
            args: Tool arguments

        Returns:
            Tool execution result
        """
        # Extract operation from tool name
        operation = tool_name.split("_")[-1]

        if operation == "info":
            return await self.info(**args)
        elif operation == "slowlog":
            return await self.slowlog(**args)
        elif operation == "log" and "acl" in tool_name:
            return await self.acl_log(**args)
        elif operation == "get" and "config" in tool_name:
            return await self.config_get(**args)
        elif operation == "list" and "client" in tool_name:
            return await self.client_list(**args)
        elif operation == "doctor" and "memory" in tool_name:
            return await self.memory_doctor()
        elif operation == "doctor" and "latency" in tool_name:
            return await self.latency_doctor()
        elif operation == "info" and "cluster" in tool_name:
            return await self.cluster_info()
        elif operation == "info" and "replication" in tool_name:
            return await self.replication_info()
        elif operation == "stats" and "memory" in tool_name:
            return await self.memory_stats()
        else:
            raise ValueError(f"Unknown operation: {operation} (from tool: {tool_name})")

    async def info(self, section: Optional[str] = None) -> Dict[str, Any]:
        """Execute Redis INFO command.

        Args:
            section: Optional section to query (e.g., "memory", "stats")

        Returns:
            Parsed INFO output
        """
        logger.info(f"Executing INFO{' ' + section if section else ''}")
        try:
            if section:
                result = await self._client.info(section)
            else:
                result = await self._client.info()

            return {
                "status": "success",
                "section": section or "all",
                "data": result,
            }
        except Exception as e:
            logger.error(f"Failed to execute INFO: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def slowlog(self, count: int = 10) -> Dict[str, Any]:
        """Query Redis SLOWLOG.

        Args:
            count: Number of entries to retrieve

        Returns:
            Slowlog entries
        """
        logger.info(f"Querying SLOWLOG (count={count})")
        try:
            result = await self._client.slowlog_get(count)

            # Format slowlog entries
            entries = []
            for entry in result:
                entries.append(
                    {
                        "id": entry["id"],
                        "timestamp": entry["start_time"],
                        "duration_us": entry["duration"],
                        "command": " ".join(str(arg) for arg in entry["command"]),
                        "client_address": entry.get("client_address", "N/A"),
                        "client_name": entry.get("client_name", "N/A"),
                    }
                )

            return {
                "status": "success",
                "count": len(entries),
                "entries": entries,
            }
        except Exception as e:
            logger.error(f"Failed to query SLOWLOG: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def acl_log(self, count: int = 10) -> Dict[str, Any]:
        """Query Redis ACL LOG.

        Args:
            count: Number of entries to retrieve

        Returns:
            ACL log entries
        """
        logger.info(f"Querying ACL LOG (count={count})")
        try:
            result = await self._client.acl_log(count)

            # Format ACL log entries
            entries = []
            for entry in result:
                entries.append(
                    {
                        "count": entry.get("count", 0),
                        "reason": entry.get("reason", "unknown"),
                        "context": entry.get("context", "unknown"),
                        "object": entry.get("object", "N/A"),
                        "username": entry.get("username", "N/A"),
                        "age_seconds": entry.get("age-seconds", 0),
                        "client_info": entry.get("client-info", "N/A"),
                    }
                )

            return {
                "status": "success",
                "count": len(entries),
                "entries": entries,
            }
        except Exception as e:
            logger.error(f"Failed to query ACL LOG: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def config_get(self, pattern: str) -> Dict[str, Any]:
        """Get Redis configuration values.

        Args:
            pattern: Configuration parameter pattern

        Returns:
            Configuration key-value pairs
        """
        logger.info(f"Executing CONFIG GET {pattern}")
        try:
            result = await self._client.config_get(pattern)

            return {
                "status": "success",
                "pattern": pattern,
                "config": result,
                "count": len(result),
            }
        except Exception as e:
            logger.error(f"Failed to execute CONFIG GET: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def client_list(self, client_type: Optional[str] = None) -> Dict[str, Any]:
        """List connected Redis clients.

        Args:
            client_type: Optional client type filter

        Returns:
            List of connected clients
        """
        logger.info(f"Executing CLIENT LIST{' TYPE ' + client_type if client_type else ''}")
        try:
            if client_type:
                result = await self._client.client_list(_type=client_type)
            else:
                result = await self._client.client_list()

            return {
                "status": "success",
                "client_type": client_type or "all",
                "count": len(result),
                "clients": result,
            }
        except Exception as e:
            logger.error(f"Failed to execute CLIENT LIST: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def memory_doctor(self) -> Dict[str, Any]:
        """Execute MEMORY DOCTOR command.

        Returns:
            Memory analysis and recommendations
        """
        logger.info("Executing MEMORY DOCTOR")
        try:
            result = await self._client.memory_doctor()

            return {
                "status": "success",
                "analysis": result,
            }
        except Exception as e:
            logger.error(f"Failed to execute MEMORY DOCTOR: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def latency_doctor(self) -> Dict[str, Any]:
        """Execute LATENCY DOCTOR command.

        Returns:
            Latency analysis and recommendations
        """
        logger.info("Executing LATENCY DOCTOR")
        try:
            result = await self._client.execute_command("LATENCY", "DOCTOR")

            return {
                "status": "success",
                "analysis": result,
            }
        except Exception as e:
            logger.error(f"Failed to execute LATENCY DOCTOR: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def cluster_info(self) -> Dict[str, Any]:
        """Execute CLUSTER INFO command.

        Returns:
            Cluster state and information
        """
        logger.info("Executing CLUSTER INFO")
        try:
            result = await self._client.cluster("INFO")

            return {
                "status": "success",
                "cluster_info": result,
            }
        except Exception as e:
            logger.error(f"Failed to execute CLUSTER INFO: {e}")
            return {
                "status": "error",
                "error": str(e),
                "note": "This command only works in cluster mode",
            }

    async def replication_info(self) -> Dict[str, Any]:
        """Get replication information.

        Returns:
            Replication status, role, and lag
        """
        logger.info("Getting replication info")
        try:
            # Get INFO replication
            info = await self._client.info("replication")

            # Get ROLE command output
            role = await self._client.execute_command("ROLE")

            return {
                "status": "success",
                "info": info,
                "role": {
                    "type": role[0] if role else "unknown",
                    "details": role[1:] if len(role) > 1 else [],
                },
            }
        except Exception as e:
            logger.error(f"Failed to get replication info: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    async def memory_stats(self) -> Dict[str, Any]:
        """Execute MEMORY STATS command.

        Returns:
            Detailed memory statistics
        """
        logger.info("Executing MEMORY STATS")
        try:
            result = await self._client.memory_stats()

            return {
                "status": "success",
                "stats": result,
            }
        except Exception as e:
            logger.error(f"Failed to execute MEMORY STATS: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

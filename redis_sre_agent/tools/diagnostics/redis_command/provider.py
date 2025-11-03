"""Redis Command Diagnostics tool provider.

This provider executes Redis diagnostic commands directly via redis-py.
All commands are read-only for safety.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from opentelemetry import trace
from pydantic import BaseModel
from redis.asyncio import Redis

from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.tools.decorators import status_update
from redis_sre_agent.tools.protocols import SystemHost, ToolCapability, ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class RedisCliConfig(BaseModel):
    """Configuration for Redis Command Diagnostics provider.

    Note: This provider does not use configuration. All tools require
    a connection_url parameter to be passed at runtime.
    """

    pass


class RedisCommandToolProvider(ToolProvider):
    """Redis Command Diagnostics provider using redis-py.

    Provides read-only diagnostic tools for Redis troubleshooting:

    - INFO command (server, memory, clients, stats, etc.)
    - SLOWLOG (performance diagnostics)
    - ACL LOG (security diagnostics)
    - CONFIG GET (configuration inspection)
    - CLIENT LIST (connection diagnostics)
    - CLUSTER INFO (cluster diagnostics)
    - Replication info (replication diagnostics)
    - MEMORY STATS (detailed memory breakdown)
    - RANDOMKEY (keyspace sampling)
    - TYPE (key type inspection)
    - FT._LIST (list Search indexes)
    - FT.INFO (Search index information)

    Note: MEMORY DOCTOR and LATENCY DOCTOR are not included as they are not
    available in Redis Cloud and some Redis versions.

    The provider is initialized with a connection URL and manages the Redis client lifecycle.
    """

    # Declare capabilities so orchestrators can obtain a diagnostics provider via ToolManager
    capabilities = {ToolCapability.DIAGNOSTICS}

    def __init__(
        self,
        redis_instance: Optional[RedisInstance] = None,
        connection_url: Optional[str] = None,
        _config: Optional[RedisCliConfig] = None,
    ):
        """Initialize the Redis Command Diagnostics provider.

        Args:
            redis_instance: Optional Redis instance for scoped diagnostics.
                           If provided, uses its connection_url.
            connection_url: Redis connection URL (e.g., redis://localhost:6379).
                           Required if redis_instance is not provided.
            _config: Optional config (unused, kept for compatibility)
        """
        super().__init__(redis_instance)

        # Get connection URL from redis_instance or parameter
        if redis_instance:
            # Extract secret value if it's a SecretStr
            from pydantic import SecretStr

            conn_url = redis_instance.connection_url
            logger.debug(f"redis_instance.connection_url type: {type(conn_url)}")

            if isinstance(conn_url, SecretStr):
                self.connection_url = conn_url.get_secret_value()
                logger.debug(
                    f"Extracted from SecretStr, starts with: {self.connection_url[:10] if self.connection_url else 'EMPTY'}..."
                )
            elif isinstance(conn_url, str):
                self.connection_url = conn_url
                logger.debug(
                    f"Using plain string, starts with: {self.connection_url[:10] if self.connection_url else 'EMPTY'}..."
                )
            else:
                raise ValueError(f"connection_url has unexpected type: {type(conn_url)}")
        elif connection_url:
            self.connection_url = connection_url
            logger.debug(
                f"Using provided connection_url, starts with: {self.connection_url[:10] if self.connection_url else 'EMPTY'}..."
            )
        else:
            raise ValueError("Either redis_instance or connection_url must be provided")

        # Validate that we have a non-empty connection URL
        if not self.connection_url or not isinstance(self.connection_url, str):
            raise ValueError(
                f"Invalid connection_url: {self.connection_url!r} (type: {type(self.connection_url)})"
            )

        # Validate URL scheme
        if not self.connection_url.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError(
                f"Invalid Redis URL scheme: {self.connection_url!r}. "
                "Must start with redis://, rediss://, or unix://"
            )

        self._client: Optional[Redis] = None

    @property
    def provider_name(self) -> str:
        return "redis_command"

    def get_client(self) -> Redis:
        """Get or create the Redis client (lazy initialization).

        Returns:
            Redis: Initialized Redis client
        """
        if self._client is None:
            from redis_sre_agent.core.instances import mask_redis_url

            self._client = Redis.from_url(self.connection_url, decode_responses=True)
            logger.info(f"Connected to Redis at {mask_redis_url(self.connection_url)}")
        return self._client

    async def __aenter__(self):
        """Support async context manager (no-op, client is lazily initialized)."""
        return self

    async def __aexit__(self, *args):
        """Clean up Redis connection on context exit."""
        if self._client:
            await self._client.aclose()
        self._client = None

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Create tool schemas for Redis Command diagnostic operations."""
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
                        "section": {
                            "type": "string",
                            "description": (
                                "Optional INFO section to query. Examples: 'server', 'memory', "
                                "'clients', 'stats', 'replication', 'cpu', 'keyspace'. "
                                "Leave empty for all sections."
                            ),
                        },
                    },
                    "required": [],
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
            # NOTE: MEMORY DOCTOR and LATENCY DOCTOR are not available in Redis Cloud
            # and some Redis versions, so they have been removed
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
            ToolDefinition(
                name=self._make_tool_name("sample_keys"),
                description=(
                    "Sample random keys from the Redis keyspace with minimal impact using RANDOMKEY. "
                    "Returns a sample of unique keys with their types. Prefer this for lightweight "
                    "inspections of the data model and type distribution."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of keys to sample (default: 100; upper bound enforced)",
                            "default": 100,
                        }
                    },
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("search_indexes"),
                description=(
                    "List all Redis Search (RediSearch) indexes using FT._LIST. "
                    "Use this to discover what search indexes exist in the Redis instance."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("search_index_info"),
                description=(
                    "Get detailed information about a Redis Search index using FT.INFO. "
                    "Returns schema, statistics, and configuration for the specified index. "
                    "Use this to understand index structure, document count, and performance metrics."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "index_name": {
                            "type": "string",
                            "description": "Name of the search index to inspect",
                        }
                    },
                    "required": ["index_name"],
                },
            ),
        ]

    def get_status_update(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        """Return a concise natural-language status for this Redis CLI call."""
        operation = tool_name.split("_")[-1]
        if (
            operation == "info"
            and "index" not in tool_name
            and "cluster" not in tool_name
            and "replication" not in tool_name
        ):
            section = args.get("section")
            if section:
                return f"I'm running Redis INFO for the {section} section."
            return "I'm running Redis INFO to collect server metrics."
        if operation == "slowlog":
            return "I'm checking Redis SLOWLOG for slow queries."
        if operation == "client" and "list" in tool_name:
            return "I'm listing connected Redis clients."
        if operation == "get" and "config" in tool_name:
            pattern = args.get("pattern", "*")
            return f"I'm inspecting Redis configuration with CONFIG GET {pattern}."
        return None

    def resolve_operation(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        """Map tool_name to concrete method names for decorator/status usage."""
        op = tool_name.split("_")[-1]
        if op == "info":
            if "cluster" in tool_name:
                return "cluster_info"
            if "replication" in tool_name:
                return "replication_info"
            if "index" in tool_name:
                return "search_index_info"
            return "info"
        if op == "slowlog":
            return "slowlog"
        if op == "log" and "acl" in tool_name:
            return "acl_log"
        if op == "get" and "config" in tool_name:
            return "config_get"
        if op == "list" and "client" in tool_name:
            return "client_list"
        if op == "stats" and "memory" in tool_name:
            return "memory_stats"
        if op == "keys":
            return "sample_keys"
        if op == "indexes":
            return "search_indexes"
        return op

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Route tool call to appropriate method.

        Args:
            tool_name: Tool name (e.g., "redis_command_a3f2b1_info")
            args: Tool arguments

        Returns:
            Tool execution result
        """
        # Defensive: Remove connection_url if LLM passes it (provider already has it)
        args = {k: v for k, v in args.items() if k != "connection_url"}

        # Extract operation from tool name
        operation = tool_name.split("_")[-1]

        if operation == "info":
            # Disambiguate between different info commands
            if "cluster" in tool_name:
                return await self.cluster_info()
            elif "replication" in tool_name:
                return await self.replication_info()
            elif "index" in tool_name:
                return await self.search_index_info(**args)
            else:
                return await self.info(**args)
        elif operation == "slowlog":
            return await self.slowlog(**args)
        elif operation == "log" and "acl" in tool_name:
            return await self.acl_log(**args)
        elif operation == "get" and "config" in tool_name:
            return await self.config_get(**args)
        elif operation == "list" and "client" in tool_name:
            return await self.client_list(**args)
        elif operation == "stats" and "memory" in tool_name:
            return await self.memory_stats()
        elif operation == "keys":
            return await self.sample_keys(**args)
        elif operation == "indexes":
            return await self.search_indexes()
        else:
            raise ValueError(f"Unknown operation: {operation} (from tool: {tool_name})")

    @status_update("I'm running Redis INFO to collect server metrics ({section}).")
    async def info(self, section: Optional[str] = None) -> Dict[str, Any]:
        """Execute Redis INFO command.

        Args:
            section: Optional section to query (e.g., "memory", "stats")

        Returns:
            Parsed INFO output
        """
        logger.info(f"Executing INFO{' ' + section if section else ''}")
        try:
            client = self.get_client()
            if section:
                result = await client.info(section)
            else:
                result = await client.info()

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

    @status_update("I'm checking Redis SLOWLOG for slow queries.")
    async def slowlog(self, count: int = 10) -> Dict[str, Any]:
        """Query Redis SLOWLOG.

        Args:
            count: Number of entries to retrieve

        Returns:
            Slowlog entries
        """
        logger.info(f"Querying SLOWLOG (count={count})")
        try:
            client = self.get_client()
            result = await client.slowlog_get(count)

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

    @status_update("I'm checking Redis ACL LOG for auth and permission issues.")
    async def acl_log(self, count: int = 10) -> Dict[str, Any]:
        """Query Redis ACL LOG.

        Args:
            count: Number of entries to retrieve

        Returns:
            ACL log entries
        """
        logger.info(f"Querying ACL LOG (count={count})")
        try:
            client = self.get_client()
            result = await client.acl_log(count)

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

    @status_update("I'm inspecting Redis configuration with CONFIG GET {pattern}.")
    async def config_get(self, pattern: str) -> Dict[str, Any]:
        """Get Redis configuration values.

        Args:
            pattern: Configuration parameter pattern

        Returns:
            Configuration key-value pairs
        """
        logger.info(f"Executing CONFIG GET {pattern}")
        try:
            client = self.get_client()
            result = await client.config_get(pattern)

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

    @status_update("I'm listing connected Redis clients.")
    async def client_list(self, client_type: Optional[str] = None) -> Dict[str, Any]:
        """List connected Redis clients.

        Args:
            client_type: Optional client type filter

        Returns:
            List of connected clients
        """
        logger.info(f"Executing CLIENT LIST{' TYPE ' + client_type if client_type else ''}")
        try:
            client = self.get_client()
            if client_type:
                result = await client.client_list(_type=client_type)
            else:
                result = await client.client_list()

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

    @status_update("I'm checking Redis cluster info.")
    async def cluster_info(self) -> Dict[str, Any]:
        """Execute CLUSTER INFO command.

        Returns:
            Cluster state and information
        """
        logger.info("Executing CLUSTER INFO")
        try:
            client = self.get_client()
            result = await client.cluster("INFO")

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

    @status_update("I'm checking Redis replication info.")
    async def replication_info(self) -> Dict[str, Any]:
        """Get replication information.

        Returns:
            Replication status, role, and lag
        """
        logger.info("Getting replication info")
        try:
            client = self.get_client()

            # Get INFO replication
            info = await client.info("replication")

            # Get ROLE command output
            role = await client.execute_command("ROLE")

            return {
                "status": "success",
                "info": info,
                "role": {
                    "type": role[0] if role else "unknown",
                    "details": role[1:] if (role and len(role) > 1) else [],
                },
            }
        except Exception as e:
            logger.error(f"Failed to get replication info: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    @status_update("I'm collecting detailed Redis memory stats.")
    async def memory_stats(self) -> Dict[str, Any]:
        """Execute MEMORY STATS command.

        Returns:
            Detailed memory statistics
        """
        logger.info("Executing MEMORY STATS")
        try:
            client = self.get_client()
            result = await client.memory_stats()

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

    @status_update("I'm sampling random keys from the Redis keyspace (count: {count}).")
    async def sample_keys(self, count: int = 100) -> Dict[str, Any]:
        """Sample random keys from the Redis keyspace with minimal impact.

        Uses RANDOMKEY in pipelined batches and then TYPE for deduplicated keys.
        Enforces an upper bound on count and a time limit to preserve server performance.
        """
        logger.info(f"Sampling {count} random keys")
        try:
            client = self.get_client()

            async def _run_sample(span) -> Dict[str, Any]:
                max_count = 200  # hard cap to avoid excessive load
                time_limit_secs = 1.0  # wall-clock cap
                batch_attempts_max = 100  # max RANDOMKEY calls per batch
                attempt_factor = 3  # oversample factor to offset duplicates

                try:
                    requested = int(count)
                except Exception:
                    requested = 100
                target = max(0, min(requested, max_count))

                start = time.monotonic()
                sampled: Dict[str, str] = {}
                attempts = 0
                batches = 0
                max_attempts_total = max(50, target * 5)

                while len(sampled) < target and (time.monotonic() - start) < time_limit_secs:
                    remaining = target - len(sampled)
                    to_attempt = min(max(remaining * attempt_factor, 10), batch_attempts_max)
                    if attempts >= max_attempts_total:
                        break
                    to_attempt = min(to_attempt, max_attempts_total - attempts)

                    pipe = client.pipeline(transaction=False)
                    for _ in range(int(to_attempt)):
                        pipe.randomkey()
                    keys = await pipe.execute()

                    fresh: List[str] = []
                    seen_batch = set()
                    for k in keys:
                        if not k:
                            continue
                        if k in sampled or k in seen_batch:
                            continue
                        seen_batch.add(k)
                        fresh.append(k)

                    if fresh:
                        pipe2 = client.pipeline(transaction=False)
                        for k in fresh:
                            pipe2.type(k)
                        types = await pipe2.execute()
                        for k, t in zip(fresh, types):
                            if len(sampled) >= target:
                                break
                            sampled[k] = t

                    attempts += int(to_attempt)
                    batches += 1

                # Build outputs
                items = [{"key": k, "type": v} for k, v in list(sampled.items())[:target]]
                type_counts: Dict[str, int] = {}
                for it in items:
                    t = it["type"]
                    type_counts[t] = type_counts.get(t, 0) + 1

                # Annotate the span with summary info
                if span is not None:
                    span.set_attribute("redis.random.attempts", int(attempts))
                    span.set_attribute("redis.random.batches", int(batches))
                    span.set_attribute("redis.sample.keys_sampled", len(items))
                    span.set_attribute("redis.sample.requested_count", int(requested))
                    span.set_attribute("redis.sample.max_count_enforced", int(max_count))
                    span.set_attribute("redis.sample.time_limit_secs", float(time_limit_secs))

                limit_applied = (requested > max_count) or (
                    (time.monotonic() - start) >= time_limit_secs
                )
                return {
                    "status": "success",
                    "requested_count": requested,
                    "sampled_count": len(items),
                    "keys": items,
                    "type_distribution": type_counts,
                    "limit_applied": bool(limit_applied),
                }

            with tracer.start_as_current_span(
                "tool.redis_command.sample_keys",
                attributes={"requested_count": int(count)},
            ) as span:
                return await _run_sample(span)
        except Exception as e:
            logger.error(f"Failed to sample keys: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    @status_update("I'm listing search indexes.")
    async def search_indexes(self) -> Dict[str, Any]:
        """List all Redis Search indexes.

        Returns:
            List of search index names
        """
        logger.info("Listing Redis Search indexes")
        try:
            client = self.get_client()

            # Execute FT._LIST command
            result = await client.execute_command("FT._LIST")

            # Result is a list of index names
            if result is None:
                indexes = []
            else:
                indexes = [idx.decode() if isinstance(idx, bytes) else idx for idx in result]

            return {
                "status": "success",
                "count": len(indexes),
                "indexes": indexes,
            }
        except Exception as e:
            logger.error(f"Failed to list search indexes: {e}")
            return {
                "status": "error",
                "error": str(e),
                "note": "This command requires RediSearch module to be loaded",
            }

    @status_update("I'm getting search index info for {index_name}.")
    async def search_index_info(self, index_name: str) -> Dict[str, Any]:
        """Get information about a Redis Search index.

        Args:
            index_name: Name of the search index

        Returns:
            Index schema, statistics, and configuration
        """
        logger.info(f"Getting info for search index: {index_name}")
        try:
            client = self.get_client()

            # Execute FT.INFO command
            result = await client.execute_command("FT.INFO", index_name)

            # Parse the result (it's a flat list of key-value pairs)
            info = {}
            if result is not None:
                i = 0
                while i < len(result):
                    key = result[i].decode() if isinstance(result[i], bytes) else result[i]
                    value = result[i + 1]

                    # Decode bytes values
                    if isinstance(value, bytes):
                        value = value.decode()
                    elif isinstance(value, list):
                        value = [v.decode() if isinstance(v, bytes) else v for v in value]

                    info[key] = value
                    i += 2

            return {
                "status": "success",
                "index_name": index_name,
                "info": info,
            }
        except Exception as e:
            logger.error(f"Failed to get search index info: {e}")
            return {
                "status": "error",
                "error": str(e),
                "index_name": index_name,
                "note": "This command requires RediSearch module and a valid index name",
            }

    async def system_hosts(self) -> List[SystemHost]:
        """Discover system hosts for this Redis deployment.

        Returns a list of SystemHost entries derived from Redis diagnostics:
        - Redis Cluster: parsed from CLUSTER NODES
        - Replication: parsed from INFO replication (master/replica hosts)
        - Single instance: inferred from our connection's local address (CLIENT LIST + CLIENT ID)
        """
        hosts: dict[Tuple[str, Optional[int]], SystemHost] = {}
        client = self.get_client()

        # Helper to add or update a host entry
        def add_host(
            host: str,
            port: Optional[int] = None,
            role: Optional[str] = None,
            labels: Optional[Dict[str, str]] = None,
        ):
            if not host:
                return
            key = (host, port)
            if key not in hosts:
                hosts[key] = SystemHost(host=host, port=port, role=role, labels=labels or {})
            else:
                # Preserve first non-empty role and merge labels
                if role and not hosts[key].role:
                    hosts[key].role = role
                if labels:
                    hosts[key].labels.update(labels)

        # 1) Try Redis Cluster discovery
        try:
            nodes_raw = await client.cluster("NODES")
            if isinstance(nodes_raw, (bytes, bytearray)):
                nodes_raw = nodes_raw.decode()
            if isinstance(nodes_raw, str) and nodes_raw.strip():
                for line in nodes_raw.splitlines():
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    addr = parts[1]  # e.g., 10.0.0.1:6379@16379
                    flags = parts[2]  # contains master, slave, replica, etc.
                    # Extract host and port (handle IPv6 [::1]:6379@16379)
                    hp = addr.split("@")[0]
                    if hp.startswith("[") and "]" in hp:
                        host = hp[1 : hp.rfind("]")]
                        port_str = hp[hp.rfind("]") + 2 :]
                    else:
                        host_port = hp.rsplit(":", 1)
                        if len(host_port) == 2:
                            host, port_str = host_port[0], host_port[1]
                        else:
                            host, port_str = hp, None
                    try:
                        port = int(port_str) if port_str else None
                    except Exception:
                        port = None

                    role = None
                    f = flags.lower()
                    if "master" in f:
                        role = "cluster-master"
                    elif "replica" in f or "slave" in f:
                        role = "cluster-replica"
                    add_host(host, port, role, labels={"source": "cluster"})
        except Exception:
            # Not a cluster or command not available
            pass

        # If we already discovered cluster nodes, return them
        if hosts:
            return list(hosts.values())

        # 2) Try replication topology
        try:
            repl = await client.info("replication")
            if isinstance(repl, dict):
                # Master (if this node is replica)
                mhost = repl.get("master_host") or repl.get("master_host_ip")
                mport = None
                try:
                    mport = int(repl.get("master_port")) if repl.get("master_port") else None
                except Exception:
                    mport = None
                if mhost:
                    add_host(str(mhost), mport, role="master", labels={"source": "replication"})

                # Replicas
                for k, v in repl.items():
                    if not isinstance(k, str) or not k.startswith("slave"):
                        continue
                    ip = None
                    port = None
                    if isinstance(v, dict):
                        ip = v.get("ip") or v.get("host")
                        try:
                            port = int(v.get("port")) if v.get("port") else None
                        except Exception:
                            port = None
                    elif isinstance(v, str):
                        # format: "ip=10.0.0.2,port=6380,state=online,..."
                        try:
                            m_ip = re.search(r"ip=([^,\s]+)", v)
                            m_po = re.search(r"port=(\d+)", v)
                            ip = m_ip.group(1) if m_ip else None
                            port = int(m_po.group(1)) if m_po else None
                        except Exception:
                            ip, port = None, None
                    if ip:
                        add_host(str(ip), port, role="replica", labels={"source": "replication"})
        except Exception:
            pass

        # 3) Fallback for single instance: use our connection's local address (laddr)
        # Only if nothing else found
        if not hosts:
            try:
                cid = await client.client_id()
                clist = await client.client_list()
                # Find this connection in client list
                entry = None
                for row in clist or []:
                    try:
                        if int(row.get("id")) == int(cid):
                            entry = row
                            break
                    except Exception:
                        continue
                if entry:
                    laddr = entry.get("laddr")  # e.g., "127.0.0.1:6379"
                    if isinstance(laddr, str) and ":" in laddr:
                        h, p = laddr.rsplit(":", 1)
                        try:
                            add_host(h, int(p), role="single", labels={"source": "client_list"})
                        except Exception:
                            add_host(h, None, role="single", labels={"source": "client_list"})
            except Exception:
                pass

        # 4) Final fallback: use connection_url hostname/port
        if not hosts:
            try:
                url = getattr(self, "connection_url", None)
                if url:
                    p = urlparse(url)
                    if p.hostname:
                        port_val = None
                        try:
                            port_val = int(p.port) if p.port else None
                        except Exception:
                            port_val = None
                        add_host(
                            p.hostname, port_val, role="single", labels={"source": "connection_url"}
                        )
            except Exception:
                pass

        return list(hosts.values())

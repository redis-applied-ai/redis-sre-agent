"""Redis direct diagnostics provider type.

This provider type connects directly to Redis instances via Redis protocol
and gathers deep diagnostic information including memory analysis, slow queries,
client connections, configuration, and more.
"""

import logging
from typing import Any, Dict, List

from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.models.provider_config import RedisDirectDiagnosticsConfig

from ..protocols import ToolCapability
from ..redis_diagnostics import capture_redis_diagnostics
from ..tool_definition import ToolDefinition
from .base import ProviderType

logger = logging.getLogger(__name__)


class RedisDirectDiagnosticsProviderType(ProviderType):
    """Provider type for direct Redis diagnostics connections.

    This provider creates tools that connect directly to Redis instances
    via Redis protocol and gather comprehensive diagnostic information.
    """

    def __init__(self, config: RedisDirectDiagnosticsConfig):
        """Initialize the provider type.

        Args:
            config: Configuration for Redis direct diagnostics
        """
        self.config = config

    @property
    def provider_type_name(self) -> str:
        return "redis_diagnostics"

    def get_capabilities(self) -> List[ToolCapability]:
        return [ToolCapability.DIAGNOSTICS]

    def create_tools_scoped_to_instance(self, instance: RedisInstance) -> List[ToolDefinition]:
        """Create diagnostics tools for a specific Redis instance.

        Creates four tools:
        1. capture_diagnostics - Capture comprehensive diagnostics
        2. capture_specific_sections - Capture specific diagnostic sections
        3. sample_keys - Sample keys from the instance
        4. analyze_keys - Analyze key types, TTLs, and memory usage

        Args:
            instance: The Redis instance to create tools for

        Returns:
            List of tool definitions
        """
        tools = []

        # Tool 1: Capture comprehensive diagnostics
        tools.append(self._create_capture_diagnostics_tool(instance))

        # Tool 2: Capture specific sections
        tools.append(self._create_capture_sections_tool(instance))

        # Tool 3: Sample keys
        tools.append(self._create_sample_keys_tool(instance))

        # Tool 4: Analyze keys
        tools.append(self._create_analyze_keys_tool(instance))

        return tools

    def _create_capture_diagnostics_tool(self, instance: RedisInstance) -> ToolDefinition:
        """Create the capture_diagnostics tool for an instance."""
        tool_name = self._create_tool_name(instance, "capture_diagnostics")
        description_prefix = self._create_tool_description_prefix(instance)

        async def capture_diagnostics_func() -> Dict[str, Any]:
            """Capture comprehensive diagnostics from this Redis instance."""
            try:
                result = await capture_redis_diagnostics(
                    redis_url=instance.connection_url,
                    sections=None,  # All sections
                    include_raw_data=True,
                )
                return result
            except Exception as e:
                logger.error(f"Error capturing diagnostics for {instance.name}: {e}")
                return {
                    "capture_status": "failed",
                    "error": str(e),
                    "instance": instance.name,
                }

        return ToolDefinition(
            name=tool_name,
            description=(
                f"{description_prefix}"
                f"Capture COMPREHENSIVE diagnostics from this Redis instance. "
                f"This includes ALL diagnostic sections: memory, performance, clients, "
                f"slowlog, configuration, keyspace, replication, persistence, and CPU. "
                f"Use this when you need a complete picture of the instance health. "
                f"For targeted investigation, use the capture_specific_sections tool instead. "
                f"This connects directly to Redis via INFO commands and other diagnostics."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            function=capture_diagnostics_func,
        )

    def _create_capture_sections_tool(self, instance: RedisInstance) -> ToolDefinition:
        """Create the capture_specific_sections tool for an instance."""
        tool_name = self._create_tool_name(instance, "capture_sections")
        description_prefix = self._create_tool_description_prefix(instance)

        async def capture_sections_func(sections: List[str]) -> Dict[str, Any]:
            """Capture specific diagnostic sections from this Redis instance."""
            try:
                result = await capture_redis_diagnostics(
                    redis_url=instance.connection_url,
                    sections=sections,
                    include_raw_data=True,
                )
                return result
            except Exception as e:
                logger.error(f"Error capturing sections for {instance.name}: {e}")
                return {
                    "capture_status": "failed",
                    "error": str(e),
                    "instance": instance.name,
                    "requested_sections": sections,
                }

        return ToolDefinition(
            name=tool_name,
            description=(
                f"{description_prefix}"
                f"Capture SPECIFIC diagnostic sections from this Redis instance. "
                f"Use this for targeted investigation when you know what you're looking for. "
                f"Available sections: "
                f"'memory' (memory usage, fragmentation), "
                f"'performance' (hit rates, ops/sec, command stats), "
                f"'clients' (connection analysis, client patterns), "
                f"'slowlog' (slow query log), "
                f"'configuration' (Redis config), "
                f"'keyspace' (database and key statistics), "
                f"'replication' (master/slave status), "
                f"'persistence' (RDB/AOF status), "
                f"'cpu' (CPU usage). "
                f"Example: sections=['memory', 'performance'] for memory and performance only."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of diagnostic sections to capture. "
                            "Options: memory, performance, clients, slowlog, configuration, "
                            "keyspace, replication, persistence, cpu. "
                            "Example: ['memory', 'clients']"
                        ),
                    }
                },
                "required": ["sections"],
            },
            function=capture_sections_func,
        )

    def _create_sample_keys_tool(self, instance: RedisInstance) -> ToolDefinition:
        """Create the sample_keys tool for an instance."""
        tool_name = self._create_tool_name(instance, "sample_keys")
        description_prefix = self._create_tool_description_prefix(instance)

        async def sample_keys_func(
            pattern: str = "*",
            count: int = 100,
            database: int = 0,
        ) -> Dict[str, Any]:
            """Sample keys from this Redis instance using SCAN."""
            try:
                import redis.asyncio as redis

                # Connect to Redis
                client = redis.from_url(
                    instance.connection_url,
                    decode_responses=True,
                    socket_timeout=10,
                    socket_connect_timeout=5,
                )

                try:
                    # Select database if not 0
                    if database != 0:
                        await client.select(database)

                    # Sample keys using SCAN
                    sampled_keys = []
                    cursor = 0
                    scan_count = min(count, 1000)

                    while len(sampled_keys) < count:
                        cursor, keys = await client.scan(cursor, match=pattern, count=scan_count)
                        sampled_keys.extend(keys)

                        if cursor == 0:
                            break

                    # Limit to requested count
                    sampled_keys = sampled_keys[:count]

                    # Analyze key patterns
                    key_patterns = {}
                    for key in sampled_keys:
                        if ":" in key:
                            prefix = key.split(":")[0]
                            key_patterns[prefix] = key_patterns.get(prefix, 0) + 1
                        else:
                            key_patterns["<no_prefix>"] = key_patterns.get("<no_prefix>", 0) + 1

                    # Get total key count
                    info = await client.info("keyspace")
                    db_key = f"db{database}"
                    total_keys = 0
                    if db_key in info:
                        db_info = info[db_key]
                        if isinstance(db_info, dict):
                            total_keys = db_info.get("keys", 0)

                    return {
                        "success": True,
                        "instance": instance.name,
                        "database": database,
                        "pattern": pattern,
                        "total_keys_in_db": total_keys,
                        "sampled_count": len(sampled_keys),
                        "sampled_keys": sampled_keys,
                        "key_patterns": key_patterns,
                        "pattern_summary": [
                            {"prefix": prefix, "count": cnt}
                            for prefix, cnt in sorted(
                                key_patterns.items(), key=lambda x: x[1], reverse=True
                            )
                        ],
                    }

                finally:
                    await client.aclose()

            except Exception as e:
                logger.error(f"Error sampling keys for {instance.name}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "instance": instance.name,
                }

        return ToolDefinition(
            name=tool_name,
            description=(
                f"{description_prefix}"
                f"Sample keys from this Redis instance using SCAN command. "
                f"Use this to understand what types of keys exist, identify key patterns, "
                f"or investigate specific key namespaces. "
                f"IMPORTANT: Use this instead of asking the user to check keys - you can do it yourself! "
                f"The SCAN command is safe and won't block the instance. "
                f"Returns sampled keys, key patterns, and statistics."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Key pattern to match (default: '*' for all keys). "
                            "Examples: 'user:*', 'session:*', 'cache:*'"
                        ),
                    },
                    "count": {
                        "type": "integer",
                        "description": "Maximum number of keys to sample (default: 100)",
                    },
                    "database": {
                        "type": "integer",
                        "description": "Database number to select (default: 0)",
                    },
                },
                "required": [],
            },
            function=sample_keys_func,
        )

    def _create_analyze_keys_tool(self, instance: RedisInstance) -> ToolDefinition:
        """Create the analyze_keys tool for an instance."""
        tool_name = self._create_tool_name(instance, "analyze_keys")
        description_prefix = self._create_tool_description_prefix(instance)

        async def analyze_keys_func(
            pattern: str = "*",
            sample_size: int = 100,
            database: int = 0,
        ) -> Dict[str, Any]:
            """Analyze keys in detail: types, TTLs, memory usage."""
            try:
                import redis.asyncio as redis

                # Connect to Redis
                client = redis.from_url(
                    instance.connection_url,
                    decode_responses=True,
                    socket_timeout=10,
                    socket_connect_timeout=5,
                )

                try:
                    # Select database if not 0
                    if database != 0:
                        await client.select(database)

                    # Get keyspace info first
                    info = await client.info("keyspace")
                    db_key = f"db{database}"
                    total_keys = 0
                    keys_with_ttl = 0
                    avg_ttl = 0

                    if db_key in info:
                        db_info = info[db_key]
                        if isinstance(db_info, dict):
                            total_keys = db_info.get("keys", 0)
                            keys_with_ttl = db_info.get("expires", 0)
                            avg_ttl = db_info.get("avg_ttl", 0)
                        else:
                            # Parse string format
                            for stat in db_info.split(","):
                                key, value = stat.split("=")
                                if key == "keys":
                                    total_keys = int(value)
                                elif key == "expires":
                                    keys_with_ttl = int(value)
                                elif key == "avg_ttl":
                                    avg_ttl = int(value)

                    # Sample keys using SCAN
                    sampled_keys = []
                    cursor = 0
                    scan_count = min(sample_size, 1000)

                    while len(sampled_keys) < sample_size:
                        cursor, keys = await client.scan(cursor, match=pattern, count=scan_count)
                        sampled_keys.extend(keys)

                        if cursor == 0:
                            break

                    # Limit to requested sample size
                    sampled_keys = sampled_keys[:sample_size]

                    # Analyze sampled keys
                    type_distribution = {}
                    ttl_distribution = {
                        "no_expiry": 0,
                        "0_to_1h": 0,
                        "1h_to_1d": 0,
                        "1d_to_7d": 0,
                        "7d_plus": 0,
                    }
                    memory_by_type = {}
                    total_memory = 0

                    key_details = []

                    for key in sampled_keys:
                        try:
                            # Get key type
                            key_type = await client.type(key)
                            type_distribution[key_type] = type_distribution.get(key_type, 0) + 1

                            # Get TTL
                            ttl = await client.ttl(key)
                            if ttl == -1:
                                ttl_distribution["no_expiry"] += 1
                                ttl_seconds = None
                            elif ttl == -2:
                                # Key doesn't exist (race condition)
                                continue
                            else:
                                ttl_seconds = ttl
                                if ttl < 3600:
                                    ttl_distribution["0_to_1h"] += 1
                                elif ttl < 86400:
                                    ttl_distribution["1h_to_1d"] += 1
                                elif ttl < 604800:
                                    ttl_distribution["1d_to_7d"] += 1
                                else:
                                    ttl_distribution["7d_plus"] += 1

                            # Get memory usage (if MEMORY USAGE command is available)
                            try:
                                memory_bytes = await client.memory_usage(key)
                                if memory_bytes:
                                    total_memory += memory_bytes
                                    memory_by_type[key_type] = (
                                        memory_by_type.get(key_type, 0) + memory_bytes
                                    )
                            except Exception:
                                memory_bytes = None

                            # Store key details (limit to first 20 for brevity)
                            if len(key_details) < 20:
                                key_details.append(
                                    {
                                        "key": key,
                                        "type": key_type,
                                        "ttl_seconds": ttl_seconds,
                                        "memory_bytes": memory_bytes,
                                    }
                                )

                        except Exception as e:
                            logger.debug(f"Error analyzing key {key}: {e}")
                            continue

                    # Calculate percentages
                    keys_without_ttl = total_keys - keys_with_ttl if total_keys > 0 else 0
                    ttl_percentage = (keys_with_ttl / total_keys * 100) if total_keys > 0 else 0

                    return {
                        "success": True,
                        "instance": instance.name,
                        "database": database,
                        "pattern": pattern,
                        "keyspace_summary": {
                            "total_keys": total_keys,
                            "keys_with_ttl": keys_with_ttl,
                            "keys_without_ttl": keys_without_ttl,
                            "ttl_percentage": round(ttl_percentage, 2),
                            "avg_ttl_seconds": avg_ttl,
                            "avg_ttl_human": self._format_ttl(avg_ttl) if avg_ttl > 0 else "N/A",
                        },
                        "sample_analysis": {
                            "sampled_count": len(sampled_keys),
                            "type_distribution": type_distribution,
                            "ttl_distribution": ttl_distribution,
                            "memory_by_type_bytes": memory_by_type,
                            "total_memory_bytes": total_memory,
                            "avg_memory_per_key_bytes": (
                                round(total_memory / len(sampled_keys))
                                if len(sampled_keys) > 0 and total_memory > 0
                                else None
                            ),
                        },
                        "key_details": key_details,
                    }

                finally:
                    await client.aclose()

            except Exception as e:
                logger.error(f"Error analyzing keys for {instance.name}: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "instance": instance.name,
                }

        return ToolDefinition(
            name=tool_name,
            description=(
                f"{description_prefix}"
                f"Analyze keys in detail from this Redis instance. "
                f"This tool provides comprehensive key analysis including: "
                f"1) Key type distribution (STRING, HASH, LIST, SET, ZSET, STREAM), "
                f"2) TTL distribution (no expiry, 0-1h, 1h-1d, 1d-7d, 7d+), "
                f"3) Memory usage per key type, "
                f"4) Average memory per key, "
                f"5) Detailed information about sampled keys. "
                f"Use this to understand key characteristics, identify keys without TTLs, "
                f"find memory-heavy key types, or investigate expiration patterns. "
                f"IMPORTANT: This is more detailed than sample_keys - use this when you need "
                f"to understand key properties, not just key names."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Key pattern to match (default: '*' for all keys). "
                            "Examples: 'user:*', 'session:*', 'cache:*'"
                        ),
                    },
                    "sample_size": {
                        "type": "integer",
                        "description": "Number of keys to sample for analysis (default: 100)",
                    },
                    "database": {
                        "type": "integer",
                        "description": "Database number to select (default: 0)",
                    },
                },
                "required": [],
            },
            function=analyze_keys_func,
        )

    def _format_ttl(self, seconds: int) -> str:
        """Format TTL in human-readable format."""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m"
        elif seconds < 86400:
            return f"{seconds // 3600}h"
        else:
            return f"{seconds // 86400}d"

    async def health_check(self) -> Dict[str, Any]:
        """Check if this provider type is healthy.

        For Redis direct diagnostics, we just check that the config is valid.
        Actual connectivity is checked per-instance.
        """
        return {
            "provider_type": self.provider_type_name,
            "status": "healthy",
            "config": {
                "connection_timeout": self.config.connection_timeout,
                "socket_timeout": self.config.socket_timeout,
            },
        }

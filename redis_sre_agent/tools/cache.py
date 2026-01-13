"""Tool output caching with Redis backend.

This module provides a shared cache for tool call outputs that persists
across agent runs and threads. It uses Redis with TTL-based expiration.
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Default TTLs by tool operation (in seconds)
# These can be overridden via configuration
DEFAULT_TOOL_TTLS: Dict[str, int] = {
    # Redis diagnostic tools - relatively stable data
    "info": 60,  # INFO command output
    "memory_stats": 60,  # MEMORY STATS
    "config_get": 300,  # CONFIG rarely changes
    "slowlog": 60,  # Slowlog entries (append-only, cache recent)
    "client_list": 30,  # Client connections change more frequently
    "cluster_info": 60,  # Cluster state
    "cluster_nodes": 60,  # Cluster topology
    "dbsize": 30,  # Key count
    "latency": 30,  # Latency samples
    "commandstats": 60,  # Command statistics
    # Knowledge base - content changes on ingestion only
    "knowledge_search": 300,
    "knowledge_get": 300,
    # Prometheus metrics - moderate refresh rate
    "prometheus_query": 30,
    "prometheus_query_range": 60,
}

# Cache key prefix
CACHE_PREFIX = "sre_cache:tool"

# Default TTL for tools not in the mapping
DEFAULT_TTL = 60


class ToolCache:
    """Redis-backed cache for tool call outputs.

    Provides cross-thread and cross-run caching of tool results with
    configurable TTLs per tool type.

    Example:
        cache = ToolCache(redis_client=client, instance_id="redis-prod-1")

        # Check cache
        result = await cache.get("redis_cli_info", {"section": "memory"})
        if result is None:
            result = await execute_tool(...)
            await cache.set("redis_cli_info", {"section": "memory"}, result)
    """

    def __init__(
        self,
        redis_client: Redis,
        instance_id: str,
        ttl_overrides: Optional[Dict[str, int]] = None,
        enabled: bool = True,
    ):
        """Initialize the tool cache.

        Args:
            redis_client: Async Redis client for cache storage
            instance_id: Redis instance ID to scope cache keys
            ttl_overrides: Custom TTLs for specific tools
            enabled: Whether caching is enabled
        """
        self._redis = redis_client
        self._instance_id = instance_id
        self._ttl_overrides = ttl_overrides or {}
        self._enabled = enabled

    def _normalize_tool_name(self, tool_name: str) -> str:
        """Normalize tool name by removing the instance hash.

        Tool names follow format: {provider}_{instance_hash}_{operation}
        e.g., redis_command_104c81_info -> redis_command_info

        This ensures cache keys are stable across runs even when
        provider instances have different memory addresses.
        """
        import re

        # Match pattern: underscore + 6 hex chars + underscore
        # Replace with just underscore to preserve provider_operation format
        return re.sub(r"_([0-9a-f]{6})_", "_", tool_name)

    def build_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Build cache key from tool name and arguments.

        Key format: sre_cache:tool:{instance_id}:{normalized_tool_name}:{args_hash}

        Tool names are normalized to remove instance hashes, ensuring
        cache keys are stable across runs.
        """
        # Normalize tool name to remove instance hash
        normalized_name = self._normalize_tool_name(tool_name)

        # Create stable hash of arguments
        args_json = json.dumps(args, sort_keys=True, default=str)
        args_hash = hashlib.sha256(args_json.encode()).hexdigest()[:16]

        return f"{CACHE_PREFIX}:{self._instance_id}:{normalized_name}:{args_hash}"

    def _get_ttl(self, tool_name: str) -> int:
        """Get TTL for a tool, checking overrides then defaults."""
        # Check overrides first
        for key, ttl in self._ttl_overrides.items():
            if key in tool_name.lower():
                return ttl

        # Check defaults
        for key, ttl in DEFAULT_TOOL_TTLS.items():
            if key in tool_name.lower():
                return ttl

        return DEFAULT_TTL

    def _should_cache(self, result: Any) -> bool:
        """Determine if a result should be cached.

        Don't cache error responses.
        """
        if isinstance(result, dict):
            status = result.get("status", "").lower()
            if status in ("error", "failed", "failure"):
                return False
        return True

    async def get(self, tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
        """Get cached tool result if available.

        Returns None on cache miss or if caching is disabled.
        """
        if not self._enabled:
            return None

        try:
            key = self.build_key(tool_name, args)
            data = await self._redis.get(key)
            if data:
                logger.debug(f"Cache HIT for {tool_name}")
                return json.loads(data)
            logger.debug(f"Cache MISS for {tool_name}")
            return None
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None

    async def set(self, tool_name: str, args: Dict[str, Any], result: Any) -> bool:
        """Cache a tool result with appropriate TTL.

        Returns True if cached successfully, False otherwise.
        Does not cache error responses.
        """
        if not self._enabled:
            return False

        if not self._should_cache(result):
            logger.debug(f"Not caching error result for {tool_name}")
            return False

        try:
            key = self.build_key(tool_name, args)
            ttl = self._get_ttl(tool_name)
            data = json.dumps(result, default=str)
            await self._redis.setex(key, ttl, data)
            logger.debug(f"Cached {tool_name} with TTL {ttl}s")
            return True
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")
            return False

    async def clear(self) -> int:
        """Clear all cached entries for this instance.

        Returns the number of keys deleted.
        """
        try:
            pattern = f"{CACHE_PREFIX}:{self._instance_id}:*"
            keys = await self._redis.keys(pattern)
            if keys:
                deleted = await self._redis.delete(*keys)
                logger.info(f"Cleared {deleted} cache keys for {self._instance_id}")
                return deleted
            return 0
        except Exception as e:
            logger.warning(f"Cache clear failed: {e}")
            return 0

    async def clear_all(self) -> int:
        """Clear all cached entries across all instances.

        Returns the number of keys deleted.
        """
        try:
            pattern = f"{CACHE_PREFIX}:*"
            keys = await self._redis.keys(pattern)
            if keys:
                deleted = await self._redis.delete(*keys)
                logger.info(f"Cleared {deleted} total cache keys")
                return deleted
            return 0
        except Exception as e:
            logger.warning(f"Cache clear_all failed: {e}")
            return 0

    async def stats(self) -> Dict[str, Any]:
        """Get cache statistics for this instance.

        Returns dict with cached_keys, instance_id, enabled.
        """
        try:
            pattern = f"{CACHE_PREFIX}:{self._instance_id}:*"
            keys = await self._redis.keys(pattern)
            return {
                "instance_id": self._instance_id,
                "cached_keys": len(keys),
                "enabled": self._enabled,
            }
        except Exception as e:
            logger.warning(f"Cache stats failed: {e}")
            return {
                "instance_id": self._instance_id,
                "cached_keys": 0,
                "enabled": self._enabled,
                "error": str(e),
            }

    async def stats_all(self) -> Dict[str, Any]:
        """Get cache statistics across all instances.

        Returns dict with total_keys and list of instances.
        """
        try:
            pattern = f"{CACHE_PREFIX}:*"
            keys = await self._redis.keys(pattern)

            # Extract unique instance IDs from keys
            instances = set()
            for key in keys:
                parts = key.decode() if isinstance(key, bytes) else key
                # Format: sre_cache:tool:{instance_id}:{tool_name}:{hash}
                key_parts = parts.split(":")
                if len(key_parts) >= 3:
                    instances.add(key_parts[2])

            return {
                "total_keys": len(keys),
                "instances": list(instances),
            }
        except Exception as e:
            logger.warning(f"Cache stats_all failed: {e}")
            return {
                "total_keys": 0,
                "instances": [],
                "error": str(e),
            }

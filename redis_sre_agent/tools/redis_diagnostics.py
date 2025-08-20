"""Direct Redis diagnostic tools for SRE operations."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from ..core.config import settings

logger = logging.getLogger(__name__)


class RedisDiagnostics:
    """Direct Redis diagnostic and management tool for SRE operations."""

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize Redis diagnostics with connection details."""
        self.redis_url = redis_url or settings.redis_url
        self._client: Optional[redis.Redis] = None

    async def get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(
                self.redis_url, decode_responses=True, socket_timeout=10, socket_connect_timeout=5
            )
        return self._client

    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def run_diagnostic_suite(self) -> Dict[str, Any]:
        """Run comprehensive Redis diagnostic suite."""
        logger.info("Starting Redis diagnostic suite")

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "redis_url": self.redis_url,
            "diagnostics": {},
            "overall_status": "unknown",
            "critical_issues": [],
            "warnings": [],
            "recommendations": [],
        }

        try:
            client = await self.get_client()

            # Core diagnostics
            results["diagnostics"]["connection"] = await self._test_connection(client)
            results["diagnostics"]["info"] = await self._get_redis_info(client)
            results["diagnostics"]["memory"] = await self._analyze_memory_usage(client)
            results["diagnostics"]["performance"] = await self._check_performance_metrics(client)
            results["diagnostics"]["configuration"] = await self._check_configuration(client)
            results["diagnostics"]["keyspace"] = await self._analyze_keyspace(client)
            results["diagnostics"]["slowlog"] = await self._check_slowlog(client)
            results["diagnostics"]["clients"] = await self._analyze_client_connections(client)

            # Determine overall status
            results["overall_status"] = self._determine_overall_status(results["diagnostics"])
            results["critical_issues"] = self._identify_critical_issues(results["diagnostics"])
            results["warnings"] = self._identify_warnings(results["diagnostics"])
            results["recommendations"] = self._generate_recommendations(results["diagnostics"])

            logger.info(f"Redis diagnostics completed: {results['overall_status']}")

        except Exception as e:
            logger.error(f"Redis diagnostics failed: {e}")
            results["diagnostics"]["error"] = str(e)
            results["overall_status"] = "error"
            results["critical_issues"].append(f"Diagnostic failure: {str(e)}")

        return results

    async def _test_connection(self, client: redis.Redis) -> Dict[str, Any]:
        """Test Redis connection and basic operations."""
        try:
            # Test ping
            ping_start = datetime.now()
            pong = await client.ping()
            ping_duration = (datetime.now() - ping_start).total_seconds() * 1000

            # Test basic operations
            test_key = f"sre_diagnostic_test_{int(datetime.now().timestamp())}"
            await client.set(test_key, "test_value", ex=10)
            test_value = await client.get(test_key)
            await client.delete(test_key)

            return {
                "status": "healthy",
                "ping_response": pong,
                "ping_duration_ms": round(ping_duration, 2),
                "basic_operations": "working" if test_value == "test_value" else "failed",
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "ping_duration_ms": None,
                "basic_operations": "failed",
            }

    async def _get_redis_info(self, client: redis.Redis) -> Dict[str, Any]:
        """Get comprehensive Redis server information."""
        try:
            info = await client.info("all")

            # Extract key metrics
            return {
                "version": info.get("redis_version"),
                "mode": info.get("redis_mode"),
                "uptime_seconds": info.get("uptime_in_seconds"),
                "connected_clients": info.get("connected_clients"),
                "used_memory": info.get("used_memory"),
                "used_memory_human": info.get("used_memory_human"),
                "used_memory_rss": info.get("used_memory_rss"),
                "maxmemory": info.get("maxmemory"),
                "maxmemory_human": info.get("maxmemory_human"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
                "total_commands_processed": info.get("total_commands_processed"),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec"),
                "role": info.get("role"),
                "raw_info": info,
            }

        except Exception as e:
            return {"error": str(e)}

    async def _analyze_memory_usage(self, client: redis.Redis) -> Dict[str, Any]:
        """Analyze Redis memory usage patterns."""
        try:
            info = await client.info("memory")

            used_memory = info.get("used_memory", 0)
            maxmemory = info.get("maxmemory", 0)

            # Calculate memory usage percentage
            memory_usage_pct = 0
            if maxmemory > 0:
                memory_usage_pct = (used_memory / maxmemory) * 100

            # Get memory breakdown
            memory_breakdown = {}
            for key, value in info.items():
                if key.startswith("used_memory_"):
                    memory_breakdown[key] = value

            return {
                "used_memory_bytes": used_memory,
                "used_memory_human": info.get("used_memory_human"),
                "max_memory_bytes": maxmemory,
                "max_memory_human": info.get("maxmemory_human"),
                "memory_usage_percentage": round(memory_usage_pct, 2),
                "memory_fragmentation_ratio": info.get("mem_fragmentation_ratio"),
                "memory_breakdown": memory_breakdown,
                "status": (
                    "critical"
                    if memory_usage_pct > 90
                    else "warning" if memory_usage_pct > 80 else "healthy"
                ),
            }

        except Exception as e:
            return {"error": str(e), "status": "error"}

    async def _check_performance_metrics(self, client: redis.Redis) -> Dict[str, Any]:
        """Check Redis performance metrics."""
        try:
            info = await client.info("stats")

            keyspace_hits = info.get("keyspace_hits", 0)
            keyspace_misses = info.get("keyspace_misses", 0)
            total_keyspace = keyspace_hits + keyspace_misses

            hit_rate = 0
            if total_keyspace > 0:
                hit_rate = (keyspace_hits / total_keyspace) * 100

            return {
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec"),
                "total_commands_processed": info.get("total_commands_processed"),
                "keyspace_hits": keyspace_hits,
                "keyspace_misses": keyspace_misses,
                "hit_rate_percentage": round(hit_rate, 2),
                "expired_keys": info.get("expired_keys"),
                "evicted_keys": info.get("evicted_keys"),
                "rejected_connections": info.get("rejected_connections"),
                "status": "warning" if hit_rate < 80 else "healthy",
            }

        except Exception as e:
            return {"error": str(e), "status": "error"}

    async def _check_configuration(self, client: redis.Redis) -> Dict[str, Any]:
        """Check Redis configuration for SRE best practices."""
        try:
            config = await client.config_get("*")

            # Key configuration checks
            checks = {
                "persistence_enabled": {
                    "save": config.get("save"),
                    "appendonly": config.get("appendonly") == "yes",
                },
                "memory_policy": config.get("maxmemory-policy"),
                "timeout": config.get("timeout"),
                "tcp_keepalive": config.get("tcp-keepalive"),
                "slowlog_threshold": config.get("slowlog-log-slower-than"),
            }

            # Configuration recommendations
            recommendations = []
            if config.get("maxmemory-policy") == "noeviction":
                recommendations.append("Consider setting a memory eviction policy")

            if config.get("save") == "":
                recommendations.append("Consider enabling periodic saves for data persistence")

            return {
                "configuration_checks": checks,
                "recommendations": recommendations,
                "raw_config": config,
            }

        except Exception as e:
            return {"error": str(e)}

    async def _analyze_keyspace(self, client: redis.Redis) -> Dict[str, Any]:
        """Analyze Redis keyspace information."""
        try:
            info = await client.info("keyspace")

            keyspace_analysis = {}
            total_keys = 0

            for db_key, db_info in info.items():
                if db_key.startswith("db"):
                    # Parse db info string like "keys=2,expires=0,avg_ttl=0"
                    db_stats = {}
                    for stat in db_info.split(","):
                        key, value = stat.split("=")
                        db_stats[key] = int(value)

                    keyspace_analysis[db_key] = db_stats
                    total_keys += db_stats.get("keys", 0)

            return {
                "total_keys": total_keys,
                "databases": keyspace_analysis,
                "status": "warning" if total_keys > 1000000 else "healthy",
            }

        except Exception as e:
            return {"error": str(e), "status": "error"}

    async def _check_slowlog(self, client: redis.Redis) -> Dict[str, Any]:
        """Check Redis slow query log."""
        try:
            slowlog_len = await client.slowlog_len()
            slowlog_entries = await client.slowlog_get(10)  # Get last 10 entries

            # Analyze slow queries
            slow_commands = {}
            for entry in slowlog_entries:
                command = entry["command"][0] if entry["command"] else "unknown"
                if command not in slow_commands:
                    slow_commands[command] = 0
                slow_commands[command] += 1

            return {
                "slowlog_length": slowlog_len,
                "recent_slow_queries": len(slowlog_entries),
                "slow_command_distribution": slow_commands,
                "slowlog_entries": [
                    {
                        "id": entry["id"],
                        "timestamp": entry["start_time"],
                        "duration_ms": entry["duration"] / 1000,
                        "command": " ".join(entry["command"][:3]),  # First 3 parts of command
                    }
                    for entry in slowlog_entries[:5]  # Only show top 5
                ],
                "status": "warning" if slowlog_len > 50 else "healthy",
            }

        except Exception as e:
            return {"error": str(e), "status": "error"}

    async def _analyze_client_connections(self, client: redis.Redis) -> Dict[str, Any]:
        """Analyze client connection information."""
        try:
            info = await client.info("clients")
            clients_list = await client.client_list()

            # Analyze connection patterns
            connection_types = {}
            idle_connections = 0

            for client_info in clients_list:
                client_type = client_info.get("name", "unnamed")
                if client_type not in connection_types:
                    connection_types[client_type] = 0
                connection_types[client_type] += 1

                if client_info.get("idle", 0) > 300:  # 5 minutes
                    idle_connections += 1

            return {
                "connected_clients": info.get("connected_clients"),
                "client_recent_max_input_buffer": info.get("client_recent_max_input_buffer"),
                "client_recent_max_output_buffer": info.get("client_recent_max_output_buffer"),
                "blocked_clients": info.get("blocked_clients"),
                "connection_distribution": connection_types,
                "idle_connections": idle_connections,
                "status": "warning" if idle_connections > 10 else "healthy",
            }

        except Exception as e:
            return {"error": str(e), "status": "error"}

    def _determine_overall_status(self, diagnostics: Dict[str, Any]) -> str:
        """Determine overall Redis health status."""
        statuses = []

        for section, data in diagnostics.items():
            if isinstance(data, dict) and "status" in data:
                statuses.append(data["status"])

        if "error" in statuses or "critical" in statuses:
            return "critical"
        elif "warning" in statuses:
            return "warning"
        elif "healthy" in statuses:
            return "healthy"
        else:
            return "unknown"

    def _identify_critical_issues(self, diagnostics: Dict[str, Any]) -> List[str]:
        """Identify critical issues requiring immediate attention."""
        issues = []

        # Memory usage
        memory = diagnostics.get("memory", {})
        if memory.get("memory_usage_percentage", 0) > 95:
            issues.append("Critical: Memory usage above 95%")

        # Connection issues
        connection = diagnostics.get("connection", {})
        if connection.get("status") == "error":
            issues.append("Critical: Redis connection failed")

        # Performance issues
        performance = diagnostics.get("performance", {})
        if performance.get("hit_rate_percentage", 100) < 50:
            issues.append("Critical: Cache hit rate below 50%")

        return issues

    def _identify_warnings(self, diagnostics: Dict[str, Any]) -> List[str]:
        """Identify warning conditions that need attention."""
        warnings = []

        # Memory warnings
        memory = diagnostics.get("memory", {})
        memory_pct = memory.get("memory_usage_percentage", 0)
        if 80 <= memory_pct <= 95:
            warnings.append(f"Memory usage at {memory_pct}%")

        # Performance warnings
        performance = diagnostics.get("performance", {})
        hit_rate = performance.get("hit_rate_percentage", 100)
        if 50 <= hit_rate < 80:
            warnings.append(f"Cache hit rate at {hit_rate}%")

        # Slow queries
        slowlog = diagnostics.get("slowlog", {})
        if slowlog.get("slowlog_length", 0) > 10:
            warnings.append(f"Slow query log has {slowlog['slowlog_length']} entries")

        return warnings

    def _generate_recommendations(self, diagnostics: Dict[str, Any]) -> List[str]:
        """Generate SRE recommendations based on diagnostics."""
        recommendations = []

        # Memory recommendations
        memory = diagnostics.get("memory", {})
        if memory.get("memory_usage_percentage", 0) > 80:
            recommendations.append("Consider scaling Redis or implementing memory optimization")

        # Performance recommendations
        performance = diagnostics.get("performance", {})
        if performance.get("hit_rate_percentage", 100) < 90:
            recommendations.append("Review caching strategy and key expiration policies")

        # Configuration recommendations
        config = diagnostics.get("configuration", {})
        if config.get("recommendations"):
            recommendations.extend(config["recommendations"])

        return recommendations


# Singleton instance for the diagnostics tool
_redis_diagnostics: Optional[RedisDiagnostics] = None


def get_redis_diagnostics() -> RedisDiagnostics:
    """Get or create the Redis diagnostics singleton."""
    global _redis_diagnostics
    if _redis_diagnostics is None:
        _redis_diagnostics = RedisDiagnostics()
    return _redis_diagnostics

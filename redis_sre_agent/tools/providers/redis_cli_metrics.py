"""Redis CLI metrics provider implementation.

This provider connects directly to Redis instances using redis-cli commands
to gather metrics. It has limited capabilities compared to time-series systems
but provides direct access to Redis INFO data.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from ..protocols import MetricDefinition, MetricsProvider, MetricValue, TimeRange

logger = logging.getLogger(__name__)


class RedisCLIMetricsProvider:
    """Redis CLI-based metrics provider.
    
    This provider connects directly to Redis instances and extracts metrics
    from INFO commands. It only supports current values, not time-series queries.
    """
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client: Optional[redis.Redis] = None
        self._metric_definitions: Optional[List[MetricDefinition]] = None
    
    @property
    def provider_name(self) -> str:
        return f"Redis CLI ({self.redis_url})"
    
    @property
    def supports_time_queries(self) -> bool:
        return False
    
    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(
                self.redis_url, 
                decode_responses=True, 
                socket_timeout=10, 
                socket_connect_timeout=5
            )
        return self._client
    
    async def list_metrics(self) -> List[MetricDefinition]:
        """List all available Redis metrics from INFO command."""
        if self._metric_definitions is not None:
            return self._metric_definitions
        
        # Define Redis metrics based on INFO sections
        metrics = [
            # Memory metrics
            MetricDefinition("used_memory", "Total memory used by Redis", "bytes", "gauge"),
            MetricDefinition("used_memory_rss", "Resident set size memory", "bytes", "gauge"),
            MetricDefinition("used_memory_peak", "Peak memory usage", "bytes", "gauge"),
            MetricDefinition("used_memory_lua", "Memory used by Lua scripts", "bytes", "gauge"),
            MetricDefinition("mem_fragmentation_ratio", "Memory fragmentation ratio", "ratio", "gauge"),
            MetricDefinition("maxmemory", "Maximum memory limit", "bytes", "gauge"),
            
            # Connection metrics
            MetricDefinition("connected_clients", "Number of connected clients", "count", "gauge"),
            MetricDefinition("blocked_clients", "Number of blocked clients", "count", "gauge"),
            MetricDefinition("rejected_connections", "Total rejected connections", "count", "counter"),
            
            # Performance metrics
            MetricDefinition("total_commands_processed", "Total commands processed", "count", "counter"),
            MetricDefinition("instantaneous_ops_per_sec", "Operations per second", "ops/sec", "gauge"),
            MetricDefinition("keyspace_hits", "Number of keyspace hits", "count", "counter"),
            MetricDefinition("keyspace_misses", "Number of keyspace misses", "count", "counter"),
            MetricDefinition("expired_keys", "Number of expired keys", "count", "counter"),
            MetricDefinition("evicted_keys", "Number of evicted keys", "count", "counter"),
            
            # Persistence metrics
            MetricDefinition("rdb_last_save_time", "Last RDB save timestamp", "timestamp", "gauge"),
            MetricDefinition("rdb_changes_since_last_save", "Changes since last RDB save", "count", "gauge"),
            MetricDefinition("aof_enabled", "AOF enabled status", "boolean", "gauge"),
            MetricDefinition("aof_rewrite_in_progress", "AOF rewrite in progress", "boolean", "gauge"),
            
            # Replication metrics
            MetricDefinition("role", "Redis role (master/slave)", "string", "gauge"),
            MetricDefinition("connected_slaves", "Number of connected slaves", "count", "gauge"),
            MetricDefinition("master_repl_offset", "Master replication offset", "bytes", "gauge"),
            
            # CPU metrics
            MetricDefinition("used_cpu_sys", "System CPU used by Redis", "seconds", "counter"),
            MetricDefinition("used_cpu_user", "User CPU used by Redis", "seconds", "counter"),
            
            # Keyspace metrics (dynamic based on databases)
            MetricDefinition("db_keys", "Number of keys in database", "count", "gauge"),
            MetricDefinition("db_expires", "Number of keys with expiration", "count", "gauge"),
            MetricDefinition("db_avg_ttl", "Average TTL of keys", "milliseconds", "gauge"),
        ]
        
        self._metric_definitions = metrics
        return metrics
    
    async def get_current_value(self, metric_name: str, labels: Optional[Dict[str, str]] = None) -> Optional[MetricValue]:
        """Get current value of a Redis metric."""
        try:
            client = await self._get_client()
            info = await client.info("all")
            
            # Handle database-specific metrics
            if metric_name.startswith("db_") and labels and "database" in labels:
                db_num = labels["database"]
                db_key = f"db{db_num}"
                if db_key not in info:
                    return None
                
                db_info = info[db_key]
                if metric_name == "db_keys":
                    return MetricValue(db_info.get("keys", 0))
                elif metric_name == "db_expires":
                    return MetricValue(db_info.get("expires", 0))
                elif metric_name == "db_avg_ttl":
                    return MetricValue(db_info.get("avg_ttl", 0))
            
            # Handle standard metrics
            if metric_name in info:
                value = info[metric_name]
                
                # Convert boolean strings to integers
                if isinstance(value, str):
                    if value.lower() in ("yes", "true", "1"):
                        value = 1
                    elif value.lower() in ("no", "false", "0"):
                        value = 0
                    else:
                        try:
                            value = float(value)
                        except ValueError:
                            # Keep as string for non-numeric values
                            pass
                
                return MetricValue(value, labels=labels)
            
            # Handle calculated metrics
            if metric_name == "keyspace_hit_rate":
                hits = info.get("keyspace_hits", 0)
                misses = info.get("keyspace_misses", 0)
                total = hits + misses
                if total > 0:
                    return MetricValue(hits / total, labels=labels)
                return MetricValue(0.0, labels=labels)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting metric {metric_name}: {e}")
            return None
    
    async def query_time_range(
        self, 
        metric_name: str, 
        time_range: TimeRange,
        labels: Optional[Dict[str, str]] = None,
        step: Optional[str] = None
    ) -> List[MetricValue]:
        """Redis CLI provider doesn't support time-range queries."""
        raise NotImplementedError("Redis CLI provider doesn't support time-range queries. Use Prometheus or Redis Cloud API for historical data.")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Redis connection health."""
        try:
            client = await self._get_client()
            await client.ping()
            
            # Get basic info for health status
            info = await client.info("server")
            
            return {
                "status": "healthy",
                "provider": self.provider_name,
                "redis_version": info.get("redis_version", "unknown"),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
                "connected": True,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": self.provider_name,
                "error": str(e),
                "connected": False,
                "timestamp": datetime.now().isoformat()
            }
    
    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Helper function to create instances
def create_redis_cli_provider(redis_url: str) -> RedisCLIMetricsProvider:
    """Create a Redis CLI metrics provider instance."""
    return RedisCLIMetricsProvider(redis_url)

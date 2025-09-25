"""Direct Redis diagnostic tools for SRE operations."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

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
            results["diagnostics"]["replication"] = await self._analyze_replication(client)
            results["diagnostics"]["persistence"] = await self._analyze_persistence(client)
            results["diagnostics"]["cpu"] = await self._analyze_cpu_usage(client)

            logger.info("Redis diagnostics completed successfully")

        except Exception as e:
            logger.error(f"Redis diagnostics failed: {e}")
            results["diagnostics"]["error"] = str(e)

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
                "ping_response": pong,
                "ping_duration_ms": round(ping_duration, 2),
                "basic_operations_test": test_value == "test_value",
            }

        except Exception as e:
            return {
                "error": str(e),
                "ping_duration_ms": None,
                "basic_operations_test": False,
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

            # Get fragmentation ratio
            info.get("mem_fragmentation_ratio", 1.0)

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
                "memory_usage_percentage": round(memory_usage_pct, 2) if maxmemory > 0 else None,
                "memory_fragmentation_ratio": info.get("mem_fragmentation_ratio"),
                "memory_breakdown": memory_breakdown,
                "used_memory_rss": info.get("used_memory_rss"),
                "used_memory_peak": info.get("used_memory_peak"),
                "used_memory_peak_human": info.get("used_memory_peak_human"),
                "used_memory_overhead": info.get("used_memory_overhead"),
                "used_memory_startup": info.get("used_memory_startup"),
                "used_memory_dataset": info.get("used_memory_dataset"),
                "mem_allocator": info.get("mem_allocator"),
                "mem_fragmentation_bytes": info.get("mem_fragmentation_bytes"),
                "mem_not_counted_for_evict": info.get("mem_not_counted_for_evict"),
                "mem_replication_backlog": info.get("mem_replication_backlog"),
                "active_defrag_running": info.get("active_defrag_running"),
                "lazyfree_pending_objects": info.get("lazyfree_pending_objects"),
                "raw_memory_info": info,
            }

        except Exception as e:
            return {"error": str(e)}

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
                "total_keyspace_operations": total_keyspace,
                "hit_rate_percentage": round(hit_rate, 2) if total_keyspace > 0 else None,
                "expired_keys": info.get("expired_keys"),
                "evicted_keys": info.get("evicted_keys"),
                "rejected_connections": info.get("rejected_connections"),
                "total_connections_received": info.get("total_connections_received"),
                "instantaneous_input_kbps": info.get("instantaneous_input_kbps"),
                "instantaneous_output_kbps": info.get("instantaneous_output_kbps"),
                "sync_full": info.get("sync_full"),
                "sync_partial_ok": info.get("sync_partial_ok"),
                "sync_partial_err": info.get("sync_partial_err"),
                "pubsub_channels": info.get("pubsub_channels"),
                "pubsub_patterns": info.get("pubsub_patterns"),
                "migrate_cached_sockets": info.get("migrate_cached_sockets"),
                "slave_expires_tracked_keys": info.get("slave_expires_tracked_keys"),
                "active_defrag_hits": info.get("active_defrag_hits"),
                "active_defrag_misses": info.get("active_defrag_misses"),
                "active_defrag_key_hits": info.get("active_defrag_key_hits"),
                "active_defrag_key_misses": info.get("active_defrag_key_misses"),
                "raw_stats_info": info,
            }

        except Exception as e:
            return {"error": str(e)}

    async def _check_configuration(self, client: redis.Redis) -> Dict[str, Any]:
        """Check Redis configuration for SRE best practices."""
        try:
            config = await client.config_get("*")

            # Extract key configuration values
            return {
                "maxmemory": config.get("maxmemory"),
                "maxmemory_policy": config.get("maxmemory-policy"),
                "maxmemory_samples": config.get("maxmemory-samples"),
                "save": config.get("save"),
                "appendonly": config.get("appendonly"),
                "appendfsync": config.get("appendfsync"),
                "timeout": config.get("timeout"),
                "tcp_keepalive": config.get("tcp-keepalive"),
                "slowlog_log_slower_than": config.get("slowlog-log-slower-than"),
                "slowlog_max_len": config.get("slowlog-max-len"),
                "databases": config.get("databases"),
                "maxclients": config.get("maxclients"),
                "port": config.get("port"),
                "bind": config.get("bind"),
                "protected_mode": config.get("protected-mode"),
                "requirepass": config.get("requirepass"),
                "masterauth": config.get("masterauth"),
                "auto_aof_rewrite_percentage": config.get("auto-aof-rewrite-percentage"),
                "auto_aof_rewrite_min_size": config.get("auto-aof-rewrite-min-size"),
                "hash_max_ziplist_entries": config.get("hash-max-ziplist-entries"),
                "hash_max_ziplist_value": config.get("hash-max-ziplist-value"),
                "list_max_ziplist_size": config.get("list-max-ziplist-size"),
                "set_max_intset_entries": config.get("set-max-intset-entries"),
                "zset_max_ziplist_entries": config.get("zset-max-ziplist-entries"),
                "zset_max_ziplist_value": config.get("zset-max-ziplist-value"),
                "hll_sparse_max_bytes": config.get("hll-sparse-max-bytes"),
                "stream_node_max_bytes": config.get("stream-node-max-bytes"),
                "stream_node_max_entries": config.get("stream-node-max-entries"),
                "activerehashing": config.get("activerehashing"),
                "client_output_buffer_limit_normal": config.get(
                    "client-output-buffer-limit normal"
                ),
                "client_output_buffer_limit_replica": config.get(
                    "client-output-buffer-limit replica"
                ),
                "client_output_buffer_limit_pubsub": config.get(
                    "client-output-buffer-limit pubsub"
                ),
                "hz": config.get("hz"),
                "dynamic_hz": config.get("dynamic-hz"),
                "rdb_compression": config.get("rdbcompression"),
                "rdb_checksum": config.get("rdbchecksum"),
                "stop_writes_on_bgsave_error": config.get("stop-writes-on-bgsave-error"),
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
                    # Handle both string format and dict format from different Redis client versions
                    if isinstance(db_info, dict):
                        db_stats = db_info
                    else:
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
                "raw_keyspace_info": info,
            }

        except Exception as e:
            return {"error": str(e)}

    async def _check_slowlog(self, client: redis.Redis) -> Dict[str, Any]:
        """Check Redis slow query log."""
        try:
            slowlog_len = await client.slowlog_len()
            slowlog_entries = await client.slowlog_get(10)  # Get last 10 entries

            # Analyze slow queries
            slow_commands = {}
            for entry in slowlog_entries:
                command = str(entry["command"][0]) if entry["command"] else "unknown"
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
                        "duration_microseconds": entry["duration"],
                        "duration_ms": entry["duration"] / 1000,
                        "command": " ".join(
                            str(x) for x in entry["command"][:3]
                        ),  # First 3 parts of command
                        "full_command": (
                            " ".join(str(x) for x in entry["command"])
                            if len(entry["command"]) <= 10
                            else " ".join(str(x) for x in entry["command"][:10]) + "..."
                        ),
                        "client_ip": entry.get("client_ip"),
                        "client_port": entry.get("client_port"),
                        "client_name": entry.get("client_name"),
                    }
                    for entry in slowlog_entries
                ],
            }

        except Exception as e:
            return {"error": str(e)}

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

                if int(client_info.get("idle", 0)) > 300:  # 5 minutes
                    idle_connections += 1

            # Analyze idle times
            idle_time_distribution = {"<1min": 0, "1-5min": 0, "5-30min": 0, ">30min": 0}
            client_details = []

            for client_info in clients_list:
                idle_time = int(client_info.get("idle", 0))
                if idle_time < 60:
                    idle_time_distribution["<1min"] += 1
                elif idle_time < 300:
                    idle_time_distribution["1-5min"] += 1
                elif idle_time < 1800:
                    idle_time_distribution["5-30min"] += 1
                else:
                    idle_time_distribution[">30min"] += 1

                client_details.append(
                    {
                        "id": client_info.get("id"),
                        "name": client_info.get("name"),
                        "addr": client_info.get("addr"),
                        "idle": idle_time,
                        "flags": client_info.get("flags"),
                        "db": client_info.get("db"),
                        "sub": client_info.get("sub"),
                        "psub": client_info.get("psub"),
                        "multi": client_info.get("multi"),
                        "qbuf": client_info.get("qbuf"),
                        "qbuf_free": client_info.get("qbuf-free"),
                        "obl": client_info.get("obl"),
                        "oll": client_info.get("oll"),
                        "omem": client_info.get("omem"),
                        "cmd": client_info.get("cmd"),
                    }
                )

            return {
                "connected_clients": info.get("connected_clients"),
                "client_recent_max_input_buffer": info.get("client_recent_max_input_buffer"),
                "client_recent_max_output_buffer": info.get("client_recent_max_output_buffer"),
                "blocked_clients": info.get("blocked_clients"),
                "tracking_clients": info.get("tracking_clients"),
                "clients_in_timeout_table": info.get("clients_in_timeout_table"),
                "connection_distribution": connection_types,
                "idle_connections_count": idle_connections,
                "idle_time_distribution": idle_time_distribution,
                "total_clients_analyzed": len(clients_list),
                "client_connections": client_details[
                    :20
                ],  # Limit to first 20 clients for performance
                "raw_client_info": info,
            }

        except Exception as e:
            return {"error": str(e)}

    async def _analyze_replication(self, client: redis.Redis) -> Dict[str, Any]:
        """Analyze Redis replication information."""
        try:
            info = await client.info("replication")

            return {
                "role": info.get("role"),
                "connected_slaves": info.get("connected_slaves"),
                "master_replid": info.get("master_replid"),
                "master_replid2": info.get("master_replid2"),
                "master_repl_offset": info.get("master_repl_offset"),
                "second_repl_offset": info.get("second_repl_offset"),
                "repl_backlog_active": info.get("repl_backlog_active"),
                "repl_backlog_size": info.get("repl_backlog_size"),
                "repl_backlog_first_byte_offset": info.get("repl_backlog_first_byte_offset"),
                "repl_backlog_histlen": info.get("repl_backlog_histlen"),
                "master_host": info.get("master_host"),
                "master_port": info.get("master_port"),
                "master_link_status": info.get("master_link_status"),
                "master_last_io_seconds_ago": info.get("master_last_io_seconds_ago"),
                "master_sync_in_progress": info.get("master_sync_in_progress"),
                "slave_repl_offset": info.get("slave_repl_offset"),
                "slave_priority": info.get("slave_priority"),
                "slave_read_only": info.get("slave_read_only"),
                "raw_replication_info": info,
            }

        except Exception as e:
            return {"error": str(e)}

    async def _analyze_persistence(self, client: redis.Redis) -> Dict[str, Any]:
        """Analyze Redis persistence information."""
        try:
            info = await client.info("persistence")

            return {
                "loading": info.get("loading"),
                "rdb_changes_since_last_save": info.get("rdb_changes_since_last_save"),
                "rdb_bgsave_in_progress": info.get("rdb_bgsave_in_progress"),
                "rdb_last_save_time": info.get("rdb_last_save_time"),
                "rdb_last_bgsave_status": info.get("rdb_last_bgsave_status"),
                "rdb_last_bgsave_time_sec": info.get("rdb_last_bgsave_time_sec"),
                "rdb_current_bgsave_time_sec": info.get("rdb_current_bgsave_time_sec"),
                "rdb_last_cow_size": info.get("rdb_last_cow_size"),
                "aof_enabled": info.get("aof_enabled"),
                "aof_rewrite_in_progress": info.get("aof_rewrite_in_progress"),
                "aof_rewrite_scheduled": info.get("aof_rewrite_scheduled"),
                "aof_last_rewrite_time_sec": info.get("aof_last_rewrite_time_sec"),
                "aof_current_rewrite_time_sec": info.get("aof_current_rewrite_time_sec"),
                "aof_last_bgrewrite_status": info.get("aof_last_bgrewrite_status"),
                "aof_last_write_status": info.get("aof_last_write_status"),
                "aof_last_cow_size": info.get("aof_last_cow_size"),
                "module_fork_in_progress": info.get("module_fork_in_progress"),
                "module_fork_last_cow_size": info.get("module_fork_last_cow_size"),
                "aof_current_size": info.get("aof_current_size"),
                "aof_base_size": info.get("aof_base_size"),
                "aof_pending_rewrite": info.get("aof_pending_rewrite"),
                "aof_buffer_length": info.get("aof_buffer_length"),
                "aof_rewrite_buffer_length": info.get("aof_rewrite_buffer_length"),
                "aof_pending_bio_fsync": info.get("aof_pending_bio_fsync"),
                "aof_delayed_fsync": info.get("aof_delayed_fsync"),
                "raw_persistence_info": info,
            }

        except Exception as e:
            return {"error": str(e)}

    async def _analyze_cpu_usage(self, client: redis.Redis) -> Dict[str, Any]:
        """Analyze Redis CPU usage information."""
        try:
            info = await client.info("cpu")

            return {
                "used_cpu_sys": info.get("used_cpu_sys"),
                "used_cpu_user": info.get("used_cpu_user"),
                "used_cpu_sys_children": info.get("used_cpu_sys_children"),
                "used_cpu_user_children": info.get("used_cpu_user_children"),
                "used_cpu_sys_main_thread": info.get("used_cpu_sys_main_thread"),
                "used_cpu_user_main_thread": info.get("used_cpu_user_main_thread"),
                "raw_cpu_info": info,
            }

        except Exception as e:
            return {"error": str(e)}


# Per-URL instances for the diagnostics tool
_redis_diagnostics_cache: Dict[str, RedisDiagnostics] = {}


def get_redis_diagnostics(redis_url: str) -> RedisDiagnostics:
    """Get or create a Redis diagnostics instance for the given URL."""
    if redis_url not in _redis_diagnostics_cache:
        _redis_diagnostics_cache[redis_url] = RedisDiagnostics(redis_url)
    return _redis_diagnostics_cache[redis_url]


async def capture_redis_diagnostics(
    redis_url: str,
    sections: Optional[Union[str, List[str]]] = None,
    time_window_seconds: Optional[int] = None,
    include_raw_data: bool = True,
) -> Dict[str, Any]:
    """
    Capture Redis diagnostic data for analysis.

    This function provides the same interface for both external tools (baseline capture)
    and agent tools (follow-up investigation). It returns raw metric data without
    pre-calculated assessments, allowing the agent to perform its own analysis.

    Args:
        sections: Which diagnostic sections to capture. Options:
            - None or "all": Capture all sections
            - "memory": Memory usage and fragmentation
            - "performance": Hit rates, ops/sec, command statistics
            - "clients": Connection analysis and client patterns
            - "slowlog": Slow query log analysis
            - "configuration": Current Redis configuration
            - "keyspace": Database and key statistics
            - "replication": Master/slave replication status
            - "persistence": RDB/AOF persistence status
            - "cpu": CPU usage statistics
            - ["memory", "clients"]: Multiple sections as list

        time_window_seconds: For metrics that support time-based analysis (future enhancement)
        redis_url: Redis connection URL (required)
        include_raw_data: Whether to include raw Redis INFO output (default: True)

    Returns:
        Dict containing requested diagnostic data with raw metrics only.
        Agent is responsible for calculating percentages, ratios, and assessments.

    Example:
        # External baseline capture
        baseline = await capture_redis_diagnostics("redis://localhost:6379")

        # Agent targeted investigation
        memory_data = await capture_redis_diagnostics("redis://localhost:6379", sections="memory")
        client_data = await capture_redis_diagnostics("redis://localhost:6379", sections=["clients", "slowlog"])
    """
    # Initialize diagnostics instance
    diagnostics = get_redis_diagnostics(redis_url)

    # Normalize sections parameter
    if sections is None or sections == "all":
        requested_sections = {
            "memory",
            "performance",
            "clients",
            "slowlog",
            "configuration",
            "keyspace",
            "replication",
            "persistence",
            "cpu",
        }
    elif isinstance(sections, str):
        requested_sections = {sections}
    else:
        requested_sections = set(sections)

    # Validate sections
    valid_sections = {
        "memory",
        "performance",
        "clients",
        "slowlog",
        "configuration",
        "keyspace",
        "replication",
        "persistence",
        "cpu",
    }
    invalid_sections = requested_sections - valid_sections
    if invalid_sections:
        raise ValueError(f"Invalid sections: {invalid_sections}. Valid sections: {valid_sections}")

    # Capture diagnostic data
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "redis_url": diagnostics.redis_url,
        "sections_captured": sorted(list(requested_sections)),
        "time_window_seconds": time_window_seconds,
        "capture_status": "success",  # Default to success, will be changed if errors occur
        "diagnostics": {},
    }

    try:
        client = await diagnostics.get_client()

        # Capture basic connection info for all requests
        result["diagnostics"]["connection"] = await diagnostics._test_connection(client)

        # Capture requested sections
        if "memory" in requested_sections:
            result["diagnostics"]["memory"] = await _capture_memory_metrics(
                client, include_raw_data
            )

        if "performance" in requested_sections:
            result["diagnostics"]["performance"] = await _capture_performance_metrics(
                client, include_raw_data
            )

        if "clients" in requested_sections:
            result["diagnostics"]["clients"] = await _capture_client_metrics(
                client, include_raw_data
            )

        if "slowlog" in requested_sections:
            result["diagnostics"]["slowlog"] = await _capture_slowlog_metrics(
                client, include_raw_data
            )

        if "configuration" in requested_sections:
            result["diagnostics"]["configuration"] = await _capture_config_metrics(
                client, include_raw_data
            )

        if "keyspace" in requested_sections:
            result["diagnostics"]["keyspace"] = await _capture_keyspace_metrics(
                client, include_raw_data
            )

        # Always include client list for comprehensive analysis
        result["diagnostics"]["client_list"] = await _capture_client_list(client)

        if "replication" in requested_sections:
            result["diagnostics"]["replication"] = await _capture_replication_metrics(
                client, include_raw_data
            )

        if "persistence" in requested_sections:
            result["diagnostics"]["persistence"] = await _capture_persistence_metrics(
                client, include_raw_data
            )

        if "cpu" in requested_sections:
            result["diagnostics"]["cpu"] = await _capture_cpu_metrics(client, include_raw_data)

    except Exception as e:
        logger.error(f"Failed to capture Redis diagnostics: {e}")
        result["capture_status"] = "failed"
        result["diagnostics"]["error"] = str(e)

    return result


async def _capture_memory_metrics(client: redis.Redis, include_raw: bool = True) -> Dict[str, Any]:
    """Capture raw memory metrics without pre-calculated assessments."""
    try:
        info = await client.info("memory")

        # Return only raw metrics - no status calculations
        metrics = {
            "used_memory_bytes": info.get("used_memory", 0),
            "used_memory_human": info.get("used_memory_human"),
            "used_memory_rss_bytes": info.get("used_memory_rss", 0),
            "used_memory_peak_bytes": info.get("used_memory_peak", 0),
            "used_memory_peak_human": info.get("used_memory_peak_human"),
            "used_memory_overhead_bytes": info.get("used_memory_overhead", 0),
            "used_memory_startup_bytes": info.get("used_memory_startup", 0),
            "used_memory_dataset_bytes": info.get("used_memory_dataset", 0),
            "maxmemory_bytes": info.get("maxmemory", 0),
            "maxmemory_human": info.get("maxmemory_human"),
            "mem_fragmentation_ratio": info.get("mem_fragmentation_ratio", 1.0),
            "mem_fragmentation_bytes": info.get("mem_fragmentation_bytes", 0),
            "mem_allocator": info.get("mem_allocator"),
            "mem_not_counted_for_evict": info.get("mem_not_counted_for_evict", 0),
            "mem_replication_backlog": info.get("mem_replication_backlog", 0),
            "active_defrag_running": info.get("active_defrag_running", 0),
            "lazyfree_pending_objects": info.get("lazyfree_pending_objects", 0),
        }

        if include_raw:
            metrics["raw_memory_info"] = info

        return metrics

    except Exception as e:
        return {"error": str(e)}


async def _capture_performance_metrics(
    client: redis.Redis, include_raw: bool = True
) -> Dict[str, Any]:
    """Capture raw performance metrics without calculations."""
    try:
        info = await client.info("stats")

        metrics = {
            "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
            "total_commands_processed": info.get("total_commands_processed", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "expired_keys": info.get("expired_keys", 0),
            "evicted_keys": info.get("evicted_keys", 0),
            "rejected_connections": info.get("rejected_connections", 0),
            "total_connections_received": info.get("total_connections_received", 0),
            "instantaneous_input_kbps": info.get("instantaneous_input_kbps", 0),
            "instantaneous_output_kbps": info.get("instantaneous_output_kbps", 0),
            "sync_full": info.get("sync_full", 0),
            "sync_partial_ok": info.get("sync_partial_ok", 0),
            "sync_partial_err": info.get("sync_partial_err", 0),
            "pubsub_channels": info.get("pubsub_channels", 0),
            "pubsub_patterns": info.get("pubsub_patterns", 0),
            "active_defrag_hits": info.get("active_defrag_hits", 0),
            "active_defrag_misses": info.get("active_defrag_misses", 0),
            "active_defrag_key_hits": info.get("active_defrag_key_hits", 0),
            "active_defrag_key_misses": info.get("active_defrag_key_misses", 0),
        }

        if include_raw:
            metrics["raw_stats_info"] = info

        return metrics

    except Exception as e:
        return {"error": str(e)}


async def _capture_client_metrics(client: redis.Redis, include_raw: bool = True) -> Dict[str, Any]:
    """Capture raw client connection metrics."""
    try:
        info = await client.info("clients")
        clients_list = await client.client_list()

        # Collect raw client data without analysis
        client_details = []
        for client_info in clients_list:
            client_details.append(
                {
                    "id": client_info.get("id"),
                    "name": client_info.get("name"),
                    "addr": client_info.get("addr"),
                    "idle_seconds": int(client_info.get("idle", 0)),
                    "flags": client_info.get("flags"),
                    "db": client_info.get("db"),
                    "sub": client_info.get("sub"),
                    "psub": client_info.get("psub"),
                    "multi": client_info.get("multi"),
                    "qbuf": client_info.get("qbuf"),
                    "qbuf_free": client_info.get("qbuf-free"),
                    "obl": client_info.get("obl"),
                    "oll": client_info.get("oll"),
                    "omem": client_info.get("omem"),
                    "cmd": client_info.get("cmd"),
                }
            )

        metrics = {
            "connected_clients": info.get("connected_clients", 0),
            "client_recent_max_input_buffer": info.get("client_recent_max_input_buffer", 0),
            "client_recent_max_output_buffer": info.get("client_recent_max_output_buffer", 0),
            "blocked_clients": info.get("blocked_clients", 0),
            "tracking_clients": info.get("tracking_clients", 0),
            "clients_in_timeout_table": info.get("clients_in_timeout_table", 0),
            "client_connections": client_details,  # Raw client data for agent analysis
        }

        if include_raw:
            metrics["raw_client_info"] = info

        return metrics

    except Exception as e:
        return {"error": str(e)}


async def _capture_slowlog_metrics(client: redis.Redis, include_raw: bool = True) -> Dict[str, Any]:
    """Capture raw slowlog metrics."""
    try:
        slowlog_len = await client.slowlog_len()
        slowlog_entries = await client.slowlog_get(50)  # Get more entries for analysis

        # Raw slowlog data without pre-analysis
        slowlog_data = []
        for entry in slowlog_entries:
            slowlog_data.append(
                {
                    "id": entry["id"],
                    "timestamp": entry["start_time"],
                    "duration_microseconds": entry["duration"],
                    "command": " ".join(str(x) for x in entry["command"][:5]),  # First 5 parts
                    "full_command": (
                        " ".join(str(x) for x in entry["command"])
                        if len(entry["command"]) <= 15
                        else " ".join(str(x) for x in entry["command"][:15]) + "..."
                    ),
                    "client_ip": entry.get("client_ip"),
                    "client_port": entry.get("client_port"),
                    "client_name": entry.get("client_name"),
                }
            )

        metrics = {
            "slowlog_length": slowlog_len,
            "slowlog_entries": slowlog_data,
        }

        return metrics

    except Exception as e:
        return {"error": str(e)}


async def _capture_config_metrics(client: redis.Redis, include_raw: bool = True) -> Dict[str, Any]:
    """Capture raw configuration metrics."""
    try:
        config = await client.config_get("*")

        # Key configuration values as raw data
        metrics = {
            "maxmemory": config.get("maxmemory"),
            "maxmemory_policy": config.get("maxmemory-policy"),
            "maxmemory_samples": config.get("maxmemory-samples"),
            "save": config.get("save"),
            "appendonly": config.get("appendonly"),
            "appendfsync": config.get("appendfsync"),
            "timeout": config.get("timeout"),
            "tcp_keepalive": config.get("tcp-keepalive"),
            "slowlog_log_slower_than": config.get("slowlog-log-slower-than"),
            "slowlog_max_len": config.get("slowlog-max-len"),
            "databases": config.get("databases"),
            "maxclients": config.get("maxclients"),
            "port": config.get("port"),
            "bind": config.get("bind"),
            "protected_mode": config.get("protected-mode"),
        }

        if include_raw:
            metrics["raw_config"] = config

        return metrics

    except Exception as e:
        return {"error": str(e)}


async def _capture_keyspace_metrics(
    client: redis.Redis, include_raw: bool = True
) -> Dict[str, Any]:
    """Capture raw keyspace metrics."""
    try:
        info = await client.info("keyspace")

        keyspace_data = {}
        for db_key, db_info in info.items():
            if db_key.startswith("db"):
                if isinstance(db_info, dict):
                    keyspace_data[db_key] = db_info
                else:
                    # Parse db info string
                    db_stats = {}
                    for stat in db_info.split(","):
                        key, value = stat.split("=")
                        db_stats[key] = int(value)
                    keyspace_data[db_key] = db_stats

        metrics = {
            "databases": keyspace_data,
        }

        if include_raw:
            metrics["raw_keyspace_info"] = info

        return metrics

    except Exception as e:
        return {"error": str(e)}


async def _capture_replication_metrics(
    client: redis.Redis, include_raw: bool = True
) -> Dict[str, Any]:
    """Capture raw replication metrics."""
    try:
        info = await client.info("replication")

        metrics = {
            "role": info.get("role"),
            "connected_slaves": info.get("connected_slaves", 0),
            "master_replid": info.get("master_replid"),
            "master_repl_offset": info.get("master_repl_offset"),
            "repl_backlog_active": info.get("repl_backlog_active"),
            "repl_backlog_size": info.get("repl_backlog_size"),
            "master_host": info.get("master_host"),
            "master_port": info.get("master_port"),
            "master_link_status": info.get("master_link_status"),
            "master_last_io_seconds_ago": info.get("master_last_io_seconds_ago"),
            "master_sync_in_progress": info.get("master_sync_in_progress"),
            "slave_repl_offset": info.get("slave_repl_offset"),
        }

        if include_raw:
            metrics["raw_replication_info"] = info

        return metrics

    except Exception as e:
        return {"error": str(e)}


async def _capture_persistence_metrics(
    client: redis.Redis, include_raw: bool = True
) -> Dict[str, Any]:
    """Capture raw persistence metrics."""
    try:
        info = await client.info("persistence")

        metrics = {
            "loading": info.get("loading", 0),
            "rdb_changes_since_last_save": info.get("rdb_changes_since_last_save", 0),
            "rdb_bgsave_in_progress": info.get("rdb_bgsave_in_progress", 0),
            "rdb_last_save_time": info.get("rdb_last_save_time"),
            "rdb_last_bgsave_status": info.get("rdb_last_bgsave_status"),
            "rdb_last_bgsave_time_sec": info.get("rdb_last_bgsave_time_sec"),
            "aof_enabled": info.get("aof_enabled", 0),
            "aof_rewrite_in_progress": info.get("aof_rewrite_in_progress", 0),
            "aof_last_rewrite_time_sec": info.get("aof_last_rewrite_time_sec"),
            "aof_last_bgrewrite_status": info.get("aof_last_bgrewrite_status"),
            "aof_current_size": info.get("aof_current_size"),
            "aof_base_size": info.get("aof_base_size"),
        }

        if include_raw:
            metrics["raw_persistence_info"] = info

        return metrics

    except Exception as e:
        return {"error": str(e)}


async def _capture_cpu_metrics(client: redis.Redis, include_raw: bool = True) -> Dict[str, Any]:
    """Capture raw CPU metrics."""
    try:
        info = await client.info("cpu")

        metrics = {
            "used_cpu_sys": info.get("used_cpu_sys", 0.0),
            "used_cpu_user": info.get("used_cpu_user", 0.0),
            "used_cpu_sys_children": info.get("used_cpu_sys_children", 0.0),
            "used_cpu_user_children": info.get("used_cpu_user_children", 0.0),
            "used_cpu_sys_main_thread": info.get("used_cpu_sys_main_thread", 0.0),
            "used_cpu_user_main_thread": info.get("used_cpu_user_main_thread", 0.0),
        }

        if include_raw:
            metrics["raw_cpu_info"] = info

        return metrics

    except Exception as e:
        return {"error": str(e)}


async def _capture_client_list(client: redis.Redis) -> Dict[str, Any]:
    """Capture detailed client connection list for analysis."""
    try:
        clients_list = await client.client_list()

        # Parse and analyze client connections
        active_clients = []
        idle_clients = []
        blocked_clients = []

        for client_info in clients_list:
            client_data = {
                "id": client_info.get("id"),
                "addr": client_info.get("addr"),
                "name": client_info.get("name", ""),
                "age": client_info.get("age", 0),
                "idle": client_info.get("idle", 0),
                "flags": client_info.get("flags", ""),
                "db": client_info.get("db", 0),
                "sub": client_info.get("sub", 0),
                "psub": client_info.get("psub", 0),
                "multi": client_info.get("multi", -1),
                "qbuf": client_info.get("qbuf", 0),
                "qbuf_free": client_info.get("qbuf-free", 0),
                "obl": client_info.get("obl", 0),
                "oll": client_info.get("oll", 0),
                "omem": client_info.get("omem", 0),
                "cmd": client_info.get("cmd", ""),
            }

            # Categorize clients
            if "b" in client_info.get("flags", ""):
                blocked_clients.append(client_data)
            elif client_info.get("idle", 0) > 300:  # Idle for more than 5 minutes
                idle_clients.append(client_data)
            else:
                active_clients.append(client_data)

        return {
            "total_clients": len(clients_list),
            "active_clients": len(active_clients),
            "idle_clients": len(idle_clients),
            "blocked_clients": len(blocked_clients),
            "client_details": {
                "active": active_clients[:10],  # Limit to first 10 for brevity
                "idle": idle_clients[:5],       # Limit to first 5 for brevity
                "blocked": blocked_clients,     # Show all blocked clients
            },
            "raw_client_list": clients_list,  # Full raw data for agent analysis
        }

    except Exception as e:
        return {"error": str(e)}

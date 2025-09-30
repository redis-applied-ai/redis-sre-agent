"""Redis instance type detection utilities.

This module provides functions to detect the type of Redis instance
(OSS single node, OSS cluster, Redis Enterprise, Redis Cloud) based
on connection information and server responses.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse

import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError, ResponseError

logger = logging.getLogger(__name__)


class RedisInstanceType:
    """Constants for Redis instance types."""

    OSS_SINGLE = "oss_single"
    OSS_CLUSTER = "oss_cluster"
    REDIS_ENTERPRISE = "redis_enterprise"
    REDIS_CLOUD = "redis_cloud"
    UNKNOWN = "unknown"


async def detect_redis_instance_type(
    connection_url: str, timeout: float = 5.0
) -> Tuple[str, Dict[str, Any]]:
    """
    Detect the type of Redis instance based on connection and server information.

    Args:
        connection_url: Redis connection URL
        timeout: Connection timeout in seconds

    Returns:
        Tuple of (instance_type, detection_info)

    Detection Logic:
    1. Check connection URL patterns (cloud providers, enterprise ports)
    2. Connect and run INFO command to get server information
    3. Check for Enterprise-specific features and modules
    4. Check for cluster mode
    5. Analyze server version and build information
    """
    detection_info = {
        "connection_successful": False,
        "server_info": {},
        "cluster_info": {},
        "modules": [],
        "enterprise_features": [],
        "detection_method": "unknown",
        "confidence": "low",
    }

    try:
        # Parse connection URL for initial hints
        parsed_url = urlparse(connection_url)
        hostname = parsed_url.hostname or "localhost"
        port = parsed_url.port or 6379

        # Check URL patterns for cloud providers
        if "redis.cloud" in hostname or "redislabs.com" in hostname:
            detection_info["detection_method"] = "hostname_pattern"
            detection_info["confidence"] = "high"
            return RedisInstanceType.REDIS_CLOUD, detection_info

        if "cache.amazonaws.com" in hostname:
            detection_info["detection_method"] = "hostname_pattern"
            detection_info["confidence"] = "high"
            return RedisInstanceType.REDIS_CLOUD, detection_info

        # Check for common Enterprise ports
        enterprise_ports = [12000, 12001, 12002, 12003, 12004, 12005]
        if port in enterprise_ports:
            detection_info["detection_method"] = "port_pattern"
            detection_info["confidence"] = "medium"
            # Continue with connection to confirm

        # Connect to Redis and gather information
        redis_client = redis.from_url(
            connection_url,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
            retry_on_timeout=False,
        )

        try:
            # Test basic connection
            await redis_client.ping()
            detection_info["connection_successful"] = True

            # Get server information
            info = await redis_client.info()
            detection_info["server_info"] = {
                "redis_version": info.get("redis_version", "unknown"),
                "redis_mode": info.get("redis_mode", "standalone"),
                "os": info.get("os", "unknown"),
                "arch_bits": info.get("arch_bits", "unknown"),
                "multiplexing_api": info.get("multiplexing_api", "unknown"),
                "process_id": info.get("process_id", "unknown"),
                "tcp_port": info.get("tcp_port", port),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
            }

            # Check for Redis Enterprise indicators
            enterprise_indicators = []

            # Check server section for Enterprise markers
            server_info = info.get("server", {}) if isinstance(info.get("server"), dict) else {}

            # Enterprise often has specific version patterns or build info
            redis_version = info.get("redis_version", "")
            if "enterprise" in redis_version.lower():
                enterprise_indicators.append("version_string")

            # Check for Enterprise-specific INFO fields
            if "rlec_version" in info:
                enterprise_indicators.append("rlec_version_field")
            if "enterprise_version" in info:
                enterprise_indicators.append("enterprise_version_field")

            # Check for modules (Enterprise often has modules loaded)
            try:
                modules_info = await redis_client.execute_command("MODULE", "LIST")
                if modules_info:
                    detection_info["modules"] = [
                        module[1].decode() if isinstance(module[1], bytes) else str(module[1])
                        for module in modules_info
                        if len(module) > 1
                    ]
                    if detection_info["modules"]:
                        enterprise_indicators.append("modules_loaded")
            except (ResponseError, ConnectionError):
                # MODULE command might not be available
                pass

            # Check for cluster mode
            try:
                cluster_info = await redis_client.execute_command("CLUSTER", "INFO")
                if cluster_info:
                    detection_info["cluster_info"] = {"raw": cluster_info}
                    cluster_state = "unknown"
                    if isinstance(cluster_info, (str, bytes)):
                        cluster_str = (
                            cluster_info.decode()
                            if isinstance(cluster_info, bytes)
                            else cluster_info
                        )
                        if "cluster_state:ok" in cluster_str:
                            cluster_state = "ok"
                        elif "cluster_state:fail" in cluster_str:
                            cluster_state = "fail"
                    detection_info["cluster_info"]["state"] = cluster_state

                    if cluster_state == "ok":
                        # This is a cluster, but could be OSS cluster or Enterprise cluster
                        if enterprise_indicators:
                            detection_info["detection_method"] = "cluster_with_enterprise_features"
                            detection_info["confidence"] = "high"
                            detection_info["enterprise_features"] = enterprise_indicators
                            return RedisInstanceType.REDIS_ENTERPRISE, detection_info
                        else:
                            detection_info["detection_method"] = "cluster_info_command"
                            detection_info["confidence"] = "high"
                            return RedisInstanceType.OSS_CLUSTER, detection_info

            except (ResponseError, ConnectionError):
                # CLUSTER command might not be available or cluster mode disabled
                detection_info["cluster_info"] = {"available": False}

            # Determine instance type based on collected information
            if enterprise_indicators:
                detection_info["detection_method"] = "enterprise_features"
                detection_info["confidence"] = "high"
                detection_info["enterprise_features"] = enterprise_indicators
                return RedisInstanceType.REDIS_ENTERPRISE, detection_info

            # Check if this looks like a cloud service based on other indicators
            if (
                info.get("tcp_port") != 6379
                and info.get("tcp_port", 0) > 10000
                and "aws" in info.get("os", "").lower()
            ):
                detection_info["detection_method"] = "cloud_indicators"
                detection_info["confidence"] = "medium"
                return RedisInstanceType.REDIS_CLOUD, detection_info

            # Default to OSS single node
            detection_info["detection_method"] = "default_oss_single"
            detection_info["confidence"] = "medium"
            return RedisInstanceType.OSS_SINGLE, detection_info

        finally:
            await redis_client.aclose()

    except (ConnectionError, TimeoutError) as e:
        detection_info["connection_error"] = str(e)
        detection_info["detection_method"] = "connection_failed"
        logger.warning(f"Failed to connect to Redis at {connection_url}: {e}")
        return RedisInstanceType.UNKNOWN, detection_info

    except Exception as e:
        detection_info["error"] = str(e)
        detection_info["detection_method"] = "error"
        logger.error(f"Error detecting Redis instance type for {connection_url}: {e}")
        return RedisInstanceType.UNKNOWN, detection_info


async def get_redis_enterprise_info(connection_url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """
    Get detailed information specific to Redis Enterprise instances.

    Args:
        connection_url: Redis connection URL
        timeout: Connection timeout in seconds

    Returns:
        Dictionary with Enterprise-specific information
    """
    enterprise_info = {
        "is_enterprise": False,
        "cluster_info": {},
        "modules": [],
        "memory_info": {},
        "replication_info": {},
        "persistence_info": {},
    }

    try:
        redis_client = redis.from_url(
            connection_url,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
            retry_on_timeout=False,
        )

        try:
            # Get comprehensive info
            info = await redis_client.info("all")

            # Extract Enterprise-specific sections
            if "rlec_version" in info or "enterprise" in info.get("redis_version", "").lower():
                enterprise_info["is_enterprise"] = True

            # Memory information
            enterprise_info["memory_info"] = {
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "used_memory_rss": info.get("used_memory_rss", 0),
                "used_memory_peak": info.get("used_memory_peak", 0),
                "maxmemory": info.get("maxmemory", 0),
                "maxmemory_human": info.get("maxmemory_human", "0B"),
                "maxmemory_policy": info.get("maxmemory_policy", "noeviction"),
            }

            # Replication information
            enterprise_info["replication_info"] = {
                "role": info.get("role", "unknown"),
                "connected_slaves": info.get("connected_slaves", 0),
                "master_repl_offset": info.get("master_repl_offset", 0),
                "repl_backlog_active": info.get("repl_backlog_active", 0),
            }

            # Persistence information
            enterprise_info["persistence_info"] = {
                "rdb_last_save_time": info.get("rdb_last_save_time", 0),
                "rdb_changes_since_last_save": info.get("rdb_changes_since_last_save", 0),
                "aof_enabled": info.get("aof_enabled", 0),
                "aof_rewrite_in_progress": info.get("aof_rewrite_in_progress", 0),
                "aof_last_rewrite_time_sec": info.get("aof_last_rewrite_time_sec", -1),
            }

            # Get modules information
            try:
                modules_info = await redis_client.execute_command("MODULE", "LIST")
                if modules_info:
                    enterprise_info["modules"] = [
                        {
                            "name": module[1].decode()
                            if isinstance(module[1], bytes)
                            else str(module[1]),
                            "version": module[3] if len(module) > 3 else "unknown",
                        }
                        for module in modules_info
                        if len(module) > 1
                    ]
            except (ResponseError, ConnectionError):
                pass

            # Get cluster information if available
            try:
                cluster_info = await redis_client.execute_command("CLUSTER", "INFO")
                if cluster_info:
                    enterprise_info["cluster_info"]["raw"] = cluster_info

                cluster_nodes = await redis_client.execute_command("CLUSTER", "NODES")
                if cluster_nodes:
                    enterprise_info["cluster_info"]["nodes"] = cluster_nodes

            except (ResponseError, ConnectionError):
                enterprise_info["cluster_info"]["available"] = False

        finally:
            await redis_client.aclose()

    except Exception as e:
        enterprise_info["error"] = str(e)
        logger.error(f"Error getting Redis Enterprise info for {connection_url}: {e}")

    return enterprise_info

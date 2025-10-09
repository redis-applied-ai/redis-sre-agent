"""Redis Enterprise cluster management tools.

This module provides tools for the agent to check Redis Enterprise cluster status
using rladmin commands. The tools execute commands safely and return structured data.
"""

import logging
import subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def get_redis_enterprise_cluster_status(
    container_name: str = "redis-enterprise-node1",
) -> Dict[str, Any]:
    """Get Redis Enterprise cluster status using rladmin.

    This tool executes 'rladmin status' to get comprehensive cluster information
    including nodes, databases, and shards.

    Args:
        container_name: Docker container name for Redis Enterprise node

    Returns:
        Dict containing cluster status information

    Example:
        status = await get_redis_enterprise_cluster_status()
        # Returns: {
        #   "success": True,
        #   "cluster_status": "...",
        #   "nodes": [...],
        #   "databases": [...],
        #   ...
        # }
    """
    try:
        logger.info(f"Getting Redis Enterprise cluster status from {container_name}")

        # Execute rladmin status command
        result = subprocess.run(
            ["docker", "exec", container_name, "rladmin", "status"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(f"rladmin status failed: {result.stderr}")
            return {
                "success": False,
                "error": f"Command failed: {result.stderr}",
                "container": container_name,
            }

        output = result.stdout

        return {
            "success": True,
            "container": container_name,
            "raw_output": output,
            "summary": _parse_cluster_status(output),
        }

    except subprocess.TimeoutExpired:
        logger.error("rladmin status command timed out")
        return {
            "success": False,
            "error": "Command timed out after 30 seconds",
            "container": container_name,
        }
    except FileNotFoundError:
        logger.error("Docker command not found")
        return {
            "success": False,
            "error": "Docker command not found. Is Docker installed and running?",
            "container": container_name,
        }
    except Exception as e:
        logger.error(f"Error getting cluster status: {e}")
        return {
            "success": False,
            "error": str(e),
            "container": container_name,
        }


async def get_redis_enterprise_node_status(
    container_name: str = "redis-enterprise-node1",
    node_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Get Redis Enterprise node status using rladmin.

    This tool executes 'rladmin status nodes' to get detailed node information.

    Args:
        container_name: Docker container name for Redis Enterprise node
        node_id: Optional specific node ID to get info for

    Returns:
        Dict containing node status information

    Example:
        # Get all nodes
        nodes = await get_redis_enterprise_node_status()

        # Get specific node
        node = await get_redis_enterprise_node_status(node_id=2)
    """
    try:
        logger.info(f"Getting Redis Enterprise node status from {container_name}")

        # Build command
        cmd = ["docker", "exec", container_name, "rladmin", "status", "nodes"]

        # Execute command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(f"rladmin status nodes failed: {result.stderr}")
            return {
                "success": False,
                "error": f"Command failed: {result.stderr}",
                "container": container_name,
            }

        output = result.stdout

        # If specific node requested, also get detailed info
        node_detail = None
        if node_id is not None:
            detail_result = subprocess.run(
                ["docker", "exec", container_name, "rladmin", "info", "node", str(node_id)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if detail_result.returncode == 0:
                node_detail = detail_result.stdout

        return {
            "success": True,
            "container": container_name,
            "node_id": node_id,
            "raw_output": output,
            "node_detail": node_detail,
            "summary": _parse_node_status(output),
        }

    except subprocess.TimeoutExpired:
        logger.error("rladmin status nodes command timed out")
        return {
            "success": False,
            "error": "Command timed out after 30 seconds",
            "container": container_name,
        }
    except Exception as e:
        logger.error(f"Error getting node status: {e}")
        return {
            "success": False,
            "error": str(e),
            "container": container_name,
        }


async def get_redis_enterprise_database_status(
    container_name: str = "redis-enterprise-node1",
    database_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Get Redis Enterprise database status using rladmin.

    This tool executes 'rladmin status databases' to get database information.

    Args:
        container_name: Docker container name for Redis Enterprise node
        database_name: Optional specific database name to get info for

    Returns:
        Dict containing database status information

    Example:
        # Get all databases
        dbs = await get_redis_enterprise_database_status()

        # Get specific database
        db = await get_redis_enterprise_database_status(database_name="test-db")
    """
    try:
        logger.info(f"Getting Redis Enterprise database status from {container_name}")

        # Execute command
        result = subprocess.run(
            ["docker", "exec", container_name, "rladmin", "status", "databases"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(f"rladmin status databases failed: {result.stderr}")
            return {
                "success": False,
                "error": f"Command failed: {result.stderr}",
                "container": container_name,
            }

        output = result.stdout

        # If specific database requested, also get detailed info
        db_detail = None
        if database_name is not None:
            detail_result = subprocess.run(
                ["docker", "exec", container_name, "rladmin", "info", "db", database_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if detail_result.returncode == 0:
                db_detail = detail_result.stdout

        return {
            "success": True,
            "container": container_name,
            "database_name": database_name,
            "raw_output": output,
            "database_detail": db_detail,
            "summary": _parse_database_status(output),
        }

    except subprocess.TimeoutExpired:
        logger.error("rladmin status databases command timed out")
        return {
            "success": False,
            "error": "Command timed out after 30 seconds",
            "container": container_name,
        }
    except Exception as e:
        logger.error(f"Error getting database status: {e}")
        return {
            "success": False,
            "error": str(e),
            "container": container_name,
        }


def _parse_cluster_status(output: str) -> Dict[str, Any]:
    """Parse rladmin status output to extract key information."""
    summary = {
        "has_cluster": False,
        "cluster_ok": False,
        "node_count": 0,
        "database_count": 0,
    }

    try:
        lines = output.split("\n")
        for line in lines:
            if "CLUSTER" in line.upper():
                summary["has_cluster"] = True
                if "OK" in line.upper():
                    summary["cluster_ok"] = True
            if "node:" in line.lower():
                summary["node_count"] += 1
            if "db:" in line.lower() or "database:" in line.lower():
                summary["database_count"] += 1
    except Exception as e:
        logger.warning(f"Error parsing cluster status: {e}")

    return summary


def _parse_node_status(output: str) -> Dict[str, Any]:
    """Parse rladmin status nodes output to extract key information.

    Maintenance mode is indicated by SHARDS showing 0/0, not by STATUS field.
    The STATUS field can still show "OK" for a node in maintenance mode.
    """
    summary = {
        "nodes": [],
        "maintenance_mode_nodes": [],
        "total_nodes": 0,
    }

    try:
        lines = output.split("\n")
        for line in lines:
            # Look for lines with node: prefix
            if "node:" in line.lower() and not line.strip().startswith("#"):
                summary["total_nodes"] += 1

                # Parse node information
                parts = line.split()
                node_id = None
                shards = None

                for i, part in enumerate(parts):
                    if part.startswith("node:") or part.startswith("*node:"):
                        # Extract node ID (remove * if present)
                        node_id = part.replace("*", "").split(":")[1]

                    # Look for shard count (format: X/Y where X is current, Y is max)
                    if "/" in part and i > 0:
                        try:
                            # Check if this looks like a shard count
                            current, max_shards = part.split("/")
                            if current.isdigit() and max_shards.isdigit():
                                shards = part
                                # If shards is 0/0, node is in maintenance mode
                                if part == "0/0":
                                    if node_id:
                                        summary["maintenance_mode_nodes"].append(node_id)
                                        logger.info(
                                            f"Node {node_id} detected in maintenance mode (shards: 0/0)"
                                        )
                        except ValueError:
                            pass

                if node_id:
                    summary["nodes"].append(
                        {"node_id": node_id, "shards": shards, "in_maintenance": shards == "0/0"}
                    )

    except Exception as e:
        logger.warning(f"Error parsing node status: {e}")

    return summary


def _parse_database_status(output: str) -> Dict[str, Any]:
    """Parse rladmin status databases output to extract key information."""
    summary = {
        "databases": [],
        "total_databases": 0,
    }

    try:
        lines = output.split("\n")
        for line in lines:
            if "db:" in line.lower() or "database:" in line.lower():
                summary["total_databases"] += 1
    except Exception as e:
        logger.warning(f"Error parsing database status: {e}")

    return summary

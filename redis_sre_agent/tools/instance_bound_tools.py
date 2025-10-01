"""Instance-bound tool factories.

When diagnosing a specific Redis instance, tools should be pre-configured
with that instance's connection details. This prevents the LLM from accidentally
using wrong parameters or connecting to the wrong instance.

Two modes:
1. Instance-bound: Tools are pre-configured with instance details (LLM can't override)
2. Unbound: Tools accept parameters from LLM (for exploratory queries)
"""

import logging
from typing import Any, Dict, Optional

from redis_sre_agent.api.instances import RedisInstance

logger = logging.getLogger(__name__)


def create_instance_bound_diagnostics_tool(instance: RedisInstance) -> Dict[str, Any]:
    """Create a diagnostics tool bound to a specific Redis instance.

    The LLM cannot override the redis_url - it's fixed to the instance.

    Args:
        instance: The Redis instance to bind to

    Returns:
        Tool definition with redis_url pre-configured
    """
    return {
        "type": "function",
        "function": {
            "name": "get_detailed_redis_diagnostics",
            "description": f"""Get comprehensive Redis diagnostics for {instance.name} ({instance.environment}).

This tool is PRE-CONFIGURED to connect to:
- Instance: {instance.name}
- URL: {instance.connection_url}
- Environment: {instance.environment}

You do NOT need to specify redis_url - it's already configured.
Just call this tool to get diagnostics for this specific instance.""",
            "parameters": {
                "type": "object",
                "properties": {
                    # No redis_url parameter - it's bound!
                    "include_slow_log": {
                        "type": "boolean",
                        "description": "Include slow query log analysis",
                        "default": True,
                    },
                    "include_client_list": {
                        "type": "boolean",
                        "description": "Include connected clients analysis",
                        "default": False,
                    },
                },
                "required": [],
            },
            # Store the bound redis_url in metadata
            "_bound_redis_url": instance.connection_url,
            "_bound_instance_id": instance.id,
        },
    }


def create_unbound_diagnostics_tool() -> Dict[str, Any]:
    """Create a diagnostics tool that accepts redis_url from LLM.

    Use this when no specific instance is selected.

    Returns:
        Tool definition that requires redis_url parameter
    """
    return {
        "type": "function",
        "function": {
            "name": "get_detailed_redis_diagnostics",
            "description": """Get comprehensive Redis diagnostics.

IMPORTANT: You must specify which Redis instance to connect to via redis_url parameter.

Example redis_url formats:
- redis://localhost:6379/0
- redis://:password@host:port/db
- redis://user:password@host:port/db""",
            "parameters": {
                "type": "object",
                "properties": {
                    "redis_url": {
                        "type": "string",
                        "description": "Redis connection URL (required)",
                    },
                    "include_slow_log": {
                        "type": "boolean",
                        "description": "Include slow query log analysis",
                        "default": True,
                    },
                    "include_client_list": {
                        "type": "boolean",
                        "description": "Include connected clients analysis",
                        "default": False,
                    },
                },
                "required": ["redis_url"],
            },
        },
    }


def create_instance_bound_metrics_tool(instance: RedisInstance) -> Dict[str, Any]:
    """Create a metrics query tool bound to a specific Redis instance.

    The instance identifier is pre-configured for Prometheus queries.

    Args:
        instance: The Redis instance to bind to

    Returns:
        Tool definition with instance context pre-configured
    """
    # Parse host from connection URL for Prometheus queries
    from redis_sre_agent.agent.langgraph_agent import _parse_redis_connection_url

    host, port = _parse_redis_connection_url(instance.connection_url)

    return {
        "type": "function",
        "function": {
            "name": "query_instance_metrics",
            "description": f"""Query metrics for {instance.name} ({instance.environment}).

This tool is PRE-CONFIGURED for:
- Instance: {instance.name}
- Host: {host}
- Port: {port}
- Environment: {instance.environment}

You do NOT need to specify instance details - just provide the metric names you want to query.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of metric names to query (e.g., ['used_memory', 'connected_clients'])",
                    },
                    "time_range_minutes": {
                        "type": "integer",
                        "description": "Time range in minutes (default: 60)",
                        "default": 60,
                    },
                },
                "required": ["metric_names"],
            },
            # Store bound instance context
            "_bound_instance_host": host,
            "_bound_instance_port": port,
            "_bound_instance_id": instance.id,
        },
    }


def create_unbound_metrics_tool() -> Dict[str, Any]:
    """Create a metrics query tool that accepts instance details from LLM.

    Use this when no specific instance is selected.

    Returns:
        Tool definition that requires instance parameters
    """
    return {
        "type": "function",
        "function": {
            "name": "query_instance_metrics",
            "description": """Query metrics for a Redis instance.

IMPORTANT: You must specify which instance to query via instance_host parameter.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of metric names to query",
                    },
                    "instance_host": {
                        "type": "string",
                        "description": "Instance hostname or IP (required)",
                    },
                    "instance_port": {
                        "type": "integer",
                        "description": "Instance port (default: 6379)",
                        "default": 6379,
                    },
                    "time_range_minutes": {
                        "type": "integer",
                        "description": "Time range in minutes (default: 60)",
                        "default": 60,
                    },
                },
                "required": ["metric_names", "instance_host"],
            },
        },
    }


def get_tools_for_instance(instance: Optional[RedisInstance]) -> list[Dict[str, Any]]:
    """Get tool definitions appropriate for the given instance context.

    If instance is provided: Returns instance-bound tools (LLM can't override)
    If instance is None: Returns unbound tools (LLM must provide parameters)

    Args:
        instance: The Redis instance to bind tools to, or None for unbound tools

    Returns:
        List of tool definitions
    """
    if instance:
        logger.info(f"Creating instance-bound tools for {instance.name} ({instance.id})")
        return [
            create_instance_bound_diagnostics_tool(instance),
            create_instance_bound_metrics_tool(instance),
        ]
    else:
        logger.info("Creating unbound tools (no specific instance)")
        return [
            create_unbound_diagnostics_tool(),
            create_unbound_metrics_tool(),
        ]

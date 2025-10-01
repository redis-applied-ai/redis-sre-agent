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


def create_instance_bound_metrics_tool(instance: RedisInstance) -> Dict[str, Any]:
    """Create a metrics query tool bound to a specific Redis instance.

    The instance identifier is pre-configured for metric queries.

    Args:
        instance: The Redis instance to bind to

    Returns:
        Tool definition with instance context pre-configured
    """
    # Parse host from connection URL
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
- Redis URL: {instance.connection_url}

You do NOT need to specify provider_name or labels - they are already configured.
Just provide the metric_name you want to query.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_name": {
                        "type": "string",
                        "description": "Name of the metric to query (e.g., 'used_memory', 'connected_clients')",
                    },
                    "time_range_hours": {
                        "type": "number",
                        "description": "Time range in hours (default: 1)",
                        "default": 1,
                    },
                },
                "required": ["metric_name"],
            },
            # Store bound instance context
            "_bound_redis_url": instance.connection_url,
            "_bound_provider_name": "redis",  # Use Redis provider for this instance
            "_bound_instance_id": instance.id,
        },
    }


def create_unbound_metrics_tool() -> Dict[str, Any]:
    """Create a metrics query tool that accepts parameters from LLM.

    Use this when no specific instance is selected.

    Returns:
        Tool definition that requires metric parameters
    """
    return {
        "type": "function",
        "function": {
            "name": "query_instance_metrics",
            "description": """Query metrics from Redis instances or monitoring systems.

IMPORTANT: You must specify which metric to query and optionally which provider.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_name": {
                        "type": "string",
                        "description": "Name of the metric to query (e.g., 'used_memory', 'connected_clients')",
                    },
                    "provider_name": {
                        "type": "string",
                        "description": "Optional specific provider to use (e.g., 'redis', 'prometheus')",
                    },
                    "labels": {
                        "type": "object",
                        "description": "Optional label filters for the metric query",
                    },
                    "time_range_hours": {
                        "type": "number",
                        "description": "Time range in hours (default: 1)",
                        "default": 1,
                    },
                },
                "required": ["metric_name"],
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
            create_instance_bound_metrics_tool(instance),
        ]
    else:
        logger.info("Creating unbound tools (no specific instance)")
        return [
            create_unbound_metrics_tool(),
        ]

"""Protocol-based agent tools configuration.

This module provides the tool definitions for the LangGraph agent using
the Protocol-based provider system. It replaces the hardcoded tools with
dynamic tools that discover and use registered providers.
"""

import logging
from typing import Any, Dict, List

from .dynamic_tools import (
    create_incident_ticket,
    list_available_metrics,
    query_instance_metrics,
    search_logs,
    search_related_repositories,
)
from .registry import get_global_registry

logger = logging.getLogger(__name__)


def get_protocol_based_tools() -> List[Dict[str, Any]]:
    """Get tool definitions for the Protocol-based SRE tools.
    
    Returns:
        List of tool definitions for LangGraph agent
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "query_instance_metrics",
                "description": "Query metrics from Redis instances or monitoring systems. Supports both current values and historical time-series data. Can query specific providers or search across all available metrics providers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric_name": {
                            "type": "string",
                            "description": "Name of the metric to query (e.g., 'used_memory', 'connected_clients', 'redis_memory_used_bytes'). Use list_available_metrics to see all available metrics.",
                        },
                        "provider_name": {
                            "type": "string",
                            "description": "Optional specific provider to use (e.g., 'redis', 'prometheus', 'aws'). If not specified, queries all available providers.",
                        },
                        "labels": {
                            "type": "object",
                            "description": "Optional label filters for the metric query (e.g., {'database': '0', 'instance': 'prod-redis-1'})",
                        },
                        "time_range_hours": {
                            "type": "number",
                            "description": "Optional time range in hours for historical data. Only works with providers that support time queries (like Prometheus).",
                        },
                    },
                    "required": ["metric_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_available_metrics",
                "description": "List all available metrics from registered providers. Use this to discover what metrics can be queried before using query_instance_metrics.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "provider_name": {
                            "type": "string",
                            "description": "Optional specific provider to query (e.g., 'redis', 'prometheus'). If not specified, lists metrics from all providers.",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_logs",
                "description": "Search application and system logs across available log providers (CloudWatch, Elasticsearch, etc.). Useful for finding error patterns, performance issues, and operational events.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for logs (e.g., 'ERROR', 'redis connection', 'timeout', 'memory'). Syntax depends on the log provider.",
                        },
                        "time_range_hours": {
                            "type": "number",
                            "description": "Time range in hours to search (default: 1.0)",
                            "default": 1.0,
                        },
                        "provider_name": {
                            "type": "string",
                            "description": "Optional specific log provider to use (e.g., 'aws', 'elasticsearch')",
                        },
                        "log_groups": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of log groups/streams to search",
                        },
                        "level_filter": {
                            "type": "string",
                            "description": "Optional log level filter (ERROR, WARN, INFO, DEBUG)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of log entries to return (default: 100)",
                            "default": 100,
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_incident_ticket",
                "description": "Create an incident ticket in the configured ticketing system (GitHub Issues, Jira, etc.). Use this to track and escalate Redis issues that require human intervention.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Clear, concise title for the incident ticket",
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description of the incident including symptoms, impact, and any diagnostic information gathered",
                        },
                        "provider_name": {
                            "type": "string",
                            "description": "Optional specific ticket provider to use (e.g., 'github', 'jira')",
                        },
                        "labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional labels/tags for the ticket (e.g., ['redis', 'production', 'memory-issue'])",
                        },
                        "assignee": {
                            "type": "string",
                            "description": "Optional username to assign the ticket to",
                        },
                        "priority": {
                            "type": "string",
                            "description": "Optional priority level (low, medium, high, critical)",
                        },
                    },
                    "required": ["title", "description"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_related_repositories",
                "description": "Search code repositories to find applications that might be using the Redis instance. Helps identify which services could be affected by Redis issues and provides context for troubleshooting.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for code (e.g., 'redis', 'cache', specific Redis commands, connection strings, error messages)",
                        },
                        "provider_name": {
                            "type": "string",
                            "description": "Optional specific repository provider to use (e.g., 'github', 'gitlab')",
                        },
                        "file_extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional file extension filters (e.g., ['py', 'js', 'java', 'go'])",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of code results to return (default: 20)",
                            "default": 20,
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_provider_status",
                "description": "Get the status of all registered SRE tool providers. Use this to understand what capabilities are available and check provider health.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
    ]


async def get_provider_status() -> Dict[str, Any]:
    """Get status of all registered providers.
    
    Returns:
        Provider status and health information
    """
    try:
        registry = get_global_registry()
        
        # Get registry status
        registry_status = registry.get_registry_status()
        
        # Get health checks for all providers
        health_results = await registry.health_check_all()
        
        return {
            "registry_status": registry_status,
            "provider_health": health_results,
            "summary": {
                "total_providers": registry_status["total_providers"],
                "healthy_providers": sum(
                    1 for result in health_results.values()
                    if result.get("status") == "healthy"
                ),
                "capabilities_available": registry_status["capabilities_available"]
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting provider status: {e}")
        return {"error": str(e)}


# Tool function mapping for the agent
PROTOCOL_TOOL_FUNCTIONS = {
    "query_instance_metrics": query_instance_metrics,
    "list_available_metrics": list_available_metrics,
    "search_logs": search_logs,
    "create_incident_ticket": create_incident_ticket,
    "search_related_repositories": search_related_repositories,
    "get_provider_status": get_provider_status,
}

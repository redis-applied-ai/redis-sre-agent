"""Protocol-based agent tools configuration.

This module provides the tool definitions for the LangGraph agent using
the Protocol-based provider system. It replaces the hardcoded tools with
dynamic tools that discover and use registered providers.
"""

import logging
from typing import Any, Dict, List

from .dynamic_tools import (
    create_incident_ticket,
    get_redis_diagnostics,
    list_available_metrics,
    query_instance_metrics,
    query_redis_enterprise_cluster,
    query_redis_enterprise_databases,
    query_redis_enterprise_nodes,
    sample_redis_keys,
    search_logs,
    search_related_repositories,
)

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
                "description": "Query metrics from Redis instances or monitoring systems (Prometheus, CloudWatch, etc.). When redis_url is provided, connects DIRECTLY to the Redis instance via Redis protocol to get current metrics from INFO command. Otherwise queries registered monitoring providers like Prometheus. Supports batch queries for efficiency. Use this for: 1) Quick metric checks from Redis INFO, 2) Querying Prometheus time-series data, 3) Getting metrics from multiple sources.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric_name": {
                            "type": "string",
                            "description": "Name of a single metric to query (e.g., 'used_memory', 'connected_clients'). For querying multiple metrics, use metric_names instead.",
                        },
                        "metric_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Array of metric names to query in batch (e.g., ['used_memory', 'connected_clients', 'total_commands_processed']). More efficient than multiple single queries.",
                        },
                        "redis_url": {
                            "type": "string",
                            "description": "Redis connection URL for instance-specific queries (e.g., 'redis://localhost:6379', 'redis://localhost:12000'). Use this to query a specific Redis instance. If not provided, uses registered providers.",
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
                    "required": [],
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
                "name": "query_redis_enterprise_cluster",
                "description": "Query Redis Enterprise cluster status using rladmin. Returns comprehensive cluster information including nodes, databases, and shards. Use this to check Redis Enterprise cluster health and overall state.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "container_name": {
                            "type": "string",
                            "description": "Docker container name for Redis Enterprise node (default: redis-enterprise-node1)",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_redis_enterprise_nodes",
                "description": "Query Redis Enterprise node status using rladmin. Returns detailed node information including maintenance mode status (indicated by SHARDS: 0/0), shard distribution, and node health. Use this to check if nodes are in maintenance mode or investigate node-specific issues.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "container_name": {
                            "type": "string",
                            "description": "Docker container name for Redis Enterprise node (default: redis-enterprise-node1)",
                        },
                        "node_id": {
                            "type": "integer",
                            "description": "Optional specific node ID to get detailed info for",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_redis_enterprise_databases",
                "description": "Query Redis Enterprise database status using rladmin. Returns database information including endpoints, memory usage, and replication status. Use this to check database health and configuration.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "container_name": {
                            "type": "string",
                            "description": "Docker container name for Redis Enterprise node (default: redis-enterprise-node1)",
                        },
                        "database_name": {
                            "type": "string",
                            "description": "Optional specific database name to get detailed info for",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_redis_diagnostics",
                "description": "Connect directly to a Redis instance and gather comprehensive diagnostic information via Redis INFO command and other Redis commands. Provides detailed instance-level data. IMPORTANT: Use sections='keyspace' to get database statistics (number of keys per database, keys with TTL, average TTL). Use this instead of telling the user to connect - you can get the data yourself! Available sections: memory (usage, fragmentation, RSS), performance (ops/sec, hit rate, command stats), clients (connections, blocked clients), slowlog (slow queries), configuration (maxmemory, eviction policy, maxmemory-samples), keyspace (keys per database, expires, avg_ttl), replication (master/slave status), persistence (RDB/AOF), cpu (usage stats).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "redis_url": {
                            "type": "string",
                            "description": "Redis connection URL (e.g., 'redis://localhost:6379', 'redis://localhost:12000' for Redis Enterprise)",
                        },
                        "sections": {
                            "type": "string",
                            "description": "Comma-separated list of diagnostic sections to capture, or 'all' for everything. To get keyspace info (number of keys, expires, TTL), use 'keyspace'. Options: memory, performance, clients, slowlog, configuration, keyspace, replication, persistence, cpu. Example: 'keyspace' or 'memory,keyspace,configuration' or 'all'",
                        },
                    },
                    "required": ["redis_url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sample_redis_keys",
                "description": "Sample keys from a Redis instance using SCAN command to understand key patterns and namespaces. IMPORTANT: Use this instead of telling the user to connect and check keys - you can sample keys yourself! Returns actual key names and analyzes patterns (e.g., 'user:*', 'session:*'). Use this when you need to: 1) Understand what types of keys exist, 2) Identify key naming patterns, 3) Investigate specific key namespaces, 4) Analyze key distribution.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "redis_url": {
                            "type": "string",
                            "description": "Redis connection URL (e.g., 'redis://localhost:6379', 'redis://localhost:12000')",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Key pattern to match using Redis glob-style patterns (default: '*' for all keys). Examples: 'user:*', 'session:*', 'cache:*', '*:metadata'",
                        },
                        "count": {
                            "type": "integer",
                            "description": "Maximum number of keys to sample (default: 100). Use smaller values for quick checks, larger for comprehensive analysis.",
                        },
                        "database": {
                            "type": "integer",
                            "description": "Database number to select (default: 0). Redis has databases 0-15 by default.",
                        },
                    },
                    "required": ["redis_url"],
                },
            },
        },
    ]


# get_provider_status removed - old registry system no longer used


# Tool function mapping for the agent
# NOTE: This is the old system - being phased out in favor of provider-based architecture
PROTOCOL_TOOL_FUNCTIONS = {
    "query_instance_metrics": query_instance_metrics,
    "list_available_metrics": list_available_metrics,
    "search_logs": search_logs,
    "create_incident_ticket": create_incident_ticket,
    "search_related_repositories": search_related_repositories,
    "query_redis_enterprise_cluster": query_redis_enterprise_cluster,
    "query_redis_enterprise_nodes": query_redis_enterprise_nodes,
    "query_redis_enterprise_databases": query_redis_enterprise_databases,
    "get_redis_diagnostics": get_redis_diagnostics,
    "sample_redis_keys": sample_redis_keys,
}

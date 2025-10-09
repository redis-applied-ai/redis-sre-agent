"""Dynamic SRE tools that use the Protocol-based provider system.

These tools replace the hardcoded tool implementations and dynamically
discover and use registered providers based on their capabilities.

NOTE: This module is being phased out in favor of the new DeploymentProviders
and ToolRegistry system. It's kept temporarily for compatibility.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .protocols import TimeRange

logger = logging.getLogger(__name__)


# Stub for old registry - being replaced by new system
def get_global_registry():
    """Stub for old registry system - returns None.

    This is being replaced by the new DeploymentProviders and ToolRegistry system.
    """
    logger.warning("get_global_registry() is deprecated and returns None")
    return None


# Redis Enterprise Tools


async def query_redis_enterprise_cluster(
    container_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Query Redis Enterprise cluster status.

    Creates a temporary Redis Enterprise provider and queries cluster status.

    Args:
        container_name: Docker container name (default: redis-enterprise-node1)

    Returns:
        Cluster status information
    """
    try:
        from .providers import create_redis_enterprise_provider

        # Create temporary provider
        provider = create_redis_enterprise_provider(
            container_name=container_name or "redis-enterprise-node1"
        )

        # Get cluster status
        result = await provider.get_cluster_status()

        return result

    except Exception as e:
        logger.error(f"Error querying Redis Enterprise cluster: {e}")
        return {"success": False, "error": str(e)}


async def query_redis_enterprise_nodes(
    container_name: Optional[str] = None,
    node_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Query Redis Enterprise node status.

    Creates a temporary Redis Enterprise provider and queries node status.

    Args:
        container_name: Docker container name (default: redis-enterprise-node1)
        node_id: Optional specific node ID to query

    Returns:
        Node status information
    """
    try:
        from .providers import create_redis_enterprise_provider

        # Create temporary provider
        provider = create_redis_enterprise_provider(
            container_name=container_name or "redis-enterprise-node1"
        )

        # Get node status
        result = await provider.get_node_status(node_id)

        return result

    except Exception as e:
        logger.error(f"Error querying Redis Enterprise nodes: {e}")
        return {"success": False, "error": str(e)}


async def query_redis_enterprise_databases(
    container_name: Optional[str] = None,
    database_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Query Redis Enterprise database status.

    Creates a temporary Redis Enterprise provider and queries database status.

    Args:
        container_name: Docker container name (default: redis-enterprise-node1)
        database_name: Optional specific database name to query

    Returns:
        Database status information
    """
    try:
        from .providers import create_redis_enterprise_provider

        # Create temporary provider
        provider = create_redis_enterprise_provider(
            container_name=container_name or "redis-enterprise-node1"
        )

        # Get database status
        result = await provider.get_database_status(database_name)

        return result

    except Exception as e:
        logger.error(f"Error querying Redis Enterprise databases: {e}")
        return {"success": False, "error": str(e)}


async def get_redis_diagnostics(
    redis_url: str,
    sections: Optional[str] = None,
) -> Dict[str, Any]:
    """Get detailed Redis diagnostics by connecting directly to the instance.

    This tool connects directly to a Redis instance via the Redis protocol
    and gathers comprehensive diagnostic information including memory usage,
    performance metrics, client connections, slow queries, configuration,
    and more. Use this when you need detailed instance-level information
    that may not be available in Prometheus or other monitoring systems.

    Args:
        redis_url: Redis connection URL (e.g., 'redis://localhost:6379', 'redis://localhost:12000')
        sections: Comma-separated list of sections to capture, or 'all' for everything.
                 Options: memory, performance, clients, slowlog, configuration,
                 keyspace, replication, persistence, cpu

    Returns:
        Comprehensive diagnostic data from the Redis instance
    """
    try:
        from .redis_diagnostics import capture_redis_diagnostics

        # Parse sections if provided
        sections_list = None
        if sections and sections != "all":
            sections_list = [s.strip() for s in sections.split(",") if s.strip()]

        result = await capture_redis_diagnostics(
            redis_url=redis_url,
            sections=sections_list,
            include_raw_data=True,
        )

        return result

    except Exception as e:
        logger.error(f"Error getting Redis diagnostics: {e}")
        return {"capture_status": "failed", "error": str(e)}


async def sample_redis_keys(
    redis_url: str,
    pattern: str = "*",
    count: int = 100,
    database: int = 0,
) -> Dict[str, Any]:
    """Sample keys from a Redis instance using SCAN command.

    This tool connects directly to Redis and samples keys matching a pattern.
    Use this to understand what types of keys exist, identify key patterns,
    or investigate specific key namespaces. IMPORTANT: Use this instead of
    telling the user to connect and check keys - you can do it yourself!

    Args:
        redis_url: Redis connection URL (e.g., 'redis://localhost:6379')
        pattern: Key pattern to match (default: '*' for all keys).
                Examples: 'user:*', 'session:*', 'cache:*'
        count: Maximum number of keys to sample (default: 100)
        database: Database number to select (default: 0)

    Returns:
        Dictionary with sampled keys and statistics
    """
    try:
        import redis.asyncio as redis

        # Connect to Redis
        client = redis.from_url(
            redis_url, decode_responses=True, socket_timeout=10, socket_connect_timeout=5
        )

        try:
            # Select database if not 0
            if database != 0:
                await client.select(database)

            # Sample keys using SCAN
            sampled_keys = []
            cursor = 0
            scan_count = min(count, 1000)  # Scan in batches

            while len(sampled_keys) < count:
                cursor, keys = await client.scan(cursor, match=pattern, count=scan_count)
                sampled_keys.extend(keys)

                if cursor == 0:  # Scan complete
                    break

            # Limit to requested count
            sampled_keys = sampled_keys[:count]

            # Analyze key patterns
            key_patterns = {}
            for key in sampled_keys:
                # Extract pattern (first part before colon)
                if ":" in key:
                    prefix = key.split(":")[0]
                    key_patterns[prefix] = key_patterns.get(prefix, 0) + 1
                else:
                    key_patterns["<no_prefix>"] = key_patterns.get("<no_prefix>", 0) + 1

            # Get total key count for this database
            info = await client.info("keyspace")
            db_key = f"db{database}"
            total_keys = 0
            if db_key in info:
                db_info = info[db_key]
                if isinstance(db_info, dict):
                    total_keys = db_info.get("keys", 0)
                else:
                    # Parse string format
                    for stat in db_info.split(","):
                        if stat.startswith("keys="):
                            total_keys = int(stat.split("=")[1])

            return {
                "success": True,
                "redis_url": redis_url,
                "database": database,
                "pattern": pattern,
                "total_keys_in_db": total_keys,
                "sampled_count": len(sampled_keys),
                "sampled_keys": sampled_keys,
                "key_patterns": key_patterns,
                "pattern_summary": [
                    {"prefix": prefix, "count": count}
                    for prefix, count in sorted(
                        key_patterns.items(), key=lambda x: x[1], reverse=True
                    )
                ],
            }

        finally:
            await client.aclose()

    except Exception as e:
        logger.error(f"Error sampling Redis keys: {e}")
        return {"success": False, "error": str(e)}


async def query_instance_metrics(
    metric_name: Optional[str] = None,
    metric_names: Optional[List[str]] = None,
    provider_name: Optional[str] = None,
    labels: Optional[Dict[str, str]] = None,
    time_range_hours: Optional[float] = None,
    redis_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Query instance metrics from available providers.

    Supports both single metric queries and batch queries for multiple metrics.

    Args:
        metric_name: Name of a single metric to query (deprecated, use metric_names)
        metric_names: List of metric names to query in batch
        provider_name: Optional specific provider to use
        labels: Optional label filters
        time_range_hours: Optional time range in hours for historical data
        redis_url: Optional Redis URL for instance-specific queries

    Returns:
        Metric query results
    """
    # Handle both single and batch queries
    if metric_names:
        metrics_to_query = metric_names
    elif metric_name:
        metrics_to_query = [metric_name]
    else:
        return {"error": "Either metric_name or metric_names must be provided"}
    try:
        registry = get_global_registry()

        # If redis_url is provided, create a temporary Redis provider for this query
        temp_provider = None
        if redis_url:
            logger.info(f"Creating temporary Redis provider for {redis_url}")
            from .providers import RedisCommandMetricsProvider

            temp_provider = RedisCommandMetricsProvider(redis_url)
            provider_name = "temp_redis"  # Use temp provider

        # Get metrics providers
        if temp_provider:
            # Use the temporary provider created for this specific redis_url
            providers = [temp_provider]
            logger.info(f"Using temporary Redis provider: {temp_provider.provider_name}")
        elif provider_name:
            provider_instance = registry.get_provider(provider_name)
            if not provider_instance:
                return {"error": f"Provider '{provider_name}' not found"}

            metrics_provider = await provider_instance.get_metrics_provider()
            if not metrics_provider:
                return {"error": f"Provider '{provider_name}' doesn't support metrics"}

            providers = [metrics_provider]
        else:
            providers = await registry.get_metrics_providers()

        if not providers:
            return {"error": "No metrics providers available"}

        results = []

        # Query each metric
        for metric in metrics_to_query:
            for provider in providers:
                try:
                    if time_range_hours and provider.supports_time_queries:
                        # Query time range
                        end_time = datetime.now()
                        start_time = end_time - timedelta(hours=time_range_hours)
                        time_range = TimeRange(start_time, end_time)

                        values = await provider.query_time_range(metric, time_range, labels)

                        result = {
                            "provider": provider.provider_name,
                            "metric_name": metric,
                            "time_range_hours": time_range_hours,
                            "values_count": len(values),
                            "values": [
                                {
                                    "timestamp": value.timestamp.isoformat(),
                                    "value": value.value,
                                    "labels": value.labels,
                                }
                                for value in values
                            ],
                        }
                    else:
                        # Query current value
                        value = await provider.get_current_value(metric, labels)

                        if value:
                            result = {
                                "provider": provider.provider_name,
                                "metric_name": metric,
                                "current_value": value.value,
                                "timestamp": value.timestamp.isoformat(),
                                "labels": value.labels,
                            }
                        else:
                            result = {
                                "provider": provider.provider_name,
                                "metric_name": metric,
                                "error": "Metric not found",
                            }

                    results.append(result)

                except Exception as e:
                    results.append(
                        {
                            "provider": provider.provider_name,
                            "metric_name": metric,
                            "error": str(e),
                        }
                    )

        # Return format depends on whether it was a batch query
        if len(metrics_to_query) == 1:
            return {
                "metric_name": metrics_to_query[0],
                "providers_queried": len(providers),
                "results": results,
            }
        else:
            return {
                "metrics_queried": metrics_to_query,
                "providers_queried": len(providers),
                "results": results,
            }

    except Exception as e:
        logger.error(f"Error querying metrics: {e}")
        return {"error": str(e)}


async def list_available_metrics(provider_name: Optional[str] = None) -> Dict[str, Any]:
    """List all available metrics from providers.

    Args:
        provider_name: Optional specific provider to query

    Returns:
        List of available metrics with descriptions
    """
    try:
        registry = get_global_registry()

        # Get metrics providers
        if provider_name:
            provider_instance = registry.get_provider(provider_name)
            if not provider_instance:
                return {"error": f"Provider '{provider_name}' not found"}

            metrics_provider = await provider_instance.get_metrics_provider()
            if not metrics_provider:
                return {"error": f"Provider '{provider_name}' doesn't support metrics"}

            providers = [metrics_provider]
        else:
            providers = await registry.get_metrics_providers()

        if not providers:
            return {"error": "No metrics providers available"}

        results = []

        for provider in providers:
            try:
                metrics = await provider.list_metrics()

                provider_metrics = {
                    "provider": provider.provider_name,
                    "supports_time_queries": provider.supports_time_queries,
                    "metrics_count": len(metrics),
                    "metrics": [
                        {
                            "name": metric.name,
                            "description": metric.description,
                            "unit": metric.unit,
                            "type": metric.metric_type,
                        }
                        for metric in metrics
                    ],
                }

                results.append(provider_metrics)

            except Exception as e:
                results.append({"provider": provider.provider_name, "error": str(e)})

        return {"providers_queried": len(results), "results": results}

    except Exception as e:
        logger.error(f"Error listing metrics: {e}")
        return {"error": str(e)}


async def search_logs(
    query: str,
    time_range_hours: float = 1.0,
    provider_name: Optional[str] = None,
    log_groups: Optional[List[str]] = None,
    level_filter: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Search logs across available providers.

    Args:
        query: Search query
        time_range_hours: Time range in hours to search
        provider_name: Optional specific provider to use
        log_groups: Optional log groups to search
        level_filter: Optional log level filter
        limit: Maximum number of results

    Returns:
        Log search results
    """
    try:
        registry = get_global_registry()

        # Get logs providers
        if provider_name:
            provider_instance = registry.get_provider(provider_name)
            if not provider_instance:
                return {"error": f"Provider '{provider_name}' not found"}

            logs_provider = await provider_instance.get_logs_provider()
            if not logs_provider:
                return {"error": f"Provider '{provider_name}' doesn't support logs"}

            providers = [logs_provider]
        else:
            providers = await registry.get_logs_providers()

        if not providers:
            return {"error": "No logs providers available"}

        # Create time range
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=time_range_hours)
        time_range = TimeRange(start_time, end_time)

        results = []

        for provider in providers:
            try:
                log_entries = await provider.search_logs(
                    query=query,
                    time_range=time_range,
                    log_groups=log_groups,
                    level_filter=level_filter,
                    limit=limit,
                )

                result = {
                    "provider": provider.provider_name,
                    "query": query,
                    "time_range_hours": time_range_hours,
                    "entries_found": len(log_entries),
                    "entries": [
                        {
                            "timestamp": entry.timestamp.isoformat(),
                            "level": entry.level,
                            "message": entry.message,
                            "source": entry.source,
                            "labels": entry.labels,
                        }
                        for entry in log_entries
                    ],
                }

                results.append(result)

            except Exception as e:
                results.append(
                    {"provider": provider.provider_name, "query": query, "error": str(e)}
                )

        return {"query": query, "providers_queried": len(results), "results": results}

    except Exception as e:
        logger.error(f"Error searching logs: {e}")
        return {"error": str(e)}


async def create_incident_ticket(
    title: str,
    description: str,
    provider_name: Optional[str] = None,
    labels: Optional[List[str]] = None,
    assignee: Optional[str] = None,
    priority: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an incident ticket using available providers.

    Args:
        title: Ticket title
        description: Ticket description
        provider_name: Optional specific provider to use
        labels: Optional labels/tags
        assignee: Optional assignee
        priority: Optional priority level

    Returns:
        Ticket creation results
    """
    try:
        registry = get_global_registry()

        # Get tickets providers
        if provider_name:
            provider_instance = registry.get_provider(provider_name)
            if not provider_instance:
                return {"error": f"Provider '{provider_name}' not found"}

            tickets_provider = await provider_instance.get_tickets_provider()
            if not tickets_provider:
                return {"error": f"Provider '{provider_name}' doesn't support tickets"}

            providers = [tickets_provider]
        else:
            providers = await registry.get_tickets_providers()

        if not providers:
            return {"error": "No tickets providers available"}

        # Use the first available provider for ticket creation
        provider = providers[0]

        try:
            ticket = await provider.create_ticket(
                title=title,
                description=description,
                labels=labels,
                assignee=assignee,
                priority=priority,
            )

            return {
                "provider": provider.provider_name,
                "ticket_created": True,
                "ticket": {
                    "id": ticket.id,
                    "title": ticket.title,
                    "description": ticket.description,
                    "status": ticket.status,
                    "assignee": ticket.assignee,
                    "labels": ticket.labels,
                },
            }

        except Exception as e:
            return {"provider": provider.provider_name, "ticket_created": False, "error": str(e)}

    except Exception as e:
        logger.error(f"Error creating ticket: {e}")
        return {"error": str(e)}


async def search_related_repositories(
    query: str,
    provider_name: Optional[str] = None,
    file_extensions: Optional[List[str]] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Search for repositories and code related to the query.

    Args:
        query: Search query (e.g., "redis", "cache", specific error messages)
        provider_name: Optional specific provider to use
        file_extensions: Optional file extension filters
        limit: Maximum number of results

    Returns:
        Repository and code search results
    """
    try:
        registry = get_global_registry()

        # Get repos providers
        if provider_name:
            provider_instance = registry.get_provider(provider_name)
            if not provider_instance:
                return {"error": f"Provider '{provider_name}' not found"}

            repos_provider = await provider_instance.get_repos_provider()
            if not repos_provider:
                return {"error": f"Provider '{provider_name}' doesn't support repositories"}

            providers = [repos_provider]
        else:
            providers = await registry.get_repos_providers()

        if not providers:
            return {"error": "No repository providers available"}

        results = []

        for provider in providers:
            try:
                # Search code across repositories
                code_results = await provider.search_code(
                    query=query, file_extensions=file_extensions, limit=limit
                )

                result = {
                    "provider": provider.provider_name,
                    "query": query,
                    "code_results_found": len(code_results),
                    "code_results": code_results,
                }

                results.append(result)

            except Exception as e:
                results.append(
                    {"provider": provider.provider_name, "query": query, "error": str(e)}
                )

        return {"query": query, "providers_queried": len(results), "results": results}

    except Exception as e:
        logger.error(f"Error searching repositories: {e}")
        return {"error": str(e)}

"""Dynamic SRE tools that use the Protocol-based provider system.

These tools replace the hardcoded tool implementations and dynamically
discover and use registered providers based on their capabilities.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .protocols import TimeRange
from .registry import get_global_registry

logger = logging.getLogger(__name__)


async def query_instance_metrics(
    metric_name: str,
    provider_name: Optional[str] = None,
    labels: Optional[Dict[str, str]] = None,
    time_range_hours: Optional[float] = None
) -> Dict[str, Any]:
    """Query instance metrics from available providers.

    Args:
        metric_name: Name of the metric to query
        provider_name: Optional specific provider to use
        labels: Optional label filters
        time_range_hours: Optional time range in hours for historical data

    Returns:
        Metric query results
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
                if time_range_hours and provider.supports_time_queries:
                    # Query time range
                    end_time = datetime.now()
                    start_time = end_time - timedelta(hours=time_range_hours)
                    time_range = TimeRange(start_time, end_time)

                    values = await provider.query_time_range(metric_name, time_range, labels)

                    result = {
                        "provider": provider.provider_name,
                        "metric_name": metric_name,
                        "time_range_hours": time_range_hours,
                        "values_count": len(values),
                        "values": [
                            {
                                "timestamp": value.timestamp.isoformat(),
                                "value": value.value,
                                "labels": value.labels
                            }
                            for value in values
                        ]
                    }
                else:
                    # Query current value
                    value = await provider.get_current_value(metric_name, labels)

                    if value:
                        result = {
                            "provider": provider.provider_name,
                            "metric_name": metric_name,
                            "current_value": value.value,
                            "timestamp": value.timestamp.isoformat(),
                            "labels": value.labels
                        }
                    else:
                        result = {
                            "provider": provider.provider_name,
                            "metric_name": metric_name,
                            "error": "Metric not found"
                        }

                results.append(result)

            except Exception as e:
                results.append({
                    "provider": provider.provider_name,
                    "metric_name": metric_name,
                    "error": str(e)
                })

        return {
            "metric_name": metric_name,
            "providers_queried": len(results),
            "results": results
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
                            "type": metric.metric_type
                        }
                        for metric in metrics
                    ]
                }

                results.append(provider_metrics)

            except Exception as e:
                results.append({
                    "provider": provider.provider_name,
                    "error": str(e)
                })

        return {
            "providers_queried": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"Error listing metrics: {e}")
        return {"error": str(e)}


async def search_logs(
    query: str,
    time_range_hours: float = 1.0,
    provider_name: Optional[str] = None,
    log_groups: Optional[List[str]] = None,
    level_filter: Optional[str] = None,
    limit: int = 100
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
                    limit=limit
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
                            "labels": entry.labels
                        }
                        for entry in log_entries
                    ]
                }

                results.append(result)

            except Exception as e:
                results.append({
                    "provider": provider.provider_name,
                    "query": query,
                    "error": str(e)
                })

        return {
            "query": query,
            "providers_queried": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"Error searching logs: {e}")
        return {"error": str(e)}


async def create_incident_ticket(
    title: str,
    description: str,
    provider_name: Optional[str] = None,
    labels: Optional[List[str]] = None,
    assignee: Optional[str] = None,
    priority: Optional[str] = None
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
                priority=priority
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
                    "labels": ticket.labels
                }
            }

        except Exception as e:
            return {
                "provider": provider.provider_name,
                "ticket_created": False,
                "error": str(e)
            }

    except Exception as e:
        logger.error(f"Error creating ticket: {e}")
        return {"error": str(e)}


async def search_related_repositories(
    query: str,
    provider_name: Optional[str] = None,
    file_extensions: Optional[List[str]] = None,
    limit: int = 20
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
                    query=query,
                    file_extensions=file_extensions,
                    limit=limit
                )

                result = {
                    "provider": provider.provider_name,
                    "query": query,
                    "code_results_found": len(code_results),
                    "code_results": code_results
                }

                results.append(result)

            except Exception as e:
                results.append({
                    "provider": provider.provider_name,
                    "query": query,
                    "error": str(e)
                })

        return {
            "query": query,
            "providers_queried": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"Error searching repositories: {e}")
        return {"error": str(e)}

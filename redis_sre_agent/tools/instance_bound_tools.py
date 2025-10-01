"""Instance-bound tool factories using functools.partial.

When diagnosing a specific Redis instance, tools should be pre-configured
with that instance's connection details. This prevents the LLM from accidentally
using wrong parameters or connecting to the wrong instance.

Pattern:
1. Use functools.partial to bind instance-specific parameters
2. Create StructuredTool with reduced schema (only unbound params)
3. LLM sees simplified tool that can't make wrong choices

Two modes:
1. Instance-bound: Tools are pre-configured with instance details (LLM can't override)
2. Unbound: Tools accept parameters from LLM (for exploratory queries)
"""

import logging
from functools import partial
from typing import Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from redis_sre_agent.api.instances import RedisInstance

logger = logging.getLogger(__name__)


# Schema for instance-bound metrics (only metric_name exposed)
class BoundMetricsArgs(BaseModel):
    """Arguments for instance-bound metrics query."""

    metric_name: str = Field(
        ..., description="Metric to query (e.g., 'used_memory', 'connected_clients')"
    )
    time_range_hours: Optional[float] = Field(1, description="Time range in hours (default: 1)")


def create_instance_bound_metrics_tool(instance: RedisInstance) -> StructuredTool:
    """Create a metrics query tool bound to a specific Redis instance.

    Uses functools.partial to bind redis_url, then creates a StructuredTool
    with a reduced schema that only exposes metric_name.

    Args:
        instance: The Redis instance to bind to

    Returns:
        StructuredTool with bound redis_url
    """
    from redis_sre_agent.agent.langgraph_agent import _parse_redis_connection_url
    from redis_sre_agent.tools.dynamic_tools import query_instance_metrics

    host, port = _parse_redis_connection_url(instance.connection_url)

    # Bind the redis_url using functools.partial
    bound_func = partial(query_instance_metrics, redis_url=instance.connection_url)

    # Create tool with reduced schema (no redis_url, no provider_name)
    return StructuredTool.from_function(
        func=bound_func,
        name="query_instance_metrics",
        description=f"""Query metrics for {instance.name} ({instance.environment}).

PRE-CONFIGURED for:
- Instance: {instance.name}
- Host: {host}:{port}
- Environment: {instance.environment}

Do NOT specify redis_url or provider_name - they are already bound.
Just provide the metric_name you want to query.""",
        args_schema=BoundMetricsArgs,
    )


# Schema for unbound metrics (full surface)
class UnboundMetricsArgs(BaseModel):
    """Arguments for unbound metrics query."""

    metric_name: str = Field(
        ..., description="Metric to query (e.g., 'used_memory', 'connected_clients')"
    )
    provider_name: Optional[str] = Field(
        None, description="Provider to use (e.g., 'redis', 'prometheus')"
    )
    labels: Optional[Dict[str, str]] = Field(None, description="Label filters for the query")
    time_range_hours: Optional[float] = Field(1, description="Time range in hours (default: 1)")
    redis_url: Optional[str] = Field(None, description="Redis URL for instance-specific queries")


def create_unbound_metrics_tool() -> StructuredTool:
    """Create a metrics query tool that accepts all parameters from LLM.

    Use this when no specific instance is selected.

    Returns:
        StructuredTool with full parameter surface
    """
    from redis_sre_agent.tools.dynamic_tools import query_instance_metrics

    return StructuredTool.from_function(
        func=query_instance_metrics,
        name="query_instance_metrics",
        description="""Query metrics from Redis instances or monitoring systems.

You can specify:
- metric_name: Which metric to query
- provider_name: Which provider to use (redis, prometheus, etc.)
- redis_url: Direct Redis connection for instance-specific queries
- labels: Filter by labels
- time_range_hours: Historical data range""",
        args_schema=UnboundMetricsArgs,
    )


def get_tools_for_instance(instance: Optional[RedisInstance]) -> List[StructuredTool]:
    """Get tool definitions appropriate for the given instance context.

    If instance is provided: Returns instance-bound tools (LLM can't override)
    If instance is None: Returns unbound tools (LLM must provide parameters)

    Args:
        instance: The Redis instance to bind tools to, or None for unbound tools

    Returns:
        List of StructuredTool instances
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

"""Redis direct metrics provider type.

This provider type connects directly to Redis instances via Redis protocol
and gathers metrics using INFO commands. It wraps the existing
RedisCommandMetricsProvider to create instance-scoped tools.
"""

import logging
from typing import Any, Dict, List

from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.models.provider_config import RedisDirectMetricsConfig

from ..protocols import ToolCapability
from ..providers.redis_command_metrics import RedisCommandMetricsProvider
from ..tool_definition import ToolDefinition
from .base import ProviderType

logger = logging.getLogger(__name__)


class RedisDirectMetricsProviderType(ProviderType):
    """Provider type for direct Redis metrics connections.

    This provider creates tools that connect directly to Redis instances
    via Redis protocol and gather metrics using INFO commands.
    """

    def __init__(self, config: RedisDirectMetricsConfig):
        """Initialize the provider type.

        Args:
            config: Configuration for Redis direct metrics
        """
        self.config = config

    @property
    def provider_type_name(self) -> str:
        return "redis_metrics"

    def get_capabilities(self) -> List[ToolCapability]:
        return [ToolCapability.METRICS]

    def create_tools_scoped_to_instance(self, instance: RedisInstance) -> List[ToolDefinition]:
        """Create metrics tools for a specific Redis instance.

        Creates three tools:
        1. list_metrics - List available metrics
        2. query_metrics - Query specific metrics
        3. get_summary - Get summary of metrics by section

        Args:
            instance: The Redis instance to create tools for

        Returns:
            List of tool definitions
        """
        tools = []

        # Create a provider instance for this Redis instance
        # (This is temporary - we create it per-call in the tool functions)

        # Tool 1: List metrics
        tools.append(self._create_list_metrics_tool(instance))

        # Tool 2: Query metrics
        tools.append(self._create_query_metrics_tool(instance))

        # Tool 3: Get summary
        tools.append(self._create_get_summary_tool(instance))

        return tools

    def _create_list_metrics_tool(self, instance: RedisInstance) -> ToolDefinition:
        """Create the list_metrics tool for an instance."""
        tool_name = self._create_tool_name(instance, "list_metrics")
        description_prefix = self._create_tool_description_prefix(instance)

        async def list_metrics_func() -> List[Dict[str, Any]]:
            """List available metrics from this Redis instance."""
            provider = RedisCommandMetricsProvider(instance.connection_url)
            try:
                metrics = await provider.list_metrics()
                return [
                    {
                        "name": m.name,
                        "description": m.description,
                        "unit": m.unit,
                        "type": m.metric_type,
                    }
                    for m in metrics
                ]
            finally:
                await provider.close()

        return ToolDefinition(
            name=tool_name,
            description=(
                f"{description_prefix}"
                f"List all available metrics from this Redis instance. "
                f"Use this FIRST before querying metrics to see what's available. "
                f"Returns metric names, descriptions, units, and types. "
                f"This connects directly to Redis via INFO command."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            function=list_metrics_func,
        )

    def _create_query_metrics_tool(self, instance: RedisInstance) -> ToolDefinition:
        """Create the query_metrics tool for an instance."""
        tool_name = self._create_tool_name(instance, "query_metrics")
        description_prefix = self._create_tool_description_prefix(instance)
        list_tool_name = self._create_tool_name(instance, "list_metrics")

        async def query_metrics_func(metric_names: List[str]) -> Dict[str, Any]:
            """Query specific metrics from this Redis instance."""
            provider = RedisCommandMetricsProvider(instance.connection_url)
            try:
                results = {}
                for metric_name in metric_names:
                    try:
                        metric_value = await provider.get_current_value(metric_name)
                        if metric_value:
                            results[metric_name] = {
                                "value": metric_value.value,
                                "timestamp": metric_value.timestamp.isoformat(),
                            }
                        else:
                            results[metric_name] = {"error": "Metric not found"}
                    except Exception as e:
                        results[metric_name] = {"error": str(e)}

                return {
                    "instance": instance.name,
                    "connection_url": instance.connection_url,
                    "metrics": results,
                }
            finally:
                await provider.close()

        return ToolDefinition(
            name=tool_name,
            description=(
                f"{description_prefix}"
                f"Query specific metrics from this Redis instance. "
                f"Connects directly via Redis protocol using INFO command. "
                f"Can query multiple metrics in one call for efficiency. "
                f"Use {list_tool_name} first to see available metrics. "
                f"Example metric names: used_memory, connected_clients, keyspace_hits."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "metric_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of metric names to query. "
                            "Example: ['used_memory', 'connected_clients', 'keyspace_hits']"
                        ),
                    }
                },
                "required": ["metric_names"],
            },
            function=query_metrics_func,
        )

    def _create_get_summary_tool(self, instance: RedisInstance) -> ToolDefinition:
        """Create the get_summary tool for an instance."""
        tool_name = self._create_tool_name(instance, "get_summary")
        description_prefix = self._create_tool_description_prefix(instance)

        async def get_summary_func(sections: List[str]) -> Dict[str, Any]:
            """Get summary of metrics grouped by section."""
            provider = RedisCommandMetricsProvider(instance.connection_url)
            try:
                # Get all metrics
                all_metrics = await provider.list_metrics()

                # Group by section (simplified - just get all for now)
                summary = {
                    "instance": instance.name,
                    "connection_url": instance.connection_url,
                    "sections": {},
                }

                for section in sections:
                    section_metrics = {}
                    # Filter metrics by section (based on metric name prefix)
                    for metric_def in all_metrics:
                        if self._metric_belongs_to_section(metric_def.name, section):
                            try:
                                metric_value = await provider.get_current_value(metric_def.name)
                                if metric_value:
                                    section_metrics[metric_def.name] = {
                                        "value": metric_value.value,
                                        "unit": metric_def.unit,
                                        "description": metric_def.description,
                                    }
                            except Exception as e:
                                logger.debug(f"Error getting metric {metric_def.name}: {e}")

                    summary["sections"][section] = section_metrics

                return summary
            finally:
                await provider.close()

        return ToolDefinition(
            name=tool_name,
            description=(
                f"{description_prefix}"
                f"Get summary of metrics from this Redis instance grouped by section. "
                f"This is a convenience method that retrieves multiple related metrics efficiently. "
                f"More efficient than querying individual metrics. "
                f"Available sections: memory, performance, clients, persistence, replication, cpu. "
                f"Example: sections=['memory', 'performance'] for memory and performance metrics."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Sections to include in summary. "
                            "Options: memory, performance, clients, persistence, replication, cpu. "
                            "Example: ['memory', 'performance']"
                        ),
                    }
                },
                "required": ["sections"],
            },
            function=get_summary_func,
        )

    def _metric_belongs_to_section(self, metric_name: str, section: str) -> bool:
        """Check if a metric belongs to a section."""
        section_keywords = {
            "memory": ["memory", "mem_", "maxmemory"],
            "performance": ["commands", "ops", "keyspace", "hits", "misses", "expired", "evicted"],
            "clients": ["clients", "blocked", "rejected"],
            "persistence": ["rdb", "aof", "save"],
            "replication": ["repl", "slave", "master", "role"],
            "cpu": ["cpu"],
        }

        keywords = section_keywords.get(section, [])
        return any(keyword in metric_name.lower() for keyword in keywords)

    async def health_check(self) -> Dict[str, Any]:
        """Check if this provider type is healthy.

        For Redis direct metrics, we just check that the config is valid.
        Actual connectivity is checked per-instance.
        """
        return {
            "provider_type": self.provider_type_name,
            "status": "healthy",
            "config": {
                "connection_timeout": self.config.connection_timeout,
                "socket_timeout": self.config.socket_timeout,
            },
        }

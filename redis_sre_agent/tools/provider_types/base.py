"""Base class for provider types.

Provider types are configured at deployment level and create tools scoped to
specific Redis instances. This allows the same provider configuration to be
used across multiple instances.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from redis_sre_agent.api.instances import RedisInstance

from ..protocols import ToolCapability
from ..tool_definition import ToolDefinition


class ProviderType(ABC):
    """Base class for provider types configured at deployment.

    A ProviderType represents a deployment-level configuration for a tool provider
    (e.g., Prometheus, CloudWatch, Redis Direct). It can create tools scoped to
    specific Redis instances.

    Example:
        # Deployment-level: One PrometheusMetricsProviderType configured
        prometheus_provider = PrometheusMetricsProviderType(
            config=PrometheusConfig(prometheus_url="http://prometheus:9090")
        )

        # Instance-level: Create tools for each instance
        prod_tools = prometheus_provider.create_tools_scoped_to_instance(prod_instance)
        # Creates: prometheus_prod_1_query_metrics, prometheus_prod_1_list_metrics, etc.

        staging_tools = prometheus_provider.create_tools_scoped_to_instance(staging_instance)
        # Creates: prometheus_staging_1_query_metrics, prometheus_staging_1_list_metrics, etc.
    """

    @property
    @abstractmethod
    def provider_type_name(self) -> str:
        """Name of this provider type (e.g., 'prometheus', 'redis_direct_metrics').

        This is used as a prefix for tool names.
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> List[ToolCapability]:
        """Get the capabilities this provider type offers.

        Returns:
            List of capabilities (METRICS, LOGS, DIAGNOSTICS, etc.)
        """
        ...

    @abstractmethod
    def create_tools_scoped_to_instance(self, instance: RedisInstance) -> List[ToolDefinition]:
        """Create tools for a specific Redis instance.

        This method creates discrete, named tools that are scoped to a specific
        instance. Tool names should include the instance identifier to make them
        unique and clear to the LLM.

        Tool naming convention:
            {provider_type_name}_{instance.name}_{operation}

        Examples:
            - redis_metrics_prod_1_query_metrics
            - redis_metrics_prod_1_list_metrics
            - redis_metrics_prod_1_get_summary
            - redis_diagnostics_prod_1_sample_keys
            - prometheus_prod_1_query_metrics

        Args:
            instance: The Redis instance to create tools for

        Returns:
            List of ToolDefinition objects, each representing a discrete tool
            that the LLM can call
        """
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check if this provider type is healthy and accessible.

        Returns:
            Dictionary with health status information
        """
        ...

    def supports_instance_type(self, instance_type: str) -> bool:
        """Check if this provider supports a specific instance type.

        Some providers may only work with certain Redis instance types.
        For example, RedisEnterpriseProviderType only works with
        instance_type='redis_enterprise'.

        Args:
            instance_type: The instance type to check (e.g., 'redis-oss', 'redis-enterprise')

        Returns:
            True if this provider supports the instance type, False otherwise
        """
        # By default, support all instance types
        return True

    def _create_tool_name(self, instance: RedisInstance, operation: str) -> str:
        """Helper to create a consistent tool name.

        Args:
            instance: The Redis instance
            operation: The operation name (e.g., 'query_metrics', 'sample_keys')

        Returns:
            Formatted tool name that matches OpenAI's pattern ^[a-zA-Z0-9_-]+$
        """
        import re

        # Sanitize instance name to match OpenAI's pattern: ^[a-zA-Z0-9_-]+$
        # Replace any character that's not alphanumeric, underscore, or hyphen with underscore
        safe_instance_name = re.sub(r"[^a-zA-Z0-9_-]", "_", instance.name)

        # Remove any leading/trailing underscores or hyphens
        safe_instance_name = safe_instance_name.strip("_-")

        # Ensure it's not empty
        if not safe_instance_name:
            safe_instance_name = "instance"

        return f"{self.provider_type_name}_{safe_instance_name}_{operation}"

    def _create_tool_description_prefix(self, instance: RedisInstance) -> str:
        """Helper to create a consistent tool description prefix.

        Args:
            instance: The Redis instance

        Returns:
            Description prefix with instance context
        """
        return (
            f"[Instance: {instance.name}] "
            f"[URL: {instance.connection_url}] "
            f"[Environment: {instance.environment}] "
        )

    def __str__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}(type={self.provider_type_name})"

    def __repr__(self) -> str:
        """Detailed representation."""
        capabilities = [cap.value for cap in self.get_capabilities()]
        return (
            f"{self.__class__.__name__}("
            f"type={self.provider_type_name}, "
            f"capabilities={capabilities})"
        )

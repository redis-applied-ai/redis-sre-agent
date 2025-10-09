"""Deployment providers manager.

This module manages all provider types configured for this deployment.
It initializes provider types from configuration and creates tools scoped
to specific Redis instances.
"""

import logging
from typing import Dict, List, Optional

from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.models.provider_config import DeploymentProvidersConfig

from .provider_types.base import ProviderType
from .provider_types.redis_direct_diagnostics import RedisDirectDiagnosticsProviderType
from .provider_types.redis_direct_metrics import RedisDirectMetricsProviderType
from .tool_definition import ToolDefinition

logger = logging.getLogger(__name__)


class DeploymentProviders:
    """Manages all provider types configured for this deployment.

    This class:
    1. Loads provider configurations from settings
    2. Initializes provider type instances
    3. Creates tools for Redis instances using those provider types

    Example:
        # At deployment/startup
        config = DeploymentProvidersConfig.from_env()
        deployment_providers = DeploymentProviders(config)

        # At conversation start
        instances = await get_all_instances(user_id, thread_id)
        for instance in instances:
            tools = deployment_providers.create_tools_for_instance(instance)
            # Register tools with agent
    """

    def __init__(self, config: DeploymentProvidersConfig):
        """Initialize deployment providers from configuration.

        Args:
            config: Deployment provider configuration
        """
        self.config = config
        self.provider_types: Dict[str, ProviderType] = {}

        # Initialize enabled provider types
        self._initialize_provider_types()

        logger.info(f"Initialized deployment providers: {list(self.provider_types.keys())}")

    def _initialize_provider_types(self):
        """Initialize provider type instances from configuration."""

        # Redis Direct Metrics
        if self.config.redis_direct_metrics:
            try:
                provider_type = RedisDirectMetricsProviderType(self.config.redis_direct_metrics)
                self.provider_types["redis_direct_metrics"] = provider_type
                logger.info("Initialized Redis Direct Metrics provider type")
            except Exception as e:
                logger.error(f"Failed to initialize Redis Direct Metrics provider: {e}")

        # Redis Direct Diagnostics
        if self.config.redis_direct_diagnostics:
            try:
                provider_type = RedisDirectDiagnosticsProviderType(
                    self.config.redis_direct_diagnostics
                )
                self.provider_types["redis_direct_diagnostics"] = provider_type
                logger.info("Initialized Redis Direct Diagnostics provider type")
            except Exception as e:
                logger.error(f"Failed to initialize Redis Direct Diagnostics provider: {e}")

        # TODO: Add more provider types as they're implemented
        # - Prometheus Metrics
        # - CloudWatch Logs
        # - GitHub Tickets/Repos
        # - Redis Enterprise
        # - X-Ray Traces

    def create_tools_for_instance(self, instance: RedisInstance) -> List[ToolDefinition]:
        """Create all tools for a specific Redis instance.

        This method iterates through all enabled provider types and asks
        each one to create tools for the given instance.

        Args:
            instance: The Redis instance to create tools for

        Returns:
            List of tool definitions for this instance
        """
        tools = []

        for provider_name, provider_type in self.provider_types.items():
            # Check if this provider supports this instance type
            if not provider_type.supports_instance_type(instance.instance_type):
                logger.debug(
                    f"Provider {provider_name} does not support "
                    f"instance type {instance.instance_type}, skipping"
                )
                continue

            try:
                # Create tools for this instance
                instance_tools = provider_type.create_tools_scoped_to_instance(instance)
                tools.extend(instance_tools)

                logger.debug(
                    f"Created {len(instance_tools)} tools from {provider_name} "
                    f"for instance {instance.name}"
                )
            except Exception as e:
                logger.error(
                    f"Error creating tools from {provider_name} for instance {instance.name}: {e}"
                )

        logger.info(f"Created {len(tools)} total tools for instance {instance.name}")

        return tools

    def create_tools_for_instances(self, instances: List[RedisInstance]) -> List[ToolDefinition]:
        """Create tools for multiple Redis instances.

        Args:
            instances: List of Redis instances

        Returns:
            Combined list of tool definitions for all instances
        """
        all_tools = []

        for instance in instances:
            tools = self.create_tools_for_instance(instance)
            all_tools.extend(tools)

        logger.info(f"Created {len(all_tools)} total tools for {len(instances)} instances")

        return all_tools

    def get_provider_type(self, name: str) -> Optional[ProviderType]:
        """Get a provider type by name.

        Args:
            name: Provider type name (e.g., 'redis_direct_metrics')

        Returns:
            ProviderType instance if found, None otherwise
        """
        return self.provider_types.get(name)

    def get_enabled_provider_names(self) -> List[str]:
        """Get list of enabled provider type names.

        Returns:
            List of provider type names
        """
        return list(self.provider_types.keys())

    async def health_check_all(self) -> Dict[str, Dict]:
        """Check health of all provider types.

        Returns:
            Dictionary mapping provider names to health status
        """
        health_results = {}

        for provider_name, provider_type in self.provider_types.items():
            try:
                health = await provider_type.health_check()
                health_results[provider_name] = health
            except Exception as e:
                health_results[provider_name] = {
                    "status": "error",
                    "error": str(e),
                }

        return health_results

    def __str__(self) -> str:
        """String representation."""
        return f"DeploymentProviders(providers={list(self.provider_types.keys())})"

    def __repr__(self) -> str:
        """Detailed representation."""
        return (
            f"DeploymentProviders("
            f"providers={list(self.provider_types.keys())}, "
            f"count={len(self.provider_types)})"
        )


# Global singleton
_deployment_providers: Optional[DeploymentProviders] = None


def get_deployment_providers() -> DeploymentProviders:
    """Get the global deployment providers instance.

    This creates a singleton instance on first call, loading configuration
    from the application settings.

    Returns:
        DeploymentProviders instance
    """
    global _deployment_providers

    if _deployment_providers is None:
        from redis_sre_agent.core.config import settings

        # Load provider configuration
        providers_config = settings.providers

        # Create deployment providers
        _deployment_providers = DeploymentProviders(providers_config)

        logger.info("Initialized global deployment providers")

    return _deployment_providers


def reset_deployment_providers():
    """Reset the global deployment providers instance.

    This is primarily useful for testing.
    """
    global _deployment_providers
    _deployment_providers = None

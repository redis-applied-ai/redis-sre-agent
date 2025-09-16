"""SRE Tool Registry for dynamic tool discovery and registration.

This module provides a registry system that allows the agent to discover
and register Protocol-based tools dynamically. Users can register their
own tool providers that implement the SRE protocols.
"""

import logging
from typing import Any, Dict, List, Optional

from .protocols import (
    LogsProvider,
    MetricsProvider,
    ReposProvider,
    SREToolProvider,
    TicketsProvider,
    ToolCapability,
    TracesProvider,
)

logger = logging.getLogger(__name__)


class SREToolRegistry:
    """Registry for SRE tool providers.

    This registry allows dynamic registration and discovery of tool providers
    that implement the SRE protocols. The agent can query the registry to
    find available tools for specific capabilities.
    """

    def __init__(self):
        self._providers: Dict[str, SREToolProvider] = {}
        self._capability_map: Dict[ToolCapability, List[str]] = {
            capability: [] for capability in ToolCapability
        }

    def register_provider(self, name: str, provider: SREToolProvider) -> None:
        """Register a new SRE tool provider.

        Args:
            name: Unique name for the provider
            provider: Provider instance implementing SREToolProvider protocol
        """
        if name in self._providers:
            logger.warning(f"Provider '{name}' already registered, replacing")

        self._providers[name] = provider

        # Update capability mapping
        for capability in provider.capabilities:
            if name not in self._capability_map[capability]:
                self._capability_map[capability].append(name)

        logger.info(
            f"Registered SRE provider '{name}' with capabilities: {[c.value for c in provider.capabilities]}"
        )

    def unregister_provider(self, name: str) -> bool:
        """Unregister an SRE tool provider.

        Args:
            name: Name of the provider to unregister

        Returns:
            True if provider was found and removed, False otherwise
        """
        if name not in self._providers:
            return False

        provider = self._providers[name]

        # Remove from capability mapping
        for capability in provider.capabilities:
            if name in self._capability_map[capability]:
                self._capability_map[capability].remove(name)

        del self._providers[name]
        logger.info(f"Unregistered SRE provider '{name}'")
        return True

    def get_provider(self, name: str) -> Optional[SREToolProvider]:
        """Get a specific provider by name.

        Args:
            name: Name of the provider

        Returns:
            Provider instance or None if not found
        """
        return self._providers.get(name)

    def list_providers(self) -> List[str]:
        """List all registered provider names.

        Returns:
            List of provider names
        """
        return list(self._providers.keys())

    def get_providers_by_capability(self, capability: ToolCapability) -> List[str]:
        """Get provider names that support a specific capability.

        Args:
            capability: The capability to search for

        Returns:
            List of provider names that support the capability
        """
        return self._capability_map.get(capability, []).copy()

    async def get_metrics_providers(self) -> List[MetricsProvider]:
        """Get all available metrics providers.

        Returns:
            List of metrics provider instances
        """
        providers = []
        for name in self.get_providers_by_capability(ToolCapability.METRICS):
            provider = self._providers[name]
            metrics_provider = await provider.get_metrics_provider()
            if metrics_provider:
                providers.append(metrics_provider)
        return providers

    async def get_logs_providers(self) -> List[LogsProvider]:
        """Get all available logs providers.

        Returns:
            List of logs provider instances
        """
        providers = []
        for name in self.get_providers_by_capability(ToolCapability.LOGS):
            provider = self._providers[name]
            logs_provider = await provider.get_logs_provider()
            if logs_provider:
                providers.append(logs_provider)
        return providers

    async def get_tickets_providers(self) -> List[TicketsProvider]:
        """Get all available tickets providers.

        Returns:
            List of tickets provider instances
        """
        providers = []
        for name in self.get_providers_by_capability(ToolCapability.TICKETS):
            provider = self._providers[name]
            tickets_provider = await provider.get_tickets_provider()
            if tickets_provider:
                providers.append(tickets_provider)
        return providers

    async def get_repos_providers(self) -> List[ReposProvider]:
        """Get all available repository providers.

        Returns:
            List of repository provider instances
        """
        providers = []
        for name in self.get_providers_by_capability(ToolCapability.REPOS):
            provider = self._providers[name]
            repos_provider = await provider.get_repos_provider()
            if repos_provider:
                providers.append(repos_provider)
        return providers

    async def get_traces_providers(self) -> List[TracesProvider]:
        """Get all available traces providers.

        Returns:
            List of traces provider instances
        """
        providers = []
        for name in self.get_providers_by_capability(ToolCapability.TRACES):
            provider = self._providers[name]
            traces_provider = await provider.get_traces_provider()
            if traces_provider:
                providers.append(traces_provider)
        return providers

    async def health_check_all(self) -> Dict[str, Any]:
        """Perform health checks on all registered providers.

        Returns:
            Dictionary with health check results for each provider
        """
        results = {}

        for name, provider in self._providers.items():
            try:
                health_result = await provider.health_check()
                results[name] = health_result
            except Exception as e:
                results[name] = {
                    "status": "error",
                    "provider": provider.provider_name,
                    "error": str(e),
                }

        return results

    def get_registry_status(self) -> Dict[str, Any]:
        """Get overall registry status and statistics.

        Returns:
            Registry status information
        """
        capability_counts = {
            capability.value: len(providers)
            for capability, providers in self._capability_map.items()
        }

        return {
            "total_providers": len(self._providers),
            "providers": list(self._providers.keys()),
            "capability_counts": capability_counts,
            "capabilities_available": [
                capability.value
                for capability, providers in self._capability_map.items()
                if providers
            ],
        }


# Global registry instance
_global_registry: Optional[SREToolRegistry] = None


def get_global_registry() -> SREToolRegistry:
    """Get the global SRE tool registry instance.

    Returns:
        Global registry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = SREToolRegistry()
    return _global_registry


def register_provider(name: str, provider: SREToolProvider) -> None:
    """Register a provider with the global registry.

    Args:
        name: Unique name for the provider
        provider: Provider instance
    """
    registry = get_global_registry()
    registry.register_provider(name, provider)


def unregister_provider(name: str) -> bool:
    """Unregister a provider from the global registry.

    Args:
        name: Name of the provider to unregister

    Returns:
        True if provider was found and removed
    """
    registry = get_global_registry()
    return registry.unregister_provider(name)


# Auto-registration helper functions
def auto_register_default_providers(config: Dict[str, Any]) -> None:
    """Auto-register default providers based on configuration.

    Args:
        config: Configuration dictionary with provider settings
    """
    registry = get_global_registry()

    # Register Redis provider if Redis URL is configured
    if config.get("redis_url"):
        from .providers import create_redis_provider

        redis_provider = create_redis_provider(
            redis_url=config["redis_url"], prometheus_url=config.get("prometheus_url")
        )
        registry.register_provider("redis", redis_provider)

    # Register AWS provider if AWS credentials are configured
    if config.get("aws_region") or config.get("aws_access_key_id"):
        from .providers import create_aws_provider

        aws_provider = create_aws_provider(
            region_name=config.get("aws_region", "us-east-1"),
            aws_access_key_id=config.get("aws_access_key_id"),
            aws_secret_access_key=config.get("aws_secret_access_key"),
        )
        registry.register_provider("aws", aws_provider)

    # Register GitHub provider if GitHub token is configured
    if config.get("github_token"):
        from .providers import create_github_provider

        github_provider = create_github_provider(
            token=config["github_token"],
            organization=config.get("github_organization"),
            default_repo=config.get("github_default_repo"),
        )
        registry.register_provider("github", github_provider)

    logger.info(f"Auto-registered {len(registry.list_providers())} default providers")

"""Tool manager for provider lifecycle and routing.

This module provides the ToolManager class which handles:
1. Loading configured tool providers
2. Managing provider lifecycle (async context managers)
3. Building a routing table from tool names to providers
4. Routing LLM tool calls to the correct provider
"""

import logging
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

from redis_sre_agent.api.instances import RedisInstance

from .protocols import ToolProvider
from .tool_definition import ToolDefinition

logger = logging.getLogger(__name__)


class ToolManager:
    """Manages tool provider lifecycle and routing.

    ToolManager is an async context manager that:
    1. Loads configured tool providers
    2. Enters each provider's context
    3. Builds a routing table mapping tool names to providers
    4. Routes LLM tool calls to the correct provider
    5. Cleans up all providers on exit

    Example:
        async with ToolManager(redis_instance=instance) as mgr:
            # Get tools for LLM binding
            tools = mgr.get_tools()

            # Execute a tool call
            result = await mgr.resolve_tool_call(
                "prometheus_a3f2b1_query_metrics",
                {"metric_name": "cpu_usage"}
            )
    """

    # Class-level cache for provider classes (path -> class)
    _provider_class_cache: Dict[str, type] = {}

    # Hard-coded always-on providers
    _always_on_providers = [
        "redis_sre_agent.tools.knowledge.knowledge_base.KnowledgeBaseToolProvider",
        "redis_sre_agent.tools.utilities.provider.UtilitiesToolProvider",
    ]

    def __init__(self, redis_instance: Optional[RedisInstance] = None):
        """Initialize tool manager.

        Args:
            redis_instance: Optional Redis instance to scope tools to
        """
        self.redis_instance = redis_instance
        # Track loaded provider class paths to avoid duplicates
        self._loaded_provider_paths: set[str] = set()

        self._routing_table: Dict[str, ToolProvider] = {}
        self._tools: List[ToolDefinition] = []
        self._stack: Optional[AsyncExitStack] = None

    async def __aenter__(self) -> "ToolManager":
        """Enter context manager and load all providers."""
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        # Load always-on providers first (these don't require redis_instance)
        for provider_path in self._always_on_providers:
            await self._load_provider(provider_path, always_on=True)

        # Load instance-specific providers only if redis_instance is provided
        if self.redis_instance:
            logger.info(f"Loading instance-specific providers for: {self.redis_instance.name}")

            # Load configured providers (these require redis_instance)
            from redis_sre_agent.core.config import settings

            for provider_path in settings.tool_providers:
                await self._load_provider(provider_path)

            # Load additional providers based on instance type
            instance_type = self.redis_instance.instance_type
            logger.info(f"Instance type: {instance_type}")

            if instance_type == "redis_enterprise":
                # Load Redis Enterprise admin API provider
                # Check for non-empty admin_url (handle None, empty string, whitespace)
                has_admin_url = (
                    self.redis_instance.admin_url and self.redis_instance.admin_url.strip()
                )

                if has_admin_url:
                    logger.info("Loading Redis Enterprise admin API provider")
                    await self._load_provider(
                        "redis_sre_agent.tools.admin.redis_enterprise.provider.RedisEnterpriseAdminToolProvider"
                    )
                else:
                    logger.warning(
                        f"Redis Enterprise instance '{self.redis_instance.name}' detected but no admin_url configured. "
                        "Enterprise admin tools will not be available. Using standard Redis CLI tools only."
                    )

            elif instance_type == "oss_cluster":
                # Future: Load Redis Cluster-specific tools
                logger.info(
                    "OSS Cluster instance detected (cluster-specific tools not yet implemented)"
                )

            elif instance_type == "oss_single":
                logger.info("OSS Single instance detected (using standard Redis CLI tools)")

            elif instance_type == "redis_cloud":
                # Load Redis Cloud Management API provider if credentials are available
                import os

                has_cloud_credentials = os.getenv("TOOLS_REDIS_CLOUD_API_KEY") and os.getenv(
                    "TOOLS_REDIS_CLOUD_API_SECRET_KEY"
                )

                if has_cloud_credentials:
                    logger.info("Loading Redis Cloud Management API provider")
                    await self._load_provider(
                        "redis_sre_agent.tools.cloud.redis_cloud.provider.RedisCloudToolProvider"
                    )
                else:
                    logger.warning(
                        f"Redis Cloud instance '{self.redis_instance.name}' detected but no API credentials configured. "
                        "Set TOOLS_REDIS_CLOUD_API_KEY and TOOLS_REDIS_CLOUD_API_SECRET_KEY environment variables "
                        "to enable Redis Cloud Management API tools. Using standard Redis CLI tools only."
                    )

            else:
                logger.info(
                    f"Unknown or unspecified instance type '{instance_type}' for instance '{self.redis_instance.name}'. "
                    "Using standard Redis tools."
                )
        else:
            logger.info("No redis_instance provided - loading only instance-independent providers")

        logger.info(
            f"ToolManager initialized with {len(self._tools)} tools "
            f"from {len(set(self._routing_table.values()))} providers"
        )

        return self

    async def _load_provider(self, provider_path: str, always_on: bool = False) -> None:
        """Load and register a provider.

        Args:
            provider_path: Fully qualified class path
            always_on: If True, initialize without redis_instance (for always-on providers)
        """
        try:
            # Skip duplicate loads of the same provider class
            if provider_path in self._loaded_provider_paths:
                logger.debug(f"Provider already loaded, skipping duplicate: {provider_path}")
                return

            provider_cls = self._get_provider_class(provider_path)
            # Always-on providers should not have redis_instance set
            instance = None if always_on else self.redis_instance
            provider = await self._stack.enter_async_context(provider_cls(redis_instance=instance))

            # Register tools in routing table
            tool_schemas = provider.create_tool_schemas()
            for tool_def in tool_schemas:
                self._routing_table[tool_def.name] = provider
                self._tools.append(tool_def)

            # Mark this provider as loaded to avoid duplicates later
            self._loaded_provider_paths.add(provider_path)

            logger.info(f"Loaded provider {provider.provider_name} with {len(tool_schemas)} tools")

        except Exception:
            logger.exception(f"Failed to load provider {provider_path}")
            # Don't fail entire manager if one provider fails

    @classmethod
    def _get_provider_class(cls, provider_path: str) -> type:
        """Get provider class from path, with caching.

        Args:
            provider_path: Fully qualified class path
                (e.g., 'redis_sre_agent.tools.metrics.prometheus.PrometheusToolProvider')

        Returns:
            Provider class
        """
        if provider_path not in cls._provider_class_cache:
            module_path, class_name = provider_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            cls._provider_class_cache[provider_path] = getattr(module, class_name)
        return cls._provider_class_cache[provider_path]

    async def __aexit__(self, *args) -> None:
        """Exit context manager and cleanup all providers."""
        if self._stack:
            await self._stack.__aexit__(*args)

    def get_tools(self) -> List[ToolDefinition]:
        """Get all registered tool schemas.

        Returns:
            List of ToolDefinition objects for LLM binding
        """
        return self._tools

    def get_status_update(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        """Return a provider-supplied status update for a tool call, if available."""
        provider = self._routing_table.get(tool_name)
        if not provider:
            return None
        try:
            return provider.get_status_update(tool_name, args)
        except Exception:
            logger.exception("Provider.get_status_update failed")
            return None

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Route tool call to appropriate provider.

        Args:
            tool_name: Tool name from LLM
            args: Tool arguments from LLM

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool name not found in routing table
        """
        provider = self._routing_table.get(tool_name)
        if not provider:
            available_tools = list(self._routing_table.keys())
            raise ValueError(
                f"Unknown tool: {tool_name}. "
                f"Available tools ({len(available_tools)}): {available_tools[:10]}..."
            )
        return await provider.resolve_tool_call(tool_name, args)

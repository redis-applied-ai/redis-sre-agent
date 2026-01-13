"""Tool manager for provider lifecycle and routing.

This module provides the ToolManager class which handles:
1. Loading configured tool providers
2. Managing provider lifecycle (async context managers)
3. Building a routing table from tool names to providers
4. Routing LLM tool calls to the correct provider
"""

import logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from opentelemetry import trace

from redis_sre_agent.core.instances import RedisInstance

from .models import Tool, ToolCapability, ToolDefinition
from .protocols import ToolProvider

if TYPE_CHECKING:
    from pathlib import Path
    from redis_sre_agent.tools.cache import ToolCache

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


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

    def __init__(
        self,
        redis_instance: Optional[RedisInstance] = None,
        exclude_mcp_categories: Optional[List[ToolCapability]] = None,
        support_package_path: Optional["Path"] = None,
        cache_client: Optional[Any] = None,
        cache_ttl_overrides: Optional[Dict[str, int]] = None,
    ):
        """Initialize tool manager.

        Args:
            redis_instance: Optional Redis instance to scope tools to
            exclude_mcp_categories: Optional list of MCP tool categories to exclude.
                Use [ToolCapability.UTILITIES] to exclude utility-only MCP tools,
                or pass all capabilities to exclude all MCP tools.
                Common categories: METRICS, LOGS, TICKETS, REPOS, TRACES,
                DIAGNOSTICS, KNOWLEDGE, UTILITIES.
            support_package_path: Optional path to an extracted support package.
                When provided, loads SupportPackageToolProvider with tools for
                analyzing logs, diagnostics, and Redis data from the package.
            cache_client: Optional async Redis client for shared tool result caching.
                When provided, tool outputs are cached across runs with TTL.
            cache_ttl_overrides: Optional custom TTLs for specific tools.
        """
        self.redis_instance = redis_instance
        self.exclude_mcp_categories = exclude_mcp_categories
        self.support_package_path = support_package_path
        # Track loaded provider class paths to avoid duplicates
        self._loaded_provider_paths: set[str] = set()

        # Mapping from tool name -> provider instance
        self._routing_table: Dict[str, ToolProvider] = {}
        # Flattened list of Tool objects from all providers
        self._tools: List[Tool] = []
        # Direct lookup from tool name -> Tool
        self._tool_by_name: Dict[str, Tool] = {}
        # Loaded provider instances (in load order, de-duplicated by class path)
        self._providers: List[ToolProvider] = []
        self._stack: Optional[AsyncExitStack] = None
        # Per-run cache of tool results: (tool_name, stable_args_json) -> result
        self._call_cache: Dict[str, Any] = {}

        # Shared Redis-backed cache (optional)
        self._shared_cache: Optional["ToolCache"] = None
        if cache_client is not None and redis_instance is not None:
            from redis_sre_agent.tools.cache import ToolCache
            self._shared_cache = ToolCache(
                redis_client=cache_client,
                instance_id=redis_instance.id,
                ttl_overrides=cache_ttl_overrides,
            )

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
            itype = (
                self.redis_instance.instance_type.value
                if self.redis_instance.instance_type
                else None
            )
            instance_type = itype or "unknown"
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

        # Load MCP servers (these are always-on and don't require redis_instance)
        # Pass excluded categories to filter which MCP tools are loaded
        await self._load_mcp_providers()

        # Load support package provider if a package path is provided
        if self.support_package_path:
            await self._load_support_package_provider()

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
            # Back-reference so providers can discover peers by capability when needed
            try:
                setattr(provider, "_manager", self)
            except Exception:
                pass

            # Register tools in routing table from the provider's Tool objects
            tools = provider.tools()
            for tool in tools:
                name = tool.metadata.name
                if not name:
                    continue
                self._routing_table[name] = provider
                self._tools.append(tool)
                self._tool_by_name[name] = tool

            # Track provider instance
            self._providers.append(provider)

            # Mark this provider as loaded to avoid duplicates later
            self._loaded_provider_paths.add(provider_path)

            logger.info(f"Loaded provider {provider.provider_name} with {len(tools)} tools")

        except Exception:
            logger.exception(f"Failed to load provider {provider_path}")
            # Don't fail entire manager if one provider fails

    async def _load_mcp_providers(self) -> None:
        """Load MCP tool providers based on configured mcp_servers.

        This method iterates through the mcp_servers configuration and creates
        an MCPToolProvider for each configured server. Tools are filtered based
        on exclude_mcp_categories if specified.
        """
        from redis_sre_agent.core.config import MCPServerConfig, settings

        if not settings.mcp_servers:
            return

        # Build set of excluded capabilities for fast lookup
        excluded_caps = set(self.exclude_mcp_categories or [])
        if excluded_caps:
            logger.info(
                f"MCP tools with these categories will be excluded: {[c.value for c in excluded_caps]}"
            )

        for server_name, server_config in settings.mcp_servers.items():
            try:
                # Convert dict to MCPServerConfig if needed
                if isinstance(server_config, dict):
                    server_config = MCPServerConfig.model_validate(server_config)

                # Skip if already loaded (use a synthetic path for tracking)
                mcp_provider_path = f"mcp:{server_name}"
                if mcp_provider_path in self._loaded_provider_paths:
                    logger.debug(f"MCP provider already loaded, skipping: {server_name}")
                    continue

                # Import and create the MCP provider
                from redis_sre_agent.tools.mcp.provider import MCPToolProvider

                provider = MCPToolProvider(
                    server_name=server_name,
                    server_config=server_config,
                    redis_instance=None,  # MCP providers don't use redis_instance
                )

                # Enter the provider's async context
                provider = await self._stack.enter_async_context(provider)

                # Set back-reference
                try:
                    setattr(provider, "_manager", self)
                except Exception:
                    pass

                # Register tools, filtering by excluded categories
                tools = provider.tools()
                included_count = 0
                excluded_count = 0
                for tool in tools:
                    name = tool.metadata.name
                    if not name:
                        continue
                    # Skip tools whose capability is in the excluded list
                    if tool.metadata.capability in excluded_caps:
                        excluded_count += 1
                        logger.debug(
                            f"Excluding MCP tool '{name}' (capability: {tool.metadata.capability.value})"
                        )
                        continue
                    self._routing_table[name] = provider
                    self._tools.append(tool)
                    self._tool_by_name[name] = tool
                    included_count += 1

                # Track provider
                self._providers.append(provider)
                self._loaded_provider_paths.add(mcp_provider_path)

                if excluded_count > 0:
                    logger.info(
                        f"Loaded MCP provider '{server_name}': {included_count} tools included, "
                        f"{excluded_count} excluded by category filter"
                    )
                else:
                    logger.info(f"Loaded MCP provider '{server_name}' with {included_count} tools")

            except Exception:
                logger.exception(f"Failed to load MCP provider '{server_name}'")
                # Don't fail entire manager if one MCP provider fails

    async def _load_support_package_provider(self) -> None:
        """Load support package tool provider if a package path is configured.

        This method creates a SupportPackageToolProvider for the configured
        support package path, enabling tools for analyzing logs, diagnostics,
        and Redis data from the package.
        """
        if not self.support_package_path:
            return

        try:
            from redis_sre_agent.tools.support_package.provider import (
                SupportPackageToolProvider,
            )

            # Use a synthetic path for tracking
            provider_path = f"support_package:{self.support_package_path}"
            if provider_path in self._loaded_provider_paths:
                logger.debug(
                    f"Support package provider already loaded: {self.support_package_path}"
                )
                return

            # Create and enter the provider's async context
            provider = SupportPackageToolProvider(package_path=self.support_package_path)
            provider = await self._stack.enter_async_context(provider)

            # Set back-reference
            try:
                setattr(provider, "_manager", self)
            except Exception:
                pass

            # Register tools
            tools = provider.tools()
            for tool in tools:
                name = tool.metadata.name
                if not name:
                    continue
                self._routing_table[name] = provider
                self._tools.append(tool)
                self._tool_by_name[name] = tool

            # Track provider
            self._providers.append(provider)
            self._loaded_provider_paths.add(provider_path)

            logger.info(
                f"Loaded support package provider for '{self.support_package_path}' "
                f"with {len(tools)} tools"
            )

        except Exception:
            logger.exception(
                f"Failed to load support package provider for '{self.support_package_path}'"
            )
            # Don't fail entire manager if support package provider fails

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
            provider_class = getattr(module, class_name, None)
            if not provider_class:
                logger.warning(f"Failed to load tool provider class: {provider_path}")
            cls._provider_class_cache[provider_path] = provider_class
        return cls._provider_class_cache[provider_path]

    async def __aexit__(self, *args) -> None:
        """Exit context manager and cleanup all providers and references.

        We explicitly break manager<->provider references and clear routing/caches
        to help GC promptly reclaim objects in long-running processes.
        """
        try:
            if self._stack:
                await self._stack.__aexit__(*args)
        finally:
            # Break back-references from providers to this manager
            providers: List[ToolProvider] = []
            try:
                providers = list(self._providers)
            except Exception:
                providers = []
            for p in providers:
                try:
                    # Break provider -> manager back-reference
                    p._manager = None
                except Exception:
                    pass
            # Clear strong refs held by manager
            self._routing_table.clear()
            self._tools.clear()
            self._tool_by_name.clear()
            self._providers.clear()
            self._loaded_provider_paths.clear()
            self._call_cache.clear()

    # ----- Tool lookup APIs used by LLM bindings -----

    def get_tools(self) -> List[ToolDefinition]:
        """Get all registered tool schemas.

        Returns:
            List of ToolDefinition objects for LLM binding
        """
        return [t.definition for t in self._tools]

    def get_tools_by_provider_names(self, provider_names: List[str]) -> List[ToolDefinition]:
        """Return tools belonging to providers with given provider_name values.

        Args:
            provider_names: List of provider_name strings to include (case-insensitive)

        Returns:
            List of ToolDefinition objects from the selected providers
        """
        try:
            wanted = {str(n).lower() for n in (provider_names or [])}
            if not wanted:
                return []
            results: List[ToolDefinition] = []
            # Filter tools by the provider that registered them
            for tool in self._tools:
                provider = self._routing_table.get(tool.metadata.name)
                pname = provider.provider_name if provider else None
                if isinstance(pname, str) and pname.lower() in wanted:
                    results.append(tool.definition)
            return results
        except Exception:
            # Be conservative; if anything goes wrong, return no tools
            return []

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

    def get_providers_for_capability(self, capability: Any) -> List["ToolProvider"]:
        """Return currently loaded providers that declare a given capability.

        Providers may implement multiple capabilities. The returned list is de-duplicated
        and preserves load order.
        """
        if not isinstance(capability, ToolCapability):
            raise ValueError(f"Invalid capability: {capability}")

        # Unique providers in load order based on tools' capabilities
        seen: set[int] = set()
        ordered_unique: List[ToolProvider] = []
        for tool in self._tools:
            try:
                if tool.metadata.capability is not capability:
                    continue
                provider = self._routing_table.get(tool.metadata.name)
                if not provider:
                    continue
                pid = id(provider)
                if pid in seen:
                    continue
                seen.add(pid)
                ordered_unique.append(provider)
            except Exception:
                continue
        return ordered_unique

    def get_providers_for_protocol(self, protocol_cls: Any) -> List["ToolProvider"]:
        """Return loaded providers that structurally satisfy a typing.Protocol.

        The protocol should be annotated with @runtime_checkable for isinstance() to work.
        """
        # Unique providers in load order
        seen = set()
        ordered_unique: List[ToolProvider] = []
        for provider in self._routing_table.values():
            if id(provider) in seen:
                continue
            seen.add(id(provider))
            try:
                if isinstance(provider, protocol_cls):  # runtime_checkable structural check
                    ordered_unique.append(provider)
            except Exception:
                continue
        return ordered_unique

    def _filter_tools_by_providers(self, providers: List["ToolProvider"]) -> List[ToolDefinition]:
        """Helper: return ToolDefinitions belonging to the given providers."""
        try:
            provider_ids = {id(p) for p in providers or []}
            results: List[ToolDefinition] = []
            for tool in self._tools:
                p = self._routing_table.get(tool.metadata.name)
                if not p or id(p) not in provider_ids:
                    continue
                results.append(tool.definition)
            return results
        except Exception:
            return []

    def get_tools_for_capability(self, capability: Any) -> List[ToolDefinition]:
        """Return tool schemas for providers declaring a capability."""
        providers = self.get_providers_for_capability(capability)
        return self._filter_tools_by_providers(providers)

    def get_tools_for_protocol(self, protocol_cls: Any) -> List[ToolDefinition]:
        """Return tool schemas for providers satisfying a protocol."""
        providers = self.get_providers_for_protocol(protocol_cls)
        return self._filter_tools_by_providers(providers)

    def get_provider_for_capability(self, capability: Any) -> Optional["ToolProvider"]:
        """Return the first provider that declares the capability, or None."""
        providers = self.get_providers_for_capability(capability)
        return providers[0] if providers else None

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Route tool call to appropriate provider with caching.

        Uses both per-run in-memory cache and optional shared Redis cache.
        The shared cache persists across runs and threads for the same instance.

        Args:
            tool_name: Tool name from LLM
            args: Tool arguments from LLM

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool name not found in routing table
        """
        provider = self._routing_table.get(tool_name)
        tool = self._tool_by_name.get(tool_name)
        if not provider or not tool:
            available_tools = list(self._routing_table.keys())
            raise ValueError(
                f"Unknown tool: {tool_name}. "
                f"Available tools ({len(available_tools)}): {available_tools[:10]}..."
            )

        # Stable JSON key for args
        try:
            import json as _json

            args_key = _json.dumps(args or {}, sort_keys=True, separators=(",", ":"))
        except Exception:
            # Fallback to string repr
            args_key = str(args or {})

        # Check per-run in-memory cache first (fastest)
        cache_key = f"{tool_name}|{args_key}"
        if cache_key in self._call_cache:
            return self._call_cache[cache_key]

        # Check shared Redis cache (if enabled)
        if self._shared_cache:
            cached_result = await self._shared_cache.get(tool_name, args or {})
            if cached_result is not None:
                # Also store in per-run cache for faster subsequent lookups
                self._call_cache[cache_key] = cached_result
                return cached_result

        # OTel: per-tool resolve span
        _provider_name = provider.provider_name if provider else None
        _op = None
        try:
            _op = provider.resolve_operation(tool_name, args)  # type: ignore[attr-defined]
        except Exception:
            _op = None
        with tracer.start_as_current_span(
            "tool.resolve",
            attributes={
                "tool.name": tool_name,
                "tool.provider": str(_provider_name) if _provider_name else "",
                "tool.operation": str(_op) if _op else "",
            },
        ):
            result = await tool.invoke(args)

        # Cache result in per-run cache
        self._call_cache[cache_key] = result

        # Cache result in shared Redis cache (if enabled)
        if self._shared_cache:
            await self._shared_cache.set(tool_name, args or {}, result)

        return result

    async def execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Any]:
        """Execute a batch of tool calls returned by an LLM.

        Supports both LangChain-normalized tool_calls (with 'name' and 'args') and
        OpenAI-style tool_calls (with 'function': {'name', 'arguments'}).
        """
        results: List[Any] = []
        for tc in tool_calls or []:
            try:
                # Extract tool name
                name = tc.get("name")
                if not name and isinstance(tc.get("function"), dict):
                    name = tc["function"].get("name")

                # Extract arguments
                args = tc.get("args")
                if args is None and isinstance(tc.get("function"), dict):
                    arguments = tc["function"].get("arguments")
                    if isinstance(arguments, str):
                        try:
                            import json

                            args = json.loads(arguments or "{}")
                        except Exception:
                            args = {}
                    elif isinstance(arguments, dict):
                        args = arguments

                if not isinstance(args, dict):
                    # Last resort: empty args
                    args = {}

                if not name:
                    logger.warning(f"Tool call missing name: {tc}")
                    results.append({"status": "failed", "error": "missing tool name"})
                    continue

                # Execute the tool via routing
                result = await self.resolve_tool_call(name, args)
                results.append(result)
            except Exception as e:
                logger.exception(f"Tool call execution failed for {tc}")
                results.append({"status": "failed", "error": str(e)})
        return results

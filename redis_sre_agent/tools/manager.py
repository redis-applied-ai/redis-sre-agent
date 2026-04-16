"""Tool manager for provider lifecycle and routing.

This module provides the ToolManager class which handles:
1. Loading configured tool providers
2. Managing provider lifecycle (async context managers)
3. Building a routing table from tool names to providers
4. Routing LLM tool calls to the correct provider
"""

import logging
import shutil
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from langgraph.errors import GraphInterrupt
from opentelemetry import trace
from ulid import ULID

from redis_sre_agent.core import clusters as core_clusters
from redis_sre_agent.core.approvals import (
    ActionExecutionLedger,
    ActionExecutionStatus,
    ApprovalManager,
    ApprovalRecord,
    ApprovalRequiredError,
    ApprovalStatus,
    PendingApprovalSummary,
    ToolExecutionDecision,
    ToolExecutionMode,
    approval_expiry_iso,
    build_action_hash,
    build_approval_interrupt_payload,
    build_blocked_tool_result,
    build_tool_args_preview,
)
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.core.runtime_overrides import (
    dispatch_tool_runtime_override,
    get_active_mcp_servers,
    has_active_mcp_server_override,
)
from redis_sre_agent.targets import get_target_handle_store, get_target_integration_registry
from redis_sre_agent.targets.contracts import BindingRequest, ProviderLoadRequest

from .models import Tool, ToolActionKind, ToolCapability, ToolDefinition
from .protocols import ToolProvider

if TYPE_CHECKING:
    from pathlib import Path

    from redis_sre_agent.core.clusters import RedisCluster
    from redis_sre_agent.tools.cache import ToolCache

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
_SENSITIVE_ARG_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "passwd",
    "secret",
    "token",
}


def interrupt(payload: Any) -> Any:
    """Call LangGraph interrupt through a patchable module seam."""

    from langgraph.types import interrupt as langgraph_interrupt

    return langgraph_interrupt(payload)


def _summarize_tool_result(result: Any, *, max_chars: int = 240) -> str:
    """Return a compact execution summary for the audit ledger."""

    if isinstance(result, str):
        rendered = result
    else:
        try:
            import json as _json

            rendered = _json.dumps(result, default=str)
        except Exception:
            rendered = str(result)
    if len(rendered) > max_chars:
        return f"{rendered[:max_chars].rstrip()}..."
    return rendered
def _command_is_available(command: Optional[str]) -> bool:
    """Return True when an executable command is available."""
    if not command:
        return True

    cmd = command.strip()
    if not cmd:
        return False

    # If command includes a path separator, resolve as path.
    if "/" in cmd:
        return Path(cmd).exists()

    return shutil.which(cmd) is not None


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
        "redis_sre_agent.tools.target_discovery.provider.TargetDiscoveryToolProvider",
    ]

    def __init__(
        self,
        redis_instance: Optional[RedisInstance] = None,
        redis_cluster: Optional["RedisCluster"] = None,
        initial_target_bindings: Optional[List[Any]] = None,
        initial_toolset_generation: Optional[int] = None,
        exclude_mcp_categories: Optional[List[ToolCapability]] = None,
        support_package_path: Optional["Path"] = None,
        cache_client: Optional[Any] = None,
        cache_ttl_overrides: Optional[Dict[str, int]] = None,
        thread_id: Optional[str] = None,
        task_id: Optional[str] = None,
        user_id: Optional[str] = None,
        graph_type: str = "agent_turn",
        graph_version: str = "v1",
    ):
        """Initialize tool manager.

        Args:
            redis_instance: Optional Redis instance to scope tools to
            redis_cluster: Optional Redis cluster to scope cluster-level tools to
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
        self.redis_cluster = redis_cluster
        self._initial_target_bindings = list(initial_target_bindings or [])
        self._initial_toolset_generation = initial_toolset_generation
        self.exclude_mcp_categories = exclude_mcp_categories
        self.support_package_path = support_package_path
        self.thread_id = thread_id
        self.task_id = task_id
        self.user_id = user_id
        self.graph_type = graph_type
        self.graph_version = graph_version
        # Track loaded provider keys to avoid duplicate loads while allowing
        # the same provider class to be attached for multiple opaque targets.
        self._loaded_provider_keys: set[str] = set()

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
        self._attached_target_bindings: Dict[str, Any] = {}
        self._toolset_generation = 0

        # Shared Redis-backed cache (optional)
        self._shared_cache: Optional["ToolCache"] = None
        if cache_client is not None and redis_instance is not None:
            from redis_sre_agent.tools.cache import ToolCache

            self._shared_cache = ToolCache(
                redis_client=cache_client,
                instance_id=redis_instance.id,
                ttl_overrides=cache_ttl_overrides,
            )

    @staticmethod
    async def resolve_redis_enterprise_admin_instance(
        redis_instance: RedisInstance,
    ) -> tuple[RedisInstance, str]:
        """Resolve effective Redis Enterprise admin credentials for a RedisInstance.

        Resolution order:
        1. If instance has `cluster_id` and linked RedisCluster is redis_enterprise with
           admin credentials, use cluster credentials.
        2. Fallback to deprecated instance-level admin_* fields.

        Returns:
            Tuple of (effective_instance, credential_source) where credential_source is one of:
            - "cluster"
            - "instance"
            - "missing"
            - "not_enterprise"
        """
        itype = redis_instance.instance_type
        itype_val = itype.value if hasattr(itype, "value") else str(itype or "").strip().lower()
        if itype_val != "redis_enterprise":
            return redis_instance, "not_enterprise"

        cluster_id = (redis_instance.cluster_id or "").strip()
        if cluster_id:
            cluster = await core_clusters.get_cluster_by_id(cluster_id)
            if not cluster:
                logger.warning(
                    "Instance '%s' references cluster_id '%s' but cluster was not found. "
                    "Falling back to deprecated instance admin_* fields.",
                    redis_instance.name,
                    cluster_id,
                )
            else:
                ctype = (
                    cluster.cluster_type.value
                    if hasattr(cluster.cluster_type, "value")
                    else str(cluster.cluster_type or "").strip().lower()
                )
                if ctype != "redis_enterprise":
                    logger.warning(
                        "Instance '%s' references cluster_id '%s' with cluster_type '%s' "
                        "(expected 'redis_enterprise'). Falling back to deprecated instance admin_* fields.",
                        redis_instance.name,
                        cluster_id,
                        ctype,
                    )
                else:
                    has_cluster_admin_url = bool((cluster.admin_url or "").strip())
                    if has_cluster_admin_url:
                        effective_instance = redis_instance.model_copy(
                            update={
                                "admin_url": cluster.admin_url,
                                "admin_username": cluster.admin_username,
                                "admin_password": cluster.admin_password,
                            }
                        )
                        return effective_instance, "cluster"
                    logger.warning(
                        "Cluster '%s' linked from instance '%s' is missing admin_url. "
                        "Falling back to deprecated instance admin_* fields.",
                        cluster_id,
                        redis_instance.name,
                    )

        has_instance_admin_url = bool((redis_instance.admin_url or "").strip())
        if has_instance_admin_url:
            return redis_instance, "instance"

        return redis_instance, "missing"

    async def __aenter__(self) -> "ToolManager":
        """Enter context manager and load all providers."""
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        # Load always-on providers first (these don't require redis_instance)
        for provider_path in self._always_on_providers:
            await self._load_provider(provider_path, always_on=True)

        # Load MCP servers (these are always-on and don't require redis_instance)
        # Pass excluded categories to filter which MCP tools are loaded
        await self._load_mcp_providers()

        # Load support package provider if a package path is provided
        if self.support_package_path:
            await self._load_support_package_provider()

        # Load explicit scope or previously attached thread scope after base tools.
        if self.redis_instance:
            logger.info("Loading instance-specific providers for: %s", self.redis_instance.name)
            await self._load_instance_scoped_providers(self.redis_instance)
        elif self.redis_cluster:
            logger.info(
                "Loading cluster-specific providers for cluster: %s",
                self.redis_cluster.name,
            )
            await self._load_cluster_scoped_providers(self.redis_cluster)
        elif self._initial_target_bindings:
            await self.attach_bound_targets(
                self._initial_target_bindings,
                generation=self._initial_toolset_generation,
            )
        else:
            await self._load_thread_attached_targets()

        self._toolset_generation = max(1, self._toolset_generation)

        logger.info(
            f"ToolManager initialized with {len(self._tools)} tools "
            f"from {len(set(self._routing_table.values()))} providers"
        )

        return self

    async def _load_thread_attached_targets(self) -> None:
        """Load target-scoped providers for any handles already attached to this thread."""
        if not self.thread_id:
            logger.info("No redis_instance provided - loading only instance-independent providers")
            return

        try:
            from redis_sre_agent.core.targets import get_thread_target_state

            target_state = await get_thread_target_state(self.thread_id)
        except Exception:
            logger.exception("Failed to load target bindings for thread %s", self.thread_id)
            return

        if not target_state.target_bindings:
            logger.info("No previously attached targets for thread %s", self.thread_id)
            return

        await self.attach_bound_targets(
            target_state.target_bindings,
            generation=target_state.target_toolset_generation,
        )

    async def _load_instance_scoped_providers(
        self,
        redis_instance: RedisInstance,
        *,
        load_key_prefix: Optional[str] = None,
    ) -> RedisInstance:
        """Load providers that operate with instance-scoped credentials."""
        logger.info("Instance type: %s", redis_instance.instance_type)
        effective_instance = redis_instance
        instance_type = (
            redis_instance.instance_type.value if redis_instance.instance_type else "unknown"
        )

        if instance_type == "redis_enterprise":
            (
                effective_instance,
                enterprise_admin_source,
            ) = await self.resolve_redis_enterprise_admin_instance(redis_instance)
            if enterprise_admin_source == "cluster":
                logger.info(
                    "Using RedisCluster admin credentials for instance '%s' (cluster_id=%s)",
                    effective_instance.name,
                    effective_instance.cluster_id,
                )
            elif enterprise_admin_source == "instance":
                logger.warning(
                    "Using deprecated instance admin_* fields for Redis Enterprise instance '%s'. "
                    "Prefer cluster_id + RedisCluster admin credentials.",
                    effective_instance.name,
                )
        if load_key_prefix is None:
            self.redis_instance = effective_instance

        from redis_sre_agent.core.config import settings

        for provider_path in settings.tool_providers:
            await self._load_provider(
                provider_path,
                redis_instance_override=effective_instance,
                load_key=f"{load_key_prefix or effective_instance.id}:{provider_path}",
            )

        if instance_type == "redis_enterprise":
            has_admin_url = bool(
                effective_instance.admin_url and effective_instance.admin_url.strip()
            )
            if has_admin_url:
                await self._load_provider(
                    "redis_sre_agent.tools.admin.redis_enterprise.provider.RedisEnterpriseAdminToolProvider",
                    redis_instance_override=effective_instance,
                    load_key=f"{load_key_prefix or effective_instance.id}:enterprise_admin",
                )
            else:
                logger.warning(
                    "Redis Enterprise instance '%s' detected but no admin_url configured. "
                    "Enterprise admin tools will not be available.",
                    effective_instance.name,
                )
        elif instance_type == "redis_cloud":
            import os

            has_cloud_credentials = os.getenv("TOOLS_REDIS_CLOUD_API_KEY") and os.getenv(
                "TOOLS_REDIS_CLOUD_API_SECRET_KEY"
            )
            if has_cloud_credentials:
                await self._load_provider(
                    "redis_sre_agent.tools.cloud.redis_cloud.provider.RedisCloudToolProvider",
                    redis_instance_override=effective_instance,
                    load_key=f"{load_key_prefix or effective_instance.id}:redis_cloud",
                )
            else:
                logger.warning(
                    "Redis Cloud instance '%s' detected but no API credentials configured. "
                    "Cloud tools will not be available.",
                    effective_instance.name,
                )
        elif instance_type == "oss_cluster":
            logger.info(
                "OSS Cluster instance detected (cluster-specific tools not yet implemented)"
            )
        elif instance_type == "oss_single":
            logger.info("OSS Single instance detected (using standard Redis CLI tools)")
        else:
            logger.info(
                "Unknown or unspecified instance type '%s' for instance '%s'. Using standard Redis tools.",
                instance_type,
                effective_instance.name,
            )

        return effective_instance

    async def _load_cluster_scoped_providers(self, redis_cluster: "RedisCluster") -> None:
        """Load providers that can operate with cluster-only context."""
        cluster_type = (
            redis_cluster.cluster_type.value
            if hasattr(redis_cluster.cluster_type, "value")
            else str(redis_cluster.cluster_type or "").strip().lower()
        )

        if cluster_type != "redis_enterprise":
            logger.info(
                "Cluster type '%s' has no cluster-only providers to load",
                cluster_type or "unknown",
            )
            return

        admin_instance = self.build_redis_enterprise_admin_instance_from_cluster(redis_cluster)
        if admin_instance is None:
            logger.warning(
                "Redis Enterprise cluster '%s' is missing admin credentials. "
                "Cluster-only admin tools will not be available.",
                redis_cluster.name,
            )
            return

        logger.info(
            "Loading Redis Enterprise admin API provider for cluster '%s'",
            redis_cluster.name,
        )
        await self._load_provider(
            "redis_sre_agent.tools.admin.redis_enterprise.provider.RedisEnterpriseAdminToolProvider",
            redis_instance_override=admin_instance,
            load_key=f"cluster:{redis_cluster.id}:enterprise_admin",
        )

    @staticmethod
    def build_redis_enterprise_admin_instance_from_cluster(
        redis_cluster: "RedisCluster",
        *,
        target_id_override: Optional[str] = None,
    ) -> Optional[RedisInstance]:
        """Build a synthetic RedisInstance for cluster-scoped admin providers."""
        if redis_cluster is None:
            return None

        cluster_type = (
            redis_cluster.cluster_type.value
            if hasattr(redis_cluster.cluster_type, "value")
            else str(redis_cluster.cluster_type or "").strip().lower()
        )
        has_admin_url = bool((redis_cluster.admin_url or "").strip())
        has_admin_username = bool((redis_cluster.admin_username or "").strip())
        has_admin_password = bool(redis_cluster.admin_password)

        if cluster_type != "redis_enterprise" or not (
            has_admin_url and has_admin_username and has_admin_password
        ):
            return None

        connection_host = (redis_cluster.admin_url or "").strip()
        return RedisInstance(
            id=target_id_override or f"cluster-admin::{redis_cluster.id}",
            name=f"{redis_cluster.name} (cluster admin)",
            connection_url="redis://cluster-only.invalid:6379",
            environment=redis_cluster.environment,
            usage="custom",
            description=f"Synthetic cluster admin target for {redis_cluster.name}",
            instance_type="redis_enterprise",
            cluster_id=redis_cluster.id,
            admin_url=redis_cluster.admin_url,
            admin_username=redis_cluster.admin_username,
            admin_password=redis_cluster.admin_password,
            monitoring_identifier=redis_cluster.name,
            logging_identifier=redis_cluster.name,
            notes=f"Cluster-scoped admin tooling target for {connection_host}",
            created_by="agent",
            user_id=redis_cluster.user_id,
        )

    async def _load_provider(
        self,
        provider_path: str,
        always_on: bool = False,
        redis_instance_override: Optional[RedisInstance] = None,
        load_key: Optional[str] = None,
    ) -> None:
        """Load and register a provider.

        Args:
            provider_path: Fully qualified class path
            always_on: If True, initialize without redis_instance (for always-on providers)
            redis_instance_override: Optional instance to use for a single provider load
            load_key: Optional unique key used to de-duplicate loads
        """
        try:
            provider_key = load_key or provider_path
            if provider_key in self._loaded_provider_keys:
                logger.debug("Provider already loaded, skipping duplicate: %s", provider_key)
                return

            provider_cls = self._get_provider_class(provider_path)
            # Always-on providers should not have redis_instance set
            instance = None if always_on else (redis_instance_override or self.redis_instance)
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
            self._loaded_provider_keys.add(provider_key)

            logger.info(f"Loaded provider {provider.provider_name} with {len(tools)} tools")

        except Exception:
            logger.exception(f"Failed to load provider {provider_path}")
            # Don't fail entire manager if one provider fails

    async def _load_provider_request(self, request: ProviderLoadRequest) -> None:
        """Load one provider from a strategy-produced load request."""
        provider_context = request.provider_context or {}
        await self._load_provider(
            request.provider_path,
            always_on=bool(provider_context.get("always_on", False)),
            redis_instance_override=provider_context.get("redis_instance_override"),
            load_key=request.provider_key,
        )

    async def _load_mcp_providers(self) -> None:
        """Load MCP tool providers based on configured mcp_servers.

        This method iterates through the mcp_servers configuration and creates
        an MCPToolProvider for each configured server. Tools are filtered based
        on exclude_mcp_categories if specified.
        """
        from redis_sre_agent.core.config import MCPServerConfig, settings

        mcp_servers = get_active_mcp_servers(settings.mcp_servers)
        if not mcp_servers:
            return

        # Build set of excluded capabilities for fast lookup
        excluded_caps = set(self.exclude_mcp_categories or [])
        if excluded_caps:
            logger.info(
                f"MCP tools with these categories will be excluded: {[c.value for c in excluded_caps]}"
            )

        use_pool = not has_active_mcp_server_override()

        for server_name, server_config in mcp_servers.items():
            try:
                # Convert dict to MCPServerConfig if needed
                if isinstance(server_config, dict):
                    server_config = MCPServerConfig.model_validate(server_config)

                if server_config.command and not _command_is_available(server_config.command):
                    logger.warning(
                        "Skipping MCP provider '%s': command '%s' not found in PATH. "
                        "Configure a valid command or URL transport instead.",
                        server_name,
                        server_config.command,
                    )
                    continue

                # Skip if already loaded (use a synthetic path for tracking)
                mcp_provider_path = f"mcp:{server_name}"
                if mcp_provider_path in self._loaded_provider_keys:
                    logger.debug(f"MCP provider already loaded, skipping: {server_name}")
                    continue

                # Import and create the MCP provider
                from redis_sre_agent.tools.mcp.provider import MCPToolProvider

                provider = MCPToolProvider(
                    server_name=server_name,
                    server_config=server_config,
                    redis_instance=None,  # MCP providers don't use redis_instance
                    use_pool=use_pool,
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
                self._loaded_provider_keys.add(mcp_provider_path)

                if excluded_count > 0:
                    logger.info(
                        f"Loaded MCP provider '{server_name}': {included_count} tools included, "
                        f"{excluded_count} excluded by category filter"
                    )
                else:
                    logger.info(f"Loaded MCP provider '{server_name}' with {included_count} tools")

            except FileNotFoundError as e:
                logger.warning(f"Failed to load MCP provider '{server_name}': {e}")
                # Don't fail entire manager if one MCP provider fails
            except Exception as e:
                logger.error(f"Failed to load MCP provider '{server_name}': {e}")
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
            if provider_path in self._loaded_provider_keys:
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
            self._loaded_provider_keys.add(provider_path)

            logger.info(
                f"Loaded support package provider for '{self.support_package_path}' "
                f"with {len(tools)} tools"
            )

        except Exception:
            logger.exception(
                f"Failed to load support package provider for '{self.support_package_path}'"
            )
            # Don't fail entire manager if support package provider fails

    @staticmethod
    def _build_target_scoped_instance(
        redis_instance: RedisInstance,
        target_handle: str,
    ) -> RedisInstance:
        """Clone an instance with an opaque ID so tool names stay secret-safe."""
        return redis_instance.model_copy(update={"id": target_handle})

    def get_toolset_generation(self) -> int:
        """Return the current toolset generation for dynamic rebinding."""
        return self._toolset_generation

    def get_attached_target_bindings(self) -> List[Any]:
        """Return the currently attached target bindings in load order."""
        return list(self._attached_target_bindings.values())

    async def attach_bound_targets(
        self,
        bindings: List[Any],
        *,
        generation: Optional[int] = None,
    ) -> List[Any]:
        """Attach already-resolved opaque target bindings to this manager."""
        from redis_sre_agent.core.instances import get_instance_by_id

        new_attachment = False
        attached: List[Any] = []
        handle_store = get_target_handle_store()
        registry = get_target_integration_registry()
        requested_handles = [
            getattr(binding, "target_handle", None)
            for binding in bindings or []
            if getattr(binding, "target_handle", None)
        ]
        handle_records = await handle_store.get_records(requested_handles)

        for binding in bindings or []:
            target_handle = getattr(binding, "target_handle", None)
            target_kind = getattr(binding, "target_kind", None)
            resource_id = getattr(binding, "resource_id", None)
            if not target_handle or not target_kind:
                continue

            existing = self._attached_target_bindings.get(target_handle)
            if existing is not None:
                attached.append(existing)
                continue

            handle_record = handle_records.get(target_handle)
            if handle_record is not None:
                binding_result = await registry.get_binding_strategy(
                    handle_record.binding_strategy
                ).bind(
                    BindingRequest(
                        handle_record=handle_record,
                        thread_id=self.thread_id,
                        task_id=self.task_id,
                    )
                )
                if not binding_result.provider_loads:
                    logger.warning(
                        "Unable to attach target handle %s: strategy %s produced no provider loads",
                        target_handle,
                        handle_record.binding_strategy,
                    )
                    continue
                for provider_load in binding_result.provider_loads:
                    await self._load_provider_request(provider_load)
                self._attached_target_bindings[target_handle] = binding_result.public_summary
                attached.append(binding_result.public_summary)
                new_attachment = True
                continue

            if not resource_id:
                logger.warning(
                    "Unable to attach target handle %s: no private handle record or legacy resource_id",
                    target_handle,
                )
                continue

            if target_kind == "instance":
                instance = await get_instance_by_id(resource_id)
                if instance is None:
                    logger.warning(
                        "Unable to attach target handle %s: instance %s not found",
                        target_handle,
                        resource_id,
                    )
                    continue
                scoped_instance = self._build_target_scoped_instance(instance, target_handle)
                await self._load_instance_scoped_providers(
                    scoped_instance,
                    load_key_prefix=f"target:{target_handle}",
                )
            elif target_kind == "cluster":
                cluster = await core_clusters.get_cluster_by_id(resource_id)
                if cluster is None:
                    logger.warning(
                        "Unable to attach target handle %s: cluster %s not found",
                        target_handle,
                        resource_id,
                    )
                    continue
                admin_instance = self.build_redis_enterprise_admin_instance_from_cluster(
                    cluster,
                    target_id_override=target_handle,
                )
                if admin_instance is None:
                    logger.warning(
                        "Unable to attach target handle %s: cluster %s has no supported cluster-only tooling",
                        target_handle,
                        resource_id,
                    )
                    continue
                await self._load_provider(
                    "redis_sre_agent.tools.admin.redis_enterprise.provider.RedisEnterpriseAdminToolProvider",
                    redis_instance_override=admin_instance,
                    load_key=f"target:{target_handle}:enterprise_admin",
                )
            else:
                logger.warning(
                    "Skipping unsupported target binding kind '%s' for %s",
                    target_kind,
                    target_handle,
                )
                continue

            self._attached_target_bindings[target_handle] = binding
            attached.append(binding)
            new_attachment = True

        if generation is not None:
            self._toolset_generation = max(self._toolset_generation, generation)
        elif new_attachment:
            self._toolset_generation += 1

        return attached

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
            self._loaded_provider_keys.clear()
            self._call_cache.clear()
            self._attached_target_bindings.clear()

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

    def _target_handles_for_policy(self) -> List[str]:
        handles = [
            getattr(binding, "target_handle", None)
            for binding in self.get_attached_target_bindings()
            if getattr(binding, "target_handle", None)
        ]
        if handles:
            return [str(handle) for handle in handles]
        if self.redis_instance is not None and getattr(self.redis_instance, "id", None):
            return [str(self.redis_instance.id)]
        if self.redis_cluster is not None and getattr(self.redis_cluster, "id", None):
            return [str(self.redis_cluster.id)]
        return []

    async def evaluate_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> ToolExecutionDecision:
        """Apply approval policy to a tool call before execution."""

        tool = self._tool_by_name.get(tool_name)
        provider = self._routing_table.get(tool_name)
        if not tool or not provider:
            available_tools = list(self._routing_table.keys())
            raise ValueError(
                f"Unknown tool: {tool_name}. "
                f"Available tools ({len(available_tools)}): {available_tools[:10]}..."
            )

        normalized_args = dict(args or {})
        metadata = tool.metadata
        action_kind = metadata.action_kind if metadata is not None else ToolActionKind.UNKNOWN
        if action_kind is ToolActionKind.READ:
            return ToolExecutionDecision(
                mode=ToolExecutionMode.ALLOW,
                tool_name=tool_name,
                tool_args=normalized_args,
            )

        if action_kind is ToolActionKind.UNKNOWN:
            return ToolExecutionDecision(
                mode=ToolExecutionMode.BLOCK,
                tool_name=tool_name,
                tool_args=normalized_args,
                message=f"Blocked {tool_name}: this tool is not classified as read or write yet.",
                result_payload=build_blocked_tool_result(
                    tool_name=tool_name,
                    reason="unclassified_tool",
                    detail="This tool must be explicitly classified before the agent can execute it.",
                ),
            )

        if settings.agent_permission_mode == "read_only":
            return ToolExecutionDecision(
                mode=ToolExecutionMode.BLOCK,
                tool_name=tool_name,
                tool_args=normalized_args,
                message=(
                    f"Blocked {tool_name}: write-capable tools are disabled while "
                    "agent_permission_mode=read_only."
                ),
                result_payload=build_blocked_tool_result(
                    tool_name=tool_name,
                    reason="read_only_mode",
                    detail=(
                        "The agent is running in read-only mode. A human must switch to "
                        "read_write mode before mutating tools can run."
                    ),
                ),
            )

        if not self.task_id or not self.thread_id:
            return ToolExecutionDecision(
                mode=ToolExecutionMode.BLOCK,
                tool_name=tool_name,
                tool_args=normalized_args,
                message=f"Blocked {tool_name}: approval requires task and thread context.",
                result_payload=build_blocked_tool_result(
                    tool_name=tool_name,
                    reason="missing_task_context",
                    detail=(
                        "This execution path cannot pause and resume safely because task context is missing."
                    ),
                ),
            )

        target_handles = self._target_handles_for_policy()
        action_hash = build_action_hash(
            tool_name=tool_name,
            tool_args=normalized_args,
            target_handles=target_handles,
        )
        tool_args_preview = build_tool_args_preview(normalized_args)
        for key in list(tool_args_preview.keys()):
            if str(key).strip().lower() in _SENSITIVE_ARG_KEYS:
                tool_args_preview[key] = "[redacted]"

        approval_manager = ApprovalManager()
        resume_state = await approval_manager.get_resume_state(self.task_id)
        if resume_state and resume_state.pending_approval_id:
            existing_approval = await approval_manager.get_approval(resume_state.pending_approval_id)
            if (
                existing_approval
                and existing_approval.tool_name == tool_name
                and existing_approval.action_hash == action_hash
            ):
                pending_approval = PendingApprovalSummary.from_record(existing_approval)
                if existing_approval.status is ApprovalStatus.APPROVED:
                    return ToolExecutionDecision(
                        mode=ToolExecutionMode.ALLOW,
                        tool_name=tool_name,
                        tool_args=normalized_args,
                        message=f"Using approved action for {tool_name}.",
                        approval_record=existing_approval,
                        pending_approval=pending_approval,
                    )
                if existing_approval.status is ApprovalStatus.REJECTED:
                    return ToolExecutionDecision(
                        mode=ToolExecutionMode.BLOCK,
                        tool_name=tool_name,
                        tool_args=normalized_args,
                        message=f"Blocked {tool_name}: approval was rejected.",
                        approval_record=existing_approval,
                        pending_approval=pending_approval,
                        result_payload=build_blocked_tool_result(
                            tool_name=tool_name,
                            reason="approval_rejected",
                            detail="A human reviewer rejected this tool call.",
                        ),
                    )
                if existing_approval.status is ApprovalStatus.EXPIRED:
                    return ToolExecutionDecision(
                        mode=ToolExecutionMode.BLOCK,
                        tool_name=tool_name,
                        tool_args=normalized_args,
                        message=f"Blocked {tool_name}: approval expired before resume.",
                        approval_record=existing_approval,
                        pending_approval=pending_approval,
                        result_payload=build_blocked_tool_result(
                            tool_name=tool_name,
                            reason="approval_expired",
                            detail="The approval expired before the task resumed.",
                        ),
                    )
                if existing_approval.status is ApprovalStatus.PENDING:
                    return ToolExecutionDecision(
                        mode=ToolExecutionMode.REQUIRE_APPROVAL,
                        tool_name=tool_name,
                        tool_args=normalized_args,
                        message=f"Approval required before executing {tool_name}.",
                        approval_record=existing_approval,
                        pending_approval=pending_approval,
                    )

        approval_record = ApprovalRecord(
            task_id=self.task_id,
            thread_id=self.thread_id,
            graph_thread_id=self.task_id,
            interrupt_id=str(ULID()),
            graph_type=self.graph_type,
            graph_version=self.graph_version,
            tool_name=tool_name,
            tool_args=normalized_args,
            tool_args_preview=tool_args_preview,
            action_kind=action_kind.value,
            action_hash=action_hash,
            target_handles=target_handles,
            expires_at=approval_expiry_iso(settings.agent_approval_ttl_seconds),
        )
        pending_approval = PendingApprovalSummary.from_record(approval_record)
        await approval_manager.create_approval(approval_record)
        return ToolExecutionDecision(
            mode=ToolExecutionMode.REQUIRE_APPROVAL,
            tool_name=tool_name,
            tool_args=normalized_args,
            message=f"Approval required before executing {tool_name}.",
            approval_record=approval_record,
            pending_approval=pending_approval,
        )

    async def resolve_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        *,
        decision: Optional[ToolExecutionDecision] = None,
    ) -> Any:
        """Route tool call to appropriate provider with approval-aware caching."""

        normalized_args = dict(args or {})
        decision = decision or await self.evaluate_tool_call(tool_name, normalized_args)
        if decision.mode is ToolExecutionMode.BLOCK:
            return dict(
                decision.result_payload
                or build_blocked_tool_result(
                    tool_name=tool_name,
                    reason="policy_blocked",
                    detail=decision.message,
                )
            )
        if decision.mode is ToolExecutionMode.REQUIRE_APPROVAL:
            if decision.approval_record is None or decision.pending_approval is None:
                return dict(
                    decision.result_payload
                    or build_blocked_tool_result(
                        tool_name=tool_name,
                        reason="approval_payload_missing",
                        detail="Approval enforcement could not build approval state.",
                    )
                )
            payload = build_approval_interrupt_payload(decision=decision)
            try:
                return interrupt(payload)
            except RuntimeError as exc:
                if "outside of a runnable context" not in str(exc):
                    raise
                raise ApprovalRequiredError(decision=decision, payload=payload) from exc

        provider = self._routing_table.get(tool_name)
        tool = self._tool_by_name.get(tool_name)
        if not provider or not tool:
            available_tools = list(self._routing_table.keys())
            raise ValueError(
                f"Unknown tool: {tool_name}. "
                f"Available tools ({len(available_tools)}): {available_tools[:10]}..."
            )

        _provider_name = provider.provider_name if provider else None
        _op = None
        try:
            _op = provider.resolve_operation(tool_name, normalized_args)  # type: ignore[attr-defined]
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
            override_result = await dispatch_tool_runtime_override(
                tool_name=tool_name,
                args=normalized_args,
                tool_by_name=self._tool_by_name,
                routing_table=self._routing_table,
            )
            if override_result is not None:
                return override_result.result

            action_kind = tool.metadata.action_kind
            try:
                import json as _json

                args_key = _json.dumps(normalized_args, sort_keys=True, separators=(",", ":"))
            except Exception:
                args_key = str(normalized_args)

            cache_key = f"{tool_name}|{args_key}"
            cacheable = action_kind is ToolActionKind.READ
            approval_record = (
                decision.approval_record
                if decision.approval_record is not None
                and decision.approval_record.status is ApprovalStatus.APPROVED
                else None
            )
            approval_manager = None
            ledger = None
            if approval_record is not None:
                approval_manager = ApprovalManager()
                existing_ledger = await approval_manager.get_execution_ledger(
                    approval_record.approval_id,
                    approval_record.action_hash,
                )
                if existing_ledger and existing_ledger.status is ActionExecutionStatus.EXECUTED:
                    return {
                        "status": "already_executed",
                        "tool_name": tool_name,
                        "approval_id": approval_record.approval_id,
                        "action_hash": approval_record.action_hash,
                        "result_summary": existing_ledger.result_summary,
                    }
                ledger = ActionExecutionLedger(
                    approval_id=approval_record.approval_id,
                    task_id=approval_record.task_id,
                    tool_name=tool_name,
                    action_hash=approval_record.action_hash,
                )
                await approval_manager.save_execution_ledger(ledger)
            if cacheable and cache_key in self._call_cache:
                return self._call_cache[cache_key]

            if cacheable and self._shared_cache:
                cached_result = await self._shared_cache.get(tool_name, normalized_args)
                if cached_result is not None:
                    self._call_cache[cache_key] = cached_result
                    return cached_result

            try:
                result = await tool.invoke(normalized_args)
            except Exception as exc:
                if approval_manager is not None and ledger is not None:
                    await approval_manager.save_execution_ledger(
                        ledger.model_copy(
                            update={
                                "status": ActionExecutionStatus.FAILED,
                                "error": str(exc),
                            }
                        )
                    )
                raise

        if cacheable:
            self._call_cache[cache_key] = result

        if cacheable and self._shared_cache:
            await self._shared_cache.set(tool_name, normalized_args, result)

        if approval_manager is not None and ledger is not None:
            await approval_manager.save_execution_ledger(
                ledger.model_copy(
                    update={
                        "status": ActionExecutionStatus.EXECUTED,
                        "executed_at": datetime.now(timezone.utc).isoformat(),
                        "result_summary": _summarize_tool_result(result),
                    }
                )
            )

        return result

    async def execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Any]:
        """Execute a batch of tool calls returned by an LLM."""
        results: List[Any] = []
        for tc in tool_calls or []:
            try:
                name = tc.get("name")
                if not name and isinstance(tc.get("function"), dict):
                    name = tc["function"].get("name")

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
                    args = {}

                if not name:
                    logger.warning(f"Tool call missing name: {tc}")
                    results.append({"status": "failed", "error": "missing tool name"})
                    continue

                decision = await self.evaluate_tool_call(name, args)
                result = await self.resolve_tool_call(name, args, decision=decision)
                results.append(result)
                if (
                    isinstance(result, dict)
                    and result.get("status") == "approval_required"
                    and decision.mode is ToolExecutionMode.REQUIRE_APPROVAL
                ):
                    break
            except (ApprovalRequiredError, GraphInterrupt):
                raise
            except Exception as e:
                logger.exception(f"Tool call execution failed for {tc}")
                results.append({"status": "failed", "error": str(e)})
        return results

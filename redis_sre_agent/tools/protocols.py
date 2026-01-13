"""ABC-based protocols and base classes for tool providers.

This module defines the base ToolProvider ABC, capability enums, lightweight
data classes, and optional Protocols that describe the minimal contracts
HostTelemetry and other orchestrators can program against.
"""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel

from .models import SystemHost, Tool, ToolCapability, ToolDefinition, ToolMetadata

if TYPE_CHECKING:
    from redis_sre_agent.core.instances import RedisInstance

    from .manager import ToolManager


logger = logging.getLogger(__name__)


# --------------------------- Optional provider Protocols ---------------------------
# These describe the minimal contracts higher-level orchestrators can rely on
# without referencing concrete implementations (e.g., Prometheus/Loki).


class MetricsProviderProtocol(Protocol):
    async def query(self, query: str) -> Dict[str, Any]: ...

    async def query_range(
        self, query: str, start_time: str, end_time: str, step: Optional[str] = None
    ) -> Dict[str, Any]: ...


class LogsProviderProtocol(Protocol):
    async def query_range(
        self,
        query: str,
        start: str,
        end: str,
        step: Optional[str] = None,
        limit: Optional[int] = None,
        interval: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> Dict[str, Any]: ...

    async def series(
        self, match: List[str], start: Optional[str] = None, end: Optional[str] = None
    ) -> Dict[str, Any]: ...


@runtime_checkable
class DiagnosticsProviderProtocol(Protocol):
    async def info(self, section: Optional[str] = None) -> Dict[str, Any]: ...
    async def replication_info(self) -> Dict[str, Any]: ...
    async def client_list(self, client_type: Optional[str] = None) -> Dict[str, Any]: ...
    async def system_hosts(self) -> List["SystemHost"]: ...


@runtime_checkable
class KnowledgeProviderProtocol(Protocol):
    async def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
        distance_threshold: Optional[float] = None,
    ) -> Dict[str, Any]: ...
    async def ingest(
        self,
        title: str,
        content: str,
        source: str,
        category: str,
        severity: Optional[str] = None,
        product_labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]: ...
    async def get_all_fragments(self, document_hash: str) -> Dict[str, Any]: ...
    async def get_related_fragments(
        self, document_hash: str, chunk_index: int, limit: int = 10
    ) -> Dict[str, Any]: ...


@runtime_checkable
class UtilitiesProviderProtocol(Protocol):
    async def calculator(self, expression: str) -> Dict[str, Any]: ...
    async def date_math(
        self,
        operation: str,
        date1: Optional[str] = None,
        date2: Optional[str] = None,
        amount: Optional[int] = None,
        unit: Optional[str] = None,
    ) -> Dict[str, Any]: ...
    async def timezone_converter(
        self, datetime_str: str, from_timezone: str, to_timezone: str
    ) -> Dict[str, Any]: ...
    async def http_head(self, url: str, timeout: Optional[float] = 2.0) -> Dict[str, Any]: ...


class ToolProvider(ABC):
    """Base class for all tool providers.

    Tool providers are async context managers that create tools for LLM use.
        Each provider instance generates unique tool names using instance hashing.

        Example:
            class MyToolProvider(ToolProvider):
                @property
                def provider_name(self) -> str:
                    return "my_tool"

                async def do_something(self, param: str) -> Dict[str, Any]:
                    return {"result": f"Did something with {param}"}

                def create_tool_schemas(self) -> List[ToolDefinition]:
                    return [
                        ToolDefinition(
                            name=self._make_tool_name("do_something"),
                            description="Does something useful",
                            capability=ToolCapability.UTILITIES,
                            parameters={...},
                        )
                    ]
    """

    # Capabilities this provider offers. Subclasses should override.
    capabilities: set[ToolCapability] = set()

    # Optional per-provider instance config model and namespace
    # If set, ToolManager/ToolProvider will attempt to parse instance.extension_data
    # and instance.extension_secrets under this namespace and expose it via
    # self.instance_config for provider use.
    instance_config_model: Optional[type[BaseModel]] = None
    extension_namespace: Optional[str] = None  # defaults to provider_name

    # Back-reference to the manager (set by ToolManager on load)
    _manager: Optional["ToolManager"] = None

    def __init__(
        self, redis_instance: Optional["RedisInstance"] = None, config: Optional[Any] = None
    ):
        """Initialize tool provider.

        Args:
            redis_instance: Optional Redis instance to scope tools to
            config: Optional provider-specific configuration
        """
        self.redis_instance = redis_instance
        self.config = config
        self.instance_config: Optional[BaseModel] = None
        # Use stable hash based on instance ID (for caching) or fallback to memory address
        if redis_instance is not None:
            import hashlib
            self._instance_hash = hashlib.sha256(redis_instance.id.encode()).hexdigest()[:6]
        else:
            self._instance_hash = hex(id(self))[2:8]
        # Attempt to load instance-scoped extension config eagerly
        try:
            self.instance_config = self._load_instance_extension_config()
        except Exception:
            # Providers should operate without instance_config
            self.instance_config = None

    # ----- Extension config helpers -----
    def _get_extension_namespace(self) -> str:
        try:
            ns = (self.extension_namespace or self.provider_name or "").strip()
            return ns or ""
        except Exception:
            return ""

    def _load_instance_extension_config(self) -> Optional[BaseModel]:
        """Parse per-instance extension config for this provider, if a model is declared.

        Supports two shapes for both extension_data and extension_secrets on RedisInstance:
        - Namespaced mapping: extension_data[namespace] -> dict
        - Flat keys:         extension_data[f"{namespace}.<key>"] -> value
        For secrets, the value should be SecretStr where possible; plain strings are accepted.
        """
        # No instance or no model -> nothing to do
        if not self.instance_config_model or not self.redis_instance:
            return None
        try:
            ns = self._get_extension_namespace()
            data: Dict[str, Any] = {}
            # Gather data
            try:
                ext = self.redis_instance.extension_data or {}
                if isinstance(ext.get(ns), dict):
                    data.update(ext.get(ns) or {})
                else:
                    # Collect flat keys with prefix 'ns.'
                    prefix = f"{ns}."
                    for k, v in (ext or {}).items():
                        if isinstance(k, str) and k.startswith(prefix):
                            data[k[len(prefix) :]] = v
            except Exception:
                pass
            # Gather secrets
            try:
                sec = self.redis_instance.extension_secrets or {}
                # If secrets are namespaced mapping
                sec_ns = sec.get(ns)
                if isinstance(sec_ns, dict):
                    for k, v in sec_ns.items():
                        data[k] = v  # SecretStr preferred
                else:
                    prefix = f"{ns}."
                    for k, v in (sec or {}).items():
                        if isinstance(k, str) and k.startswith(prefix):
                            data[k[len(prefix) :]] = v
            except Exception:
                pass
            # Validate/construct model
            model_cls = self.instance_config_model  # type: ignore[assignment]
            if not model_cls:
                return None
            return model_cls.model_validate(data or {})  # type: ignore[attr-defined]
        except Exception:
            return None

    def resolve_operation(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        """Map a tool_name to a provider method name.

        The default implementation reverses :meth:`_make_tool_name` and
        returns the *operation* portion of the tool name:

        ``{provider_name}_{instance_hash}_{operation} -> operation``

        Providers can override this for more complex mappings (for example,
        when multiple tool names share a single implementation).

        Note: This method is used for OTel tracing and status updates, not for
        routing. The ToolManager validates tool existence via the routing table
        before this is called.
        """
        import logging

        _logger = logging.getLogger(__name__)

        try:
            # Preferred fast-path: exact prefix match based on provider name
            # and this instance's hash.
            prefix = f"{self.provider_name}_{self._instance_hash}_"
            if tool_name.startswith(prefix):
                return tool_name[len(prefix) :]

            # Fallback: join everything after provider/hash. This keeps
            # backwards compatibility with historical naming schemes such as
            # "redis_command_abcdef_cluster_info".
            parts = tool_name.split("_")
            if len(parts) >= 3:
                return "_".join(parts[2:])

            # Last resort: treat the whole name as the operation.
            # Log a warning since this may indicate a misconfigured tool name.
            _logger.warning(
                f"resolve_operation falling back to full tool name '{tool_name}' as operation. "
                f"Expected format: {self.provider_name}_<hash>_<operation>"
            )
            return tool_name
        except Exception as e:
            _logger.warning(f"resolve_operation failed for '{tool_name}': {e}")
            return None

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider type name (e.g., 'prometheus', 'github_tickets').

        This is used as a prefix for tool names.
        """
        ...

    async def __aenter__(self) -> "ToolProvider":
        """Enter async context manager.

        Override this if your provider needs to set up resources
        (e.g., open database connections, initialize clients).

        Returns:
            Self
        """
        return self

    async def __aexit__(self, *args) -> None:
        """Exit async context manager.

        Override this if your provider needs to clean up resources
        (e.g., close connections, cleanup temp files).
        """
        pass

    def _make_tool_name(self, operation: str) -> str:
        """Create unique tool name with instance hash.

        Format: {provider_name}_{instance_hash}_{operation}

        The instance hash uniquely identifies the instance, so the instance name
        is not needed and causes problems with parsing (e.g., when instance names
        contain underscores).

        Args:
            operation: Tool operation name (e.g., 'query_metrics', 'create_ticket')

        Returns:
            Unique tool name matching pattern ^[a-zA-Z0-9_-]+$
        """
        return f"{self.provider_name}_{self._instance_hash}_{operation}"

    # ----- Core tool APIs -----

    def create_tool_schemas(self) -> List["ToolDefinition"]:
        """Create ToolDefinition schemas for this provider.

        Providers that implement this method can rely on the default
        :meth:`tools` implementation, which builds :class:`Tool` objects
        using the capability declared on each :class:`ToolDefinition`.
        Providers with special needs can still override :meth:`tools`.
        """

        raise NotImplementedError(
            f"{self.__class__.__name__}.create_tool_schemas() is not implemented; "
            "either override create_tool_schemas() or override tools()."
        )

    @property
    def requires_redis_instance(self) -> bool:
        """Whether this provider's tools require a Redis instance.

        Returns ``True`` if the provider was initialized with a ``redis_instance``.
        Subclasses can override to always return ``True`` or ``False`` regardless
        of initialization.
        """
        return self.redis_instance is not None

    def tools(self) -> List["Tool"]:
        """Return the concrete tools exposed by this provider.

        The default implementation builds :class:`Tool` objects from
        :meth:`create_tool_schemas`, using the ``capability`` on each
        :class:`ToolDefinition` and :attr:`requires_redis_instance` to
        populate :class:`ToolMetadata`.

        Each tool's :pyattr:`Tool.invoke` closure is wired directly to the
        corresponding provider method (for example, ``query_range`` on a
        Prometheus provider), so no additional per-provider routing is required.

        Providers with special requirements (for example, per-tool
        ``requires_instance`` flags or non-standard execution) can still
        override this method.
        """
        # Get schemas from provider. Providers that override ``tools`` may
        # ignore :meth:`create_tool_schemas` entirely.
        schemas: List[ToolDefinition] = self.create_tool_schemas()

        tools: List["Tool"] = []
        for schema in schemas:
            capability = schema.capability
            if capability is None:
                raise ValueError(
                    f"ToolDefinition {schema.name!r} is missing capability; "
                    "capability is now a required field on ToolDefinition."
                )

            meta = ToolMetadata(
                name=schema.name,
                description=schema.description,
                capability=capability,
                provider_name=self.provider_name,
                requires_instance=self.requires_redis_instance,
            )

            # Derive operation name and look up the corresponding method.
            op_name = self.resolve_operation(schema.name, {}) or ""
            method = getattr(self, op_name, None) if op_name else None

            if not callable(method):
                raise RuntimeError(
                    f"Provider {self.__class__.__name__} has no method {op_name!r} "
                    f"for tool {schema.name!r}. Define an async {op_name}() method "
                    "or override tools() to provide a custom implementation."
                )

            # Capture method via default arg to avoid late binding in the closure.
            async def _invoke(args: Dict[str, Any], _method=method) -> Any:
                return await _method(**(args or {}))

            tools.append(Tool(metadata=meta, definition=schema, invoke=_invoke))
        return tools

    def get_status_update(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        """Optional natural-language status update for this tool call.

        If a provider method corresponding to this tool call is decorated
        with @status_update("..."), this uses the template to render a
        per-call status message via Python str.format(**args).
        Providers can override this for full control.
        """
        try:
            op = self.resolve_operation(tool_name, args)
            if not op:
                logger.warning(f"get_status_update failed to resolve operation for {tool_name}")
                return None
            method = self.__dict__.get(op) or type(self).__dict__.get(op)
            if not method:
                return None
            template = getattr(method, "_status_update_template", None)
            if not template:
                return None
            try:
                return template.format(**args)
            except Exception:
                return template
        except Exception:
            return None

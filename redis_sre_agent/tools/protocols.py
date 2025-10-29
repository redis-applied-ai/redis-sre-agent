"""ABC-based protocols and base classes for tool providers.

This module defines the base ToolProvider ABC, capability enums, lightweight
data classes, and optional Protocols that describe the minimal contracts
HostTelemetry and other orchestrators can program against.
"""

import weakref
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:
    from redis_sre_agent.core.instances import RedisInstance

    from .manager import ToolManager
    from .tool_definition import ToolDefinition


class ToolCapability(Enum):
    """Capabilities that tools can provide."""

    METRICS = "metrics"
    LOGS = "logs"
    TICKETS = "tickets"
    REPOS = "repos"
    TRACES = "traces"
    DIAGNOSTICS = "diagnostics"  # For deep instance diagnostics (Redis INFO, key sampling, etc.)
    KNOWLEDGE = "knowledge"  # Knowledge base search/ingest and fragment retrieval
    UTILITIES = "utilities"  # Non-destructive utility functions (calc, date/time, http_head)


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


# --------------------------- Lightweight data classes ---------------------------


class MetricValue:
    """Represents a metric value with timestamp."""

    def __init__(
        self,
        value: float | int,
        timestamp: Optional[datetime] = None,
        labels: Optional[Dict[str, str]] = None,
    ):
        self.value = value
        self.timestamp = timestamp or datetime.now()
        self.labels = labels or {}


class MetricDefinition:
    """Defines a metric with metadata."""

    def __init__(self, name: str, description: str, unit: str, metric_type: str = "gauge"):
        self.name = name
        self.description = description
        self.unit = unit
        self.metric_type = metric_type  # gauge, counter, histogram, etc.


class TimeRange:
    """Represents a time range for queries."""

    def __init__(self, start: datetime, end: datetime):
        self.start = start
        self.end = end


class LogEntry:
    """Represents a log entry."""

    def __init__(
        self,
        timestamp: datetime,
        level: str,
        message: str,
        source: str,
        labels: Optional[Dict[str, str]] = None,
    ):
        self.timestamp = timestamp
        self.level = level
        self.message = message
        self.source = source
        self.labels = labels or {}


class SystemHost(BaseModel):
    """Represents a system host target for metrics/logs discovery.

    This describes where the Redis system is running (nodes, primaries/replicas,
    cluster nodes, or Enterprise machines), not necessarily database endpoints.
    """

    host: str
    port: Optional[int] = None
    role: Optional[str] = None  # e.g., single, master, replica, cluster-master, enterprise-node
    labels: Dict[str, str] = {}


class Ticket:
    """Represents a ticket/issue."""

    def __init__(
        self,
        id: str,
        title: str,
        description: str,
        status: str,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ):
        self.id = id
        self.title = title
        self.description = description
        self.status = status
        self.assignee = assignee
        self.labels = labels or []


class Repository:
    """Represents a code repository."""

    def __init__(
        self,
        name: str,
        url: str,
        default_branch: str = "main",
        languages: Optional[List[str]] = None,
    ):
        self.name = name
        self.url = url
        self.default_branch = default_branch
        self.languages = languages or []


class TraceSpan:
    """Represents a trace span."""

    def __init__(
        self,
        trace_id: str,
        span_id: str,
        operation_name: str,
        start_time: datetime,
        duration_ms: float,
        tags: Optional[Dict[str, str]] = None,
    ):
        self.trace_id = trace_id
        self.span_id = span_id
        self.operation_name = operation_name
        self.start_time = start_time
        self.duration_ms = duration_ms
        self.tags = tags or {}


class ToolProvider(ABC):
    """Base class for all tool providers.

    Tool providers are async context managers that create tools for LLM use.
    Each provider instance generates unique tool names using instance hashing.

    Example:
        class MyToolProvider(ToolProvider):
            provider_name = "my_tool"

            def create_tool_schemas(self) -> List[ToolDefinition]:
                return [
                    ToolDefinition(
                        name=self._make_tool_name("do_something"),
                        description="Does something useful",
                        parameters={...},
                    )
                ]

            async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
                if "do_something" in tool_name:
                    return await self.do_something(**args)
                raise ValueError(f"Unknown tool: {tool_name}")

            async def do_something(self, param: str) -> Dict[str, Any]:
                return {"result": f"Did something with {param}"}
    """

    # Capabilities this provider offers. Subclasses should override.
    capabilities: set[ToolCapability] = set()

    # Optional per-provider instance config model and namespace
    # If set, ToolManager/ToolProvider will attempt to parse instance.extension_data
    # and instance.extension_secrets under this namespace and expose it via
    # self.instance_config for provider use.
    instance_config_model: Optional[type[BaseModel]] = None
    extension_namespace: Optional[str] = None  # defaults to provider_name

    # Weak back-reference to the manager (set by ToolManager on load)
    _manager_ref: Optional[Any] = None

    @property
    def _manager(self) -> Optional["ToolManager"]:
        """Dynamically resolve the ToolManager from a weak reference.

        Back-compat: property name matches legacy attribute so providers that
        do getattr(self, "_manager", None) keep working without changes.
        """
        try:
            ref = getattr(self, "_manager_ref", None)
            return ref() if ref else None
        except Exception:
            return None

    @_manager.setter
    def _manager(self, manager: Optional["ToolManager"]) -> None:
        """Setter accepts a strong manager and stores a weakref to avoid cycles."""
        try:
            self._manager_ref = weakref.ref(manager) if manager is not None else None
        except Exception:
            self._manager_ref = None

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
        if not getattr(self, "instance_config_model", None) or not self.redis_instance:
            return None
        try:
            ns = self._get_extension_namespace()
            data: Dict[str, Any] = {}
            # Gather data
            try:
                ext = getattr(self.redis_instance, "extension_data", None) or {}
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
                sec = getattr(self.redis_instance, "extension_secrets", None) or {}
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

        Default implementation returns the last underscore-delimited token
        from the tool name. Providers can override to handle more complex
        mappings (e.g., 'config_get', 'client_list').
        """
        try:
            return tool_name.split("_")[-1]
        except Exception:
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

    @abstractmethod
    def create_tool_schemas(self) -> List["ToolDefinition"]:
        """Create tool schemas for this provider.

        Each tool should have a unique name (use _make_tool_name helper).
        If redis_instance is set, tools should be scoped to that instance
        (e.g., don't expose instance URL parameters in the schema).

        Returns:
            List of ToolDefinition objects with unique names
        """
        ...

    @abstractmethod
    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a tool call and return the result.

        This method receives the full tool name (including hash) and arguments
        from the LLM. It should dispatch to the appropriate method and return
        the result.

        Args:
            tool_name: Full tool name (e.g., 'prometheus_a3f2b1_query_metrics')
            args: Tool arguments from LLM

        Returns:
            Tool execution result (will be serialized to JSON for LLM)

        Raises:
            ValueError: If tool_name is not recognized
        """
        ...

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
                return None
            method = getattr(self, op, None)
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

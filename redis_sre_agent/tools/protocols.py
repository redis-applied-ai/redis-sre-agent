"""ABC-based protocols for tool providers.

This module defines the base ToolProvider ABC and supporting data classes
for metrics, logs, tickets, and other SRE tool capabilities.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from redis_sre_agent.api.instances import RedisInstance

    from .tool_definition import ToolDefinition


class ToolCapability(Enum):
    """Capabilities that tools can provide."""

    METRICS = "metrics"
    LOGS = "logs"
    TICKETS = "tickets"
    REPOS = "repos"
    TRACES = "traces"
    DIAGNOSTICS = "diagnostics"  # For deep instance diagnostics (Redis INFO, key sampling, etc.)


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
        self._instance_hash = hex(id(self))[2:8]

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

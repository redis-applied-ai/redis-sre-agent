import re
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class ToolActionKind(str, Enum):
    """Behavioral classification used by HITL policy enforcement."""

    READ = "read"
    WRITE = "write"
    UNKNOWN = "unknown"


_READ_PREFIXES = (
    "get_",
    "list_",
    "query_",
    "search_",
    "find_",
    "read_",
    "inspect_",
    "describe_",
)
_WRITE_PREFIXES = (
    "create_",
    "update_",
    "delete_",
    "remove_",
    "add_",
    "upload_",
    "move_",
    "restart_",
    "stop_",
    "start_",
    "enable_",
    "disable_",
    "approve_",
    "resume_",
    "retry_",
    "cancel_",
    "set_",
    "link_",
    "unlink_",
    "transition_",
    "attach_",
    "detach_",
    "failover_",
)
_READ_EXACT = {
    "acl_log",
    "auth_status",
    "client_list",
    "config_get",
    "info",
    "logs",
    "rebalance_status",
    "slowlog",
}
_READ_DESCRIPTION_MARKERS = (
    "get ",
    "list ",
    "query ",
    "search ",
    "read ",
    "inspect ",
    "retrieve ",
    "returns ",
)
_WRITE_DESCRIPTION_MARKERS = (
    "create ",
    "update ",
    "delete ",
    "remove ",
    "add ",
    "upload ",
    "move ",
    "restart ",
    "enable ",
    "disable ",
    "approve ",
    "resume ",
    "retry ",
    "cancel ",
    "set ",
    "link ",
    "unlink ",
    "transition ",
    "attach ",
    "detach ",
    "overwrite ",
    "modify ",
)


def _description_starts_with_marker(description: str, markers: tuple[str, ...]) -> bool:
    normalized = description.strip().lower()
    return any(normalized.startswith(marker) for marker in markers)


def _extract_operation_name(tool_name: str, provider_name: str) -> str:
    prefix_pattern = rf"^{re.escape(provider_name)}_[^_]+_"
    if re.match(prefix_pattern, tool_name):
        return re.sub(prefix_pattern, "", tool_name, count=1)
    # MCP providers sometimes pass the already-resolved operation name (for
    # example "_create_branch" or "list_pull_requests"). Preserve that
    # verb-bearing form instead of splitting it again and dropping the action
    # token.
    if provider_name.startswith("mcp_") or tool_name.startswith("_"):
        return tool_name
    parts = tool_name.split("_")
    if len(parts) >= 3:
        return "_".join(parts[2:])
    return tool_name


def infer_tool_action_kind(
    *,
    name: str,
    description: str,
    capability: ToolCapability,
    provider_name: str,
) -> ToolActionKind:
    """Infer the approval-relevant action kind for a tool.

    Providers default to conservative name/description inference. Callers can
    still override the result explicitly when a tool needs stricter handling.
    """

    operation = _extract_operation_name(name, provider_name).lower().lstrip("_")
    description_lower = description.lower()

    if operation in _READ_EXACT:
        return ToolActionKind.READ
    if operation.startswith(_WRITE_PREFIXES):
        return ToolActionKind.WRITE
    if operation.startswith(_READ_PREFIXES):
        return ToolActionKind.READ
    if _description_starts_with_marker(description_lower, _READ_DESCRIPTION_MARKERS):
        return ToolActionKind.READ
    if _description_starts_with_marker(description_lower, _WRITE_DESCRIPTION_MARKERS):
        return ToolActionKind.WRITE
    if capability in {
        ToolCapability.METRICS,
        ToolCapability.LOGS,
        ToolCapability.TRACES,
        ToolCapability.KNOWLEDGE,
        ToolCapability.UTILITIES,
    }:
        return ToolActionKind.READ
    return ToolActionKind.UNKNOWN


class ToolMetadata(BaseModel):
    """Metadata about a concrete tool implementation.

    This is attached to the :class:`Tool` wrapper alongside the
    :class:`ToolDefinition` schema and the callable used to execute the tool.
    """

    name: str
    description: str
    capability: ToolCapability
    provider_name: str
    requires_instance: bool = False
    action_kind: Optional[ToolActionKind] = None

    @model_validator(mode="after")
    def populate_action_kind(self) -> "ToolMetadata":
        if self.action_kind is None:
            self.action_kind = infer_tool_action_kind(
                name=self.name,
                description=self.description,
                capability=self.capability,
                provider_name=self.provider_name,
            )
        return self


class Tool(BaseModel):
    """Concrete tool object combining definition, metadata, and executor.

    Attributes:
        metadata: :class:`ToolMetadata` describing the tool for routing.
        definition: The :class:`ToolDefinition` shown to the LLM.
        invoke: Async callable taking a single ``Dict[str, Any]`` of arguments
            and returning the tool result.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    metadata: ToolMetadata
    definition: "ToolDefinition"
    invoke: Callable[[Dict[str, Any]], Awaitable[Any]]


class SystemHost(BaseModel):
    """Represents a system host target for metrics/logs discovery.

    This describes where the Redis system is running (nodes, primaries/replicas,
    cluster nodes, or Enterprise machines), not necessarily database endpoints.
    """

    host: str
    port: Optional[int] = None
    role: Optional[str] = None  # e.g., single, master, replica, cluster-master, enterprise-node
    labels: Dict[str, str] = {}


class ToolDefinition(BaseModel):
    """Definition of a tool that the LLM can call.

    This is a pure schema object - it describes the tool to the LLM but
    does not contain the execution logic. Execution happens via ToolManager
    routing the tool call to the appropriate ToolProvider.

    Example:
        tool = ToolDefinition(
            name="prometheus_a3f2b1_query_metrics",
            description="Query Prometheus metrics for a specific metric name",
            capability=ToolCapability.METRICS,
            parameters={
                "type": "object",
                "properties": {
                    "metric_name": {
                        "type": "string",
                        "description": "Name of the metric to query"
                    }
                },
                "required": ["metric_name"]
            }
        )
    """

    name: str = Field(
        ...,
        description="Unique tool name with provider and instance hash",
    )

    description: str = Field(
        ...,
        description="Verbose description for the LLM on when and how to use this tool",
    )

    parameters: Dict[str, Any] = Field(
        ...,
        description="JSON schema for tool parameters (OpenAI function calling format)",
    )

    capability: ToolCapability = Field(
        ...,
        description=(
            "High-level capability category for this tool (e.g., METRICS, LOGS, "
            "DIAGNOSTICS, UTILITIES, KNOWLEDGE)."
        ),
    )

    class Config:
        """Pydantic configuration."""

        extra = "forbid"

    def __str__(self) -> str:
        """String representation."""
        return f"ToolDefinition(name={self.name})"

    def __repr__(self) -> str:
        """Detailed representation."""
        param_names = list(self.parameters.get("properties", {}).keys())
        return f"ToolDefinition(name={self.name}, parameters={param_names})"

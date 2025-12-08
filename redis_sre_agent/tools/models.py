from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


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


class ToolMetadata(BaseModel):
    """Metadata about a concrete tool implementation.

    This is attached to the :class:`Tool` wrapper alongside the
    :class:`~redis_sre_agent.tools.tool_definition.ToolDefinition` schema
    and the callable used to execute the tool.
    """

    name: str
    description: str
    capability: ToolCapability
    provider_name: str
    requires_instance: bool = False


class Tool(BaseModel):
    """Concrete tool object combining schema, metadata, and executor.

    Attributes:
        metadata: :class:`ToolMetadata` describing the tool for routing.
        schema: The :class:`ToolDefinition` shown to the LLM (stored as ``Any``
            here to avoid import cycles).
        invoke: Async callable taking a single ``Dict[str, Any]`` of arguments
            and returning the tool result.
    """

    metadata: ToolMetadata
    schema: Any
    invoke: Any


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

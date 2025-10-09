"""Tool definition model for LLM-callable functions.

This module defines the structure of tools that are exposed to the LLM.
Each tool has a name, description, and parameters schema. Execution happens
via ToolManager routing to the appropriate ToolProvider.
"""

from typing import Any, Dict

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """Definition of a tool that the LLM can call.

    This is a pure schema object - it describes the tool to the LLM but
    does not contain the execution logic. Execution happens via ToolManager
    routing the tool call to the appropriate ToolProvider.

    Example:
        tool = ToolDefinition(
            name="prometheus_a3f2b1_query_metrics",
            description="Query Prometheus metrics for a specific metric name",
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

    class Config:
        """Pydantic configuration."""

        extra = "forbid"

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling schema.

        Returns:
            Dictionary in OpenAI function calling format
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def __str__(self) -> str:
        """String representation."""
        return f"ToolDefinition(name={self.name})"

    def __repr__(self) -> str:
        """Detailed representation."""
        param_names = list(self.parameters.get("properties", {}).keys())
        return f"ToolDefinition(name={self.name}, parameters={param_names})"

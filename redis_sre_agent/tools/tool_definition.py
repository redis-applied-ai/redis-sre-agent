"""Tool definition model for LLM-callable functions.

This module defines the structure of tools that are exposed to the LLM.
Each tool has a name, description, parameters schema, and an executable function.
"""

from typing import Any, Callable, Dict

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """Definition of a tool that the LLM can call.

    Tools are discrete, named functions with verbose descriptions that provide
    context to the LLM about when and how to use them.
    """

    name: str = Field(
        ...,
        description="Unique tool name. Should be descriptive and include instance identifier if scoped.",
    )

    description: str = Field(
        ...,
        description="Verbose description with instructions for the LLM on when and how to use this tool.",
    )

    parameters: Dict[str, Any] = Field(
        ...,
        description="JSON schema for tool parameters (OpenAI function calling format)",
    )

    function: Callable = Field(
        ...,
        description="The actual async function to call when the tool is invoked",
    )

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True  # Allow Callable type

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

    async def call(self, **kwargs) -> Any:
        """Call the tool function with provided arguments.

        Args:
            **kwargs: Arguments to pass to the function

        Returns:
            Result from the function
        """
        return await self.function(**kwargs)

    def __str__(self) -> str:
        """String representation."""
        return f"ToolDefinition(name={self.name})"

    def __repr__(self) -> str:
        """Detailed representation."""
        param_names = list(self.parameters.get("properties", {}).keys())
        return f"ToolDefinition(name={self.name}, parameters={param_names})"

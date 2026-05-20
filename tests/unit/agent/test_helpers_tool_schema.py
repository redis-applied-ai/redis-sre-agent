"""Round-trip tests for build_adapters_for_tooldefs schema generation.

Regression coverage for the case where ToolDefinition.parameters declared
JSON Schema property types but those types were stripped on the wire because
_args_model_from_parameters used a blanket Any annotation.
"""

from langchain_core.utils.function_calling import convert_to_openai_tool

from redis_sre_agent.agent.helpers import build_adapters_for_tooldefs
from redis_sre_agent.tools.models import ToolCapability, ToolDefinition


def _property_has_type(prop: dict, expected: str) -> bool:
    """True if ``prop`` declares ``expected`` as its JSON Schema type.

    Accepts both the direct form ``{"type": "string"}`` and the
    ``Optional[T]`` form Pydantic emits, ``{"anyOf": [{"type": "string"},
    {"type": "null"}]}``.
    """
    if prop.get("type") == expected:
        return True
    for branch in prop.get("anyOf", []) or []:
        if isinstance(branch, dict) and branch.get("type") == expected:
            return True
    return False


async def test_build_adapters_preserves_property_types_on_wire():
    tdef = ToolDefinition(
        name="kb_search_fixture",
        description="Fixture tool for schema round-trip test",
        capability=ToolCapability.KNOWLEDGE,
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 10,
                },
                "distance_threshold": {
                    "type": "number",
                    "description": "Optional distance threshold",
                },
            },
            "required": ["query"],
        },
    )

    adapters = await build_adapters_for_tooldefs(None, [tdef])
    assert len(adapters) == 1

    schema = convert_to_openai_tool(adapters[0])
    props = schema["function"]["parameters"]["properties"]

    assert _property_has_type(props["query"], "string"), props["query"]
    assert _property_has_type(props["limit"], "integer"), props["limit"]
    assert _property_has_type(props["distance_threshold"], "number"), props["distance_threshold"]


async def test_build_adapters_falls_back_to_any_when_source_has_no_type():
    """MCP-published schemas can omit `type`. We should keep the field
    callable rather than fabricating a type the source did not declare."""
    tdef = ToolDefinition(
        name="mcp_untyped_fixture",
        description="Fixture for property with no declared type",
        capability=ToolCapability.UTILITIES,
        parameters={
            "type": "object",
            "properties": {
                "payload": {"description": "Free-form payload, no type"},
            },
            "required": [],
        },
    )

    adapters = await build_adapters_for_tooldefs(None, [tdef])
    assert len(adapters) == 1

    schema = convert_to_openai_tool(adapters[0])
    props = schema["function"]["parameters"]["properties"]

    assert "payload" in props
    assert "type" not in props["payload"] and "anyOf" not in props["payload"]

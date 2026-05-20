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


async def test_build_adapters_accepts_type_union_form():
    """Properties declared as `{"type": ["string", "null"]}` (the strict-mode
    and common MCP form) must not crash adapter construction, and the concrete
    type should survive the round-trip."""
    tdef = ToolDefinition(
        name="union_type_fixture",
        description="Fixture for type-union nullable property",
        capability=ToolCapability.UTILITIES,
        parameters={
            "type": "object",
            "properties": {
                "label": {"type": ["string", "null"], "description": "Nullable label"},
            },
            "required": [],
        },
    )

    adapters = await build_adapters_for_tooldefs(None, [tdef])
    assert len(adapters) == 1

    schema = convert_to_openai_tool(adapters[0])
    props = schema["function"]["parameters"]["properties"]

    assert _property_has_type(props["label"], "string"), props["label"]


async def test_non_required_single_type_list_accepts_default_none():
    """A non-required property declared as `{"type": ["string"]}` (no "null"
    in the union) must still be Optional[T] so the Pydantic field default of
    None validates against the annotation when the LLM omits the parameter."""
    tdef = ToolDefinition(
        name="single_type_list_fixture",
        description="Fixture for non-required single-element type-list",
        capability=ToolCapability.UTILITIES,
        parameters={
            "type": "object",
            "properties": {
                "label": {"type": ["string"], "description": "Non-required label"},
            },
            "required": [],
        },
    )

    adapters = await build_adapters_for_tooldefs(None, [tdef])
    assert len(adapters) == 1

    # Instantiating with no args must not raise; default None must validate.
    model = adapters[0].args_schema
    instance = model()
    assert instance.label is None

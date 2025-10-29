from langchain_core.messages import ToolMessage

from redis_sre_agent.agent.helpers import build_result_envelope


class _ToolDef:
    def __init__(self, description: str):
        self.description = description


def test_build_result_envelope_parses_json_content():
    tool_name = "knowledge.kb.search"
    tool_args = {"q": "redis cluster"}
    msg = ToolMessage(content='Result: {"alpha": 1}', tool_call_id="abc")
    tooldefs = {tool_name: _ToolDef(description="Search the knowledge base")}

    env = build_result_envelope(tool_name, tool_args, msg, tooldefs)

    assert env["tool_key"] == tool_name
    assert env["name"] == "search"
    assert env["args"] == tool_args
    assert env["description"] == "Search the knowledge base"
    assert env["data"] == {"alpha": 1}


def test_build_result_envelope_fallbacks_to_raw():
    tool_name = "knowledge.kb.search"
    tool_args = {"q": "redis cluster"}
    msg = ToolMessage(content="no json here", tool_call_id="def")
    tooldefs = {tool_name: _ToolDef(description="Search the knowledge base")}

    env = build_result_envelope(tool_name, tool_args, msg, tooldefs)

    assert env["data"]["raw"].startswith("no json here")

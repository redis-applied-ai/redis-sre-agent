from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from redis_sre_agent.agent.helpers import sanitize_messages_for_llm


def test_sanitize_drops_leading_tool_and_orphans():
    # Orphan ToolMessage (no matching AI tool_call id) should be dropped
    orphan_tool = ToolMessage(content="{}", tool_call_id="abc")
    msgs = [orphan_tool, HumanMessage(content="hi")]  # tool-first and orphan

    clean = sanitize_messages_for_llm(msgs)
    assert clean, "Sanitizer should return a non-empty list when there are non-tool messages"
    assert not isinstance(clean[0], ToolMessage), "First message should not be a ToolMessage"
    # Orphan tool should be removed entirely
    assert all(not isinstance(m, ToolMessage) for m in clean)


def test_sanitize_keeps_matched_tool_messages():
    # AI asks for a tool with id "abc"; subsequent ToolMessage with matching id is kept
    ai = AIMessage(content="ok", tool_calls=[{"id": "abc", "name": "fake.tool", "args": {}}])
    tool = ToolMessage(content='{"ok": true}', tool_call_id="abc")
    clean = sanitize_messages_for_llm([HumanMessage(content="x"), ai, tool])

    # Order preserved (except potential leading tool drops); ensure ToolMessage present
    assert any(isinstance(m, ToolMessage) for m in clean), "Matched ToolMessage should be preserved"

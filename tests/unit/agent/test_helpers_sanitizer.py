from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from redis_sre_agent.agent.helpers import (
    _compact_messages_tail,
    sanitize_messages_for_llm,
)


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


def test_sanitize_empty_list():
    """Test sanitizing empty message list."""
    clean = sanitize_messages_for_llm([])
    assert clean == []


def test_sanitize_preserves_human_messages():
    """Test that human messages are preserved."""
    msgs = [HumanMessage(content="hello"), HumanMessage(content="world")]
    clean = sanitize_messages_for_llm(msgs)
    assert len(clean) == 2
    assert all(isinstance(m, HumanMessage) for m in clean)


def test_sanitize_preserves_system_messages():
    """Test that system messages are preserved."""
    msgs = [SystemMessage(content="You are helpful"), HumanMessage(content="hi")]
    clean = sanitize_messages_for_llm(msgs)
    assert len(clean) == 2
    assert isinstance(clean[0], SystemMessage)


def test_sanitize_multiple_tool_calls():
    """Test with AI message having multiple tool calls."""
    ai = AIMessage(
        content="",
        tool_calls=[
            {"id": "call1", "name": "tool1", "args": {}},
            {"id": "call2", "name": "tool2", "args": {}},
        ],
    )
    tool1 = ToolMessage(content="result1", tool_call_id="call1")
    tool2 = ToolMessage(content="result2", tool_call_id="call2")
    msgs = [HumanMessage(content="x"), ai, tool1, tool2]

    clean = sanitize_messages_for_llm(msgs)
    tool_msgs = [m for m in clean if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 2


def test_sanitize_tool_call_id_from_dict():
    """Test extracting tool_call_id from dict format."""
    # Use 'id' key which is the standard format
    ai = AIMessage(
        content="",
        tool_calls=[{"id": "alt_id", "name": "tool", "args": {}}],
    )
    tool = ToolMessage(content="result", tool_call_id="alt_id")
    msgs = [HumanMessage(content="x"), ai, tool]

    clean = sanitize_messages_for_llm(msgs)
    assert any(isinstance(m, ToolMessage) for m in clean)


class TestCompactMessagesTail:
    """Test _compact_messages_tail function."""

    def test_empty_messages(self):
        """Test with empty message list."""
        result = _compact_messages_tail([])
        assert result == []

    def test_limits_to_n_messages(self):
        """Test that only last N messages are returned."""
        msgs = [HumanMessage(content=f"msg{i}") for i in range(10)]
        result = _compact_messages_tail(msgs, limit=3)
        assert len(result) == 3

    def test_includes_role(self):
        """Test that role is included in compact output."""
        msgs = [HumanMessage(content="hello")]
        result = _compact_messages_tail(msgs)
        assert result[0]["role"] == "human"

    def test_ai_message_with_tool_calls(self):
        """Test AI message with tool calls."""
        ai = AIMessage(
            content="",
            tool_calls=[{"id": "call1", "name": "tool", "args": {}}],
        )
        result = _compact_messages_tail([ai])
        assert "tool_calls" in result[0]
        assert "call1" in result[0]["tool_calls"]

    def test_tool_message_info(self):
        """Test tool message includes tool_call_id and name."""
        tool = ToolMessage(content="result", tool_call_id="xyz", name="my_tool")
        result = _compact_messages_tail([tool])
        assert result[0]["tool_call_id"] == "xyz"
        assert result[0]["name"] == "my_tool"

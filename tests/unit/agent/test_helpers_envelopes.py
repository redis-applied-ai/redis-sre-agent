from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import ToolMessage

from redis_sre_agent.agent.helpers import (
    build_adapters_for_tooldefs,
    build_result_envelope,
    log_preflight_messages,
    parse_json_maybe_fenced,
    parse_tool_json_payload,
    summarize_signals,
)


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


def test_build_result_envelope_no_tool_def():
    """Test envelope building without tool definition."""
    msg = ToolMessage(content='{"status": "ok"}', tool_call_id="xyz")
    env = build_result_envelope("unknown.tool", {}, msg, {})

    assert env["tool_key"] == "unknown.tool"
    assert env["description"] is None


def test_build_result_envelope_empty_tool_name():
    """Test envelope with empty tool name."""
    msg = ToolMessage(content='{"data": 123}', tool_call_id="xyz")
    env = build_result_envelope("", {}, msg, {})

    assert env["tool_key"] == "tool"
    assert env["name"] == "tool"


class TestParseJsonMaybeFenced:
    """Test parse_json_maybe_fenced function."""

    def test_plain_json(self):
        """Test parsing plain JSON."""
        result = parse_json_maybe_fenced('{"key": "value"}')
        assert result == {"key": "value"}

    def test_fenced_json(self):
        """Test parsing JSON with code fences."""
        result = parse_json_maybe_fenced('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_fenced_json_with_lang(self):
        """Test parsing JSON with json language specifier."""
        result = parse_json_maybe_fenced('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_invalid_json_raises(self):
        """Test that invalid JSON raises JSONDecodeError."""
        with pytest.raises(Exception):
            parse_json_maybe_fenced("not json")


class TestSummarizeSignals:
    """Test summarize_signals function."""

    def test_empty_signals(self):
        """Test with empty signals dict."""
        result = summarize_signals({})
        assert result == "- No tool signals captured"

    def test_simple_signals(self):
        """Test with simple signals."""
        signals = {"status": "ok", "count": 42}
        result = summarize_signals(signals)
        assert "- status: ok" in result
        assert "- count: 42" in result

    def test_dict_value_signals(self):
        """Test with dict values in signals."""
        signals = {"data": {"nested": "value"}}
        result = summarize_signals(signals)
        assert "data:" in result
        assert "nested" in result

    def test_truncates_at_max_items(self):
        """Test that signals are truncated at max_items."""
        signals = {f"key{i}": i for i in range(20)}
        result = summarize_signals(signals, max_items=5)
        assert "truncated" in result


class TestParseToolJsonPayload:
    """Test parse_tool_json_payload function."""

    def test_parses_result_json(self):
        """Test parsing JSON after Result: label."""
        payload = 'Some text Result: {"key": "value"}'
        result = parse_tool_json_payload(payload)
        assert result == {"key": "value"}

    def test_no_result_label(self):
        """Test with no Result: label."""
        payload = '{"key": "value"}'
        result = parse_tool_json_payload(payload)
        assert result is None

    def test_no_json_after_result(self):
        """Test with Result: but no JSON."""
        payload = "Result: no json here"
        result = parse_tool_json_payload(payload)
        assert result is None

    def test_invalid_json(self):
        """Test with invalid JSON after Result:."""
        payload = "Result: {broken json"
        result = parse_tool_json_payload(payload)
        assert result is None


class TestLogPreflightMessages:
    """Test log_preflight_messages function."""

    def test_logs_successfully(self):
        """Test logging with mock logger."""
        from langchain_core.messages import HumanMessage

        mock_logger = MagicMock()
        msgs = [HumanMessage(content="hello")]
        log_preflight_messages(msgs, label="Test", logger=mock_logger)
        mock_logger.debug.assert_called_once()

    def test_with_note(self):
        """Test logging with note parameter."""
        from langchain_core.messages import HumanMessage

        mock_logger = MagicMock()
        msgs = [HumanMessage(content="hello")]
        log_preflight_messages(msgs, label="Test", note="attempt 1", logger=mock_logger)
        call_args = mock_logger.debug.call_args[0][0]
        assert "attempt 1" in call_args


class TestBuildAdaptersForTooldefs:
    """Test build_adapters_for_tooldefs function."""

    @pytest.mark.asyncio
    async def test_builds_adapters(self):
        """Test building adapters from tool definitions."""

        class MockToolDef:
            name = "test.tool"
            description = "A test tool"
            parameters = {
                "properties": {"arg1": {"description": "First arg"}},
                "required": ["arg1"],
            }

        mock_manager = MagicMock()
        mock_manager.resolve_tool_call = AsyncMock(return_value={"result": "ok"})

        adapters = await build_adapters_for_tooldefs(mock_manager, [MockToolDef()])

        assert len(adapters) == 1
        assert adapters[0].name == "test.tool"

    @pytest.mark.asyncio
    async def test_empty_tooldefs(self):
        """Test with empty tool definitions."""
        mock_manager = MagicMock()
        adapters = await build_adapters_for_tooldefs(mock_manager, [])
        assert adapters == []

    @pytest.mark.asyncio
    async def test_none_tooldefs(self):
        """Test with None tool definitions."""
        mock_manager = MagicMock()
        adapters = await build_adapters_for_tooldefs(mock_manager, None)
        assert adapters == []

"""Tests for the thread CLI commands.

These tests cover:
- thread get (viewing threads with messages)
- thread trace (viewing decision traces for messages)
- thread list (listing threads)
"""

import json
from unittest.mock import patch

from click.testing import CliRunner

from redis_sre_agent.cli.main import main as cli_main
from redis_sre_agent.core.threads import (
    Message,
    Thread,
    ThreadMetadata,
)


def _make_thread_with_messages(thread_id: str = "thread-1") -> Thread:
    """Create a thread with messages including assistant message with message_id."""
    return Thread(
        thread_id=thread_id,
        messages=[
            Message(
                message_id="01HX1234567890ABCDEFGHJK",
                role="user",
                content="What is causing high memory usage?",
            ),
            Message(
                message_id="01HX9876543210ZYXWVUTSRQ",
                role="assistant",
                content="Based on my analysis, the high memory is due to...",
                metadata={"task_id": "task-abc"},
            ),
        ],
        context={},
        metadata=ThreadMetadata(subject="Memory investigation"),
    )


def _make_decision_trace():
    """Create a sample decision trace."""
    return {
        "message_id": "01HX9876543210ZYXWVUTSRQ",
        "tool_envelopes": [
            {
                "tool_key": "redis_tools",
                "name": "redis_info",
                "description": "Get Redis INFO",
                "args": {"section": "memory"},
                "status": "success",
                "data": {"used_memory": "1GB"},
                "summary": "Retrieved memory info showing 1GB used",
            },
            {
                "tool_key": "knowledge_tools",
                "name": "knowledge_search",
                "description": "Search knowledge base",
                "args": {"query": "memory optimization"},
                "status": "success",
                "data": {
                    "results": [
                        {
                            "title": "Memory Best Practices",
                            "source": "redis.io",
                            "score": 0.95,
                            "id": "doc-123",
                        }
                    ]
                },
                "summary": "Found 1 relevant document",
            },
        ],
        "otel_trace_id": "abc123def456",
        "created_at": "2024-01-15T10:30:00Z",
    }


class TestThreadGet:
    """Tests for the 'thread get' command."""

    def test_thread_get_shows_message_id_column(self):
        """Test that thread get displays Message ID column for assistant messages."""
        runner = CliRunner()
        thread = _make_thread_with_messages()

        async def fake_get_thread(_self, thread_id: str):  # noqa: ARG001
            return thread

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.get_thread",
            new=fake_get_thread,
        ):
            result = runner.invoke(cli_main, ["thread", "get", "thread-1"])

        assert result.exit_code == 0, result.output
        # Should show Message ID column header
        assert "Message ID" in result.output
        # Should show truncated message_id for assistant message
        assert "01HX98765432..." in result.output
        # Should include hint about thread trace
        assert "thread trace <message_id>" in result.output

    def test_thread_get_json_output(self):
        """Test thread get with JSON output."""
        runner = CliRunner()
        thread = _make_thread_with_messages()

        async def fake_get_thread(_self, thread_id: str):  # noqa: ARG001
            return thread

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.get_thread",
            new=fake_get_thread,
        ):
            result = runner.invoke(cli_main, ["thread", "get", "thread-1", "--json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["thread_id"] == "thread-1"
        assert len(data["messages"]) == 2
        # Check message_id is present
        assert data["messages"][0]["message_id"] == "01HX1234567890ABCDEFGHJK"
        assert data["messages"][1]["message_id"] == "01HX9876543210ZYXWVUTSRQ"

    def test_thread_get_not_found(self):
        """Test thread get when thread doesn't exist."""
        runner = CliRunner()

        async def fake_get_thread(_self, thread_id: str):  # noqa: ARG001
            return None

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.get_thread",
            new=fake_get_thread,
        ):
            result = runner.invoke(cli_main, ["thread", "get", "nonexistent"])

        assert result.exit_code == 0  # CLI doesn't exit with error
        assert "not found" in result.output.lower()


class TestThreadTrace:
    """Tests for the 'thread trace' command."""

    def test_thread_trace_shows_tool_calls(self):
        """Test that thread trace displays tool calls from the trace."""
        runner = CliRunner()
        trace = _make_decision_trace()

        async def fake_get_message_trace(_self, message_id: str):  # noqa: ARG001
            return trace

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.get_message_trace",
            new=fake_get_message_trace,
        ):
            result = runner.invoke(cli_main, ["thread", "trace", "01HX9876543210ZYXWVUTSRQ"])

        assert result.exit_code == 0, result.output
        # Should show trace header with message_id
        assert "Decision Trace for Message:" in result.output
        assert "01HX9876543210ZYXWVUTSRQ" in result.output
        # Should show tool names
        assert "redis_info" in result.output
        assert "knowledge_search" in result.output
        # Should show status
        assert "success" in result.output
        # Should show OTel trace ID
        assert "abc123def456" in result.output

    def test_thread_trace_json_output(self):
        """Test thread trace with JSON output."""
        runner = CliRunner()
        trace = _make_decision_trace()

        async def fake_get_message_trace(_self, message_id: str):  # noqa: ARG001
            return trace

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.get_message_trace",
            new=fake_get_message_trace,
        ):
            result = runner.invoke(
                cli_main, ["thread", "trace", "01HX9876543210ZYXWVUTSRQ", "--json"]
            )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["message_id"] == "01HX9876543210ZYXWVUTSRQ"
        assert len(data["tool_envelopes"]) == 2
        assert data["tool_envelopes"][0]["name"] == "redis_info"

    def test_thread_trace_not_found(self):
        """Test thread trace when no trace exists for message."""
        runner = CliRunner()

        async def fake_get_message_trace(_self, message_id: str):  # noqa: ARG001
            return None

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.get_message_trace",
            new=fake_get_message_trace,
        ):
            result = runner.invoke(cli_main, ["thread", "trace", "nonexistent-msg"])

        assert result.exit_code == 0
        assert "No decision trace found" in result.output
        assert "nonexistent-msg" in result.output

    def test_thread_trace_shows_citations(self):
        """Test that thread trace shows citations derived from knowledge tools."""
        runner = CliRunner()
        trace = _make_decision_trace()

        async def fake_get_message_trace(_self, message_id: str):  # noqa: ARG001
            return trace

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.get_message_trace",
            new=fake_get_message_trace,
        ):
            result = runner.invoke(cli_main, ["thread", "trace", "01HX9876543210ZYXWVUTSRQ"])

        assert result.exit_code == 0, result.output
        # Should show citations section
        assert "Citations" in result.output
        # Should show citation details
        assert "Memory Best Practices" in result.output
        assert "redis.io" in result.output

    def test_thread_trace_with_show_data(self):
        """Test thread trace with --show-data flag."""
        runner = CliRunner()
        trace = _make_decision_trace()

        async def fake_get_message_trace(_self, message_id: str):  # noqa: ARG001
            return trace

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.get_message_trace",
            new=fake_get_message_trace,
        ):
            result = runner.invoke(
                cli_main,
                ["thread", "trace", "01HX9876543210ZYXWVUTSRQ", "--show-data"],
            )

        assert result.exit_code == 0, result.output
        # Should show full tool results
        assert "Full Tool Results" in result.output
        # Should show data from tool output
        assert "used_memory" in result.output

    def test_thread_trace_json_not_found(self):
        """Test thread trace JSON output when no trace exists."""
        runner = CliRunner()

        async def fake_get_message_trace(_self, message_id: str):  # noqa: ARG001
            return None

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.get_message_trace",
            new=fake_get_message_trace,
        ):
            result = runner.invoke(cli_main, ["thread", "trace", "nonexistent-msg", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "error" in data
        assert "nonexistent-msg" in data["error"]

    def test_thread_trace_no_tool_calls(self):
        """Test thread trace when trace has no tool envelopes."""
        runner = CliRunner()
        trace = {
            "message_id": "01HX9876543210ZYXWVUTSRQ",
            "tool_envelopes": [],
            "otel_trace_id": None,
            "created_at": "2024-01-15T10:30:00Z",
        }

        async def fake_get_message_trace(_self, message_id: str):  # noqa: ARG001
            return trace

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.get_message_trace",
            new=fake_get_message_trace,
        ):
            result = runner.invoke(cli_main, ["thread", "trace", "01HX9876543210ZYXWVUTSRQ"])

        assert result.exit_code == 0, result.output
        assert "No tool calls recorded" in result.output
        assert "No citations recorded" in result.output


class TestThreadList:
    """Tests for the 'thread list' command."""

    def test_thread_list_shows_threads(self):
        """Test that thread list displays threads."""
        runner = CliRunner()

        async def fake_list_threads(
            _self,
            user_id=None,  # noqa: ARG001
            instance_id=None,  # noqa: ARG001
            limit=50,  # noqa: ARG001
            offset=0,  # noqa: ARG001
        ):
            return [
                {
                    "thread_id": "thread-1",
                    "subject": "Memory investigation",
                    "created_at": "2024-01-15T10:00:00Z",
                    "updated_at": "2024-01-15T10:30:00Z",
                    "message_count": 5,
                }
            ]

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.list_threads",
            new=fake_list_threads,
        ):
            result = runner.invoke(cli_main, ["thread", "list"])

        assert result.exit_code == 0, result.output
        assert "thread-1" in result.output
        assert "Memory investigation" in result.output

    def test_thread_list_json_output(self):
        """Test thread list with JSON output."""
        runner = CliRunner()

        async def fake_list_threads(
            _self,
            user_id=None,  # noqa: ARG001
            instance_id=None,  # noqa: ARG001
            limit=50,  # noqa: ARG001
            offset=0,  # noqa: ARG001
        ):
            return [
                {
                    "thread_id": "thread-1",
                    "subject": "Memory investigation",
                    "created_at": "2024-01-15T10:00:00Z",
                    "updated_at": "2024-01-15T10:30:00Z",
                    "message_count": 5,
                }
            ]

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.list_threads",
            new=fake_list_threads,
        ):
            result = runner.invoke(cli_main, ["thread", "list", "--json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["thread_id"] == "thread-1"

    def test_thread_list_empty(self):
        """Test thread list when no threads exist."""
        runner = CliRunner()

        async def fake_list_threads(
            _self,
            user_id=None,  # noqa: ARG001
            instance_id=None,  # noqa: ARG001
            limit=50,  # noqa: ARG001
            offset=0,  # noqa: ARG001
        ):
            return []

        with patch(
            "redis_sre_agent.core.threads.ThreadManager.list_threads",
            new=fake_list_threads,
        ):
            result = runner.invoke(cli_main, ["thread", "list"])

        assert result.exit_code == 0, result.output
        assert "No threads found" in result.output

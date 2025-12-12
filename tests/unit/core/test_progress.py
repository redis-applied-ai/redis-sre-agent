"""Unit tests for the progress emission system."""

import asyncio
import logging
from io import StringIO
from unittest.mock import AsyncMock, MagicMock

import pytest

from redis_sre_agent.core.progress import (
    CallbackEmitter,
    CLIEmitter,
    CompositeEmitter,
    LocalProgressCounter,
    LoggingEmitter,
    NullEmitter,
    ProgressEmitter,
    TaskEmitter,
    create_emitter,
)


class TestProgressEmitterProtocol:
    """Test the ProgressEmitter protocol."""

    def test_null_emitter_is_progress_emitter(self):
        """NullEmitter should satisfy the ProgressEmitter protocol."""
        emitter = NullEmitter()
        assert isinstance(emitter, ProgressEmitter)

    def test_logging_emitter_is_progress_emitter(self):
        """LoggingEmitter should satisfy the ProgressEmitter protocol."""
        emitter = LoggingEmitter()
        assert isinstance(emitter, ProgressEmitter)

    def test_cli_emitter_is_progress_emitter(self):
        """CLIEmitter should satisfy the ProgressEmitter protocol."""
        emitter = CLIEmitter()
        assert isinstance(emitter, ProgressEmitter)


class TestLocalProgressCounter:
    """Test the LocalProgressCounter."""

    @pytest.mark.asyncio
    async def test_counter_starts_at_one(self):
        """Counter should start at 1."""
        counter = LocalProgressCounter()
        value = await counter.next()
        assert value == 1

    @pytest.mark.asyncio
    async def test_counter_increments(self):
        """Counter should increment on each call."""
        counter = LocalProgressCounter()
        assert await counter.next() == 1
        assert await counter.next() == 2
        assert await counter.next() == 3

    @pytest.mark.asyncio
    async def test_counter_thread_safety(self):
        """Counter should be thread-safe with asyncio.Lock."""
        counter = LocalProgressCounter()
        results = []

        async def increment():
            for _ in range(10):
                results.append(await counter.next())

        # Run multiple concurrent incrementers
        await asyncio.gather(increment(), increment(), increment())

        # Should have 30 unique, sequential values
        assert len(results) == 30
        assert sorted(results) == list(range(1, 31))


class TestNullEmitter:
    """Test the NullEmitter."""

    @pytest.mark.asyncio
    async def test_emit_does_nothing(self):
        """NullEmitter.emit should not raise and do nothing."""
        emitter = NullEmitter()
        # Should not raise
        await emitter.emit("test message", "progress", {"key": "value"})


class TestLoggingEmitter:
    """Test the LoggingEmitter."""

    @pytest.mark.asyncio
    async def test_emit_logs_message(self, caplog):
        """LoggingEmitter should log messages."""
        emitter = LoggingEmitter(level=logging.INFO)

        with caplog.at_level(logging.INFO):
            await emitter.emit("Test message", "tool_call")

        assert "[tool_call] Test message" in caplog.text


class TestCLIEmitter:
    """Test the CLIEmitter."""

    @pytest.mark.asyncio
    async def test_emit_prints_to_file(self):
        """CLIEmitter should print to the specified file."""
        output = StringIO()
        emitter = CLIEmitter(use_colors=False, file=output)

        await emitter.emit("Test message", "progress")

        output.seek(0)
        result = output.read()
        assert "Test message" in result

    @pytest.mark.asyncio
    async def test_emit_with_different_types(self):
        """CLIEmitter should use different symbols for different types."""
        output = StringIO()
        emitter = CLIEmitter(use_colors=False, file=output)

        await emitter.emit("Starting", "agent_start")
        await emitter.emit("Tool", "tool_call")
        await emitter.emit("Done", "agent_complete")

        output.seek(0)
        result = output.read()
        assert "🚀" in result  # agent_start
        assert "🔧" in result  # tool_call
        assert "✅" in result  # agent_complete

    def test_colorize_disabled(self):
        """Colors should be disabled when use_colors=False."""
        output = StringIO()
        emitter = CLIEmitter(use_colors=False, file=output)

        result = emitter._colorize("test", "blue")
        assert result == "test"  # No ANSI codes


class TestTaskEmitter:
    """Test the TaskEmitter."""

    @pytest.mark.asyncio
    async def test_emit_calls_task_manager(self):
        """TaskEmitter should call task_manager.add_task_update."""
        mock_task_manager = MagicMock()
        mock_task_manager.add_task_update = AsyncMock()

        emitter = TaskEmitter(task_manager=mock_task_manager, task_id="task-123")

        await emitter.emit("Progress update", "progress", {"key": "value"})

        mock_task_manager.add_task_update.assert_called_once_with(
            "task-123", "Progress update", "progress", {"key": "value"}
        )

    def test_task_id_property(self):
        """TaskEmitter should expose task_id property."""
        mock_task_manager = MagicMock()
        emitter = TaskEmitter(task_manager=mock_task_manager, task_id="task-456")

        assert emitter.task_id == "task-456"

    @pytest.mark.asyncio
    async def test_emit_handles_errors_gracefully(self):
        """TaskEmitter should not raise if task_manager fails."""
        mock_task_manager = MagicMock()
        mock_task_manager.add_task_update = AsyncMock(side_effect=Exception("Redis error"))

        emitter = TaskEmitter(task_manager=mock_task_manager, task_id="task-123")

        # Should not raise
        await emitter.emit("Progress update", "progress")


class TestCompositeEmitter:
    """Test the CompositeEmitter."""

    @pytest.mark.asyncio
    async def test_emit_calls_all_emitters(self):
        """CompositeEmitter should call emit on all child emitters."""
        emitter1 = MagicMock()
        emitter1.emit = AsyncMock()
        emitter2 = MagicMock()
        emitter2.emit = AsyncMock()

        composite = CompositeEmitter([emitter1, emitter2])

        await composite.emit("Test message", "progress", {"key": "value"})

        emitter1.emit.assert_called_once_with("Test message", "progress", {"key": "value"})
        emitter2.emit.assert_called_once_with("Test message", "progress", {"key": "value"})

    @pytest.mark.asyncio
    async def test_emit_continues_on_error(self):
        """CompositeEmitter should continue even if one emitter fails."""
        emitter1 = MagicMock()
        emitter1.emit = AsyncMock(side_effect=Exception("Failed"))
        emitter2 = MagicMock()
        emitter2.emit = AsyncMock()

        composite = CompositeEmitter([emitter1, emitter2])

        # Should not raise
        await composite.emit("Test message", "progress")

        # Second emitter should still be called
        emitter2.emit.assert_called_once()


class TestCallbackEmitter:
    """Test the CallbackEmitter for backward compatibility."""

    @pytest.mark.asyncio
    async def test_emit_calls_callback(self):
        """CallbackEmitter should forward to callback."""
        callback = AsyncMock()
        emitter = CallbackEmitter(callback)

        await emitter.emit("Test message", "progress", {"key": "value"})

        callback.assert_called_once_with("Test message", "progress", {"key": "value"})

    @pytest.mark.asyncio
    async def test_emit_handles_callback_without_metadata(self):
        """CallbackEmitter should handle callbacks that don't accept metadata."""

        async def simple_callback(msg, update_type):
            pass

        emitter = CallbackEmitter(simple_callback)

        # Should not raise (falls back to 2-arg call)
        await emitter.emit("Test message", "progress", {"key": "value"})

    @pytest.mark.asyncio
    async def test_emit_with_none_callback(self):
        """CallbackEmitter should handle None callback gracefully."""
        emitter = CallbackEmitter(None)

        # Should not raise
        await emitter.emit("Test message", "progress")


class TestCreateEmitterFactory:
    """Test the create_emitter factory function."""

    def test_returns_null_emitter_when_no_args(self):
        """create_emitter with no args should return NullEmitter."""
        emitter = create_emitter()
        assert isinstance(emitter, NullEmitter)

    def test_returns_cli_emitter_when_cli_true(self):
        """create_emitter with cli=True should return CLIEmitter."""
        emitter = create_emitter(cli=True)
        assert isinstance(emitter, CLIEmitter)

    def test_returns_task_emitter_when_task_args(self):
        """create_emitter with task args should return TaskEmitter."""
        mock_task_manager = MagicMock()
        emitter = create_emitter(task_id="task-123", task_manager=mock_task_manager)
        assert isinstance(emitter, TaskEmitter)

    def test_returns_composite_when_multiple(self):
        """create_emitter with multiple destinations should return CompositeEmitter."""
        mock_task_manager = MagicMock()
        emitter = create_emitter(
            task_id="task-123",
            task_manager=mock_task_manager,
            cli=True,
        )
        assert isinstance(emitter, CompositeEmitter)

    def test_returns_single_emitter_when_one_destination(self):
        """create_emitter should not wrap single emitter in CompositeEmitter."""
        emitter = create_emitter(cli=True)
        # Should be CLIEmitter directly, not CompositeEmitter([CLIEmitter])
        assert isinstance(emitter, CLIEmitter)
        assert not isinstance(emitter, CompositeEmitter)

    def test_includes_additional_emitters(self):
        """create_emitter should include additional_emitters."""
        extra = NullEmitter()
        emitter = create_emitter(cli=True, additional_emitters=[extra])
        assert isinstance(emitter, CompositeEmitter)

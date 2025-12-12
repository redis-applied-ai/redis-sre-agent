"""Progress emission abstraction for agent status updates.

This module provides a ProgressEmitter protocol that abstracts how progress/status
updates (notifications) are emitted during agent execution. Different implementations
can send updates to different destinations:

- TaskEmitter: Persists notifications to a Task in Redis. Clients poll the task
               for status and notifications. This is the primary implementation for
               both REST and MCP paths.
- MCPEmitter: Sends MCP protocol progress notifications (for synchronous MCP tools)
- CompositeEmitter: Combines multiple emitters for simultaneous delivery
- NullEmitter: No-op emitter for testing or batch jobs
- LoggingEmitter: Logs updates for debugging

Architecture:
    - Notifications (tool reflections, progress) → Task updates (via TaskEmitter)
    - Final result → Task result AND Thread message (handled by docket_tasks)
    - Clients (REST or MCP) poll get_task_status() for notifications and status

Example:
    # Docket worker path (REST and MCP both use this)
    emitter = TaskEmitter(task_manager, task_id)
    agent = SRELangGraphAgent(progress_emitter=emitter)
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redis_sre_agent.core.tasks import TaskManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Progress Counter (for MCP's monotonically increasing requirement)
# ---------------------------------------------------------------------------


class ProgressCounter(ABC):
    """Abstract counter for generating monotonically increasing progress values."""

    @abstractmethod
    async def next(self) -> int:
        """Get the next progress value. Must always return a value > previous."""
        ...


class LocalProgressCounter(ProgressCounter):
    """Thread-safe monotonic counter for single-process scenarios.

    Uses an asyncio.Lock to ensure concurrent calls always get increasing values.
    """

    def __init__(self, start: int = 0):
        self._value = start
        self._lock = asyncio.Lock()

    async def next(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value


# ---------------------------------------------------------------------------
# ProgressEmitter Protocol and Implementations
# ---------------------------------------------------------------------------


@runtime_checkable
class ProgressEmitter(Protocol):
    """Protocol for emitting progress/status updates during agent execution.

    Implementations of this protocol handle where and how progress updates
    are delivered (Redis persistence, MCP notifications, logging, etc.).
    """

    async def emit(
        self,
        message: str,
        update_type: str = "progress",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a progress update.

        Args:
            message: Human-readable status message
            update_type: Category of update (e.g., "progress", "agent_reflection",
                        "knowledge_sources", "tool_call")
            metadata: Optional additional data (e.g., fragments, tool args)
        """
        ...


class NullEmitter:
    """No-op emitter that discards all updates. Useful for testing or batch jobs."""

    async def emit(
        self,
        message: str,
        update_type: str = "progress",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        pass


class LoggingEmitter:
    """Emitter that logs updates. Useful for debugging."""

    def __init__(self, logger_name: str = __name__, level: int = logging.INFO):
        self._logger = logging.getLogger(logger_name)
        self._level = level

    async def emit(
        self,
        message: str,
        update_type: str = "progress",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._logger.log(self._level, f"[{update_type}] {message}")


class CLIEmitter:
    """Emitter that prints notifications to the terminal for CLI usage.

    Formats output with colors/symbols based on update_type for better
    readability in terminal environments.
    """

    # ANSI color codes
    COLORS = {
        "reset": "\033[0m",
        "dim": "\033[2m",
        "bold": "\033[1m",
        "blue": "\033[34m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "cyan": "\033[36m",
        "magenta": "\033[35m",
    }

    # Symbols and colors for different update types
    TYPE_STYLES = {
        "agent_start": ("🚀", "green"),
        "agent_complete": ("✅", "green"),
        "agent_error": ("❌", "yellow"),
        "agent_reflection": ("💭", "cyan"),
        "agent_processing": ("⚙️ ", "blue"),
        "tool_call": ("🔧", "magenta"),
        "knowledge_sources": ("📚", "blue"),
        "progress": ("→", "dim"),
        "instance_context": ("🔗", "cyan"),
        "instance_created": ("➕", "green"),
        "instance_error": ("⚠️ ", "yellow"),
        "task_start": ("📋", "blue"),
        "error": ("❌", "yellow"),
    }

    def __init__(self, use_colors: bool = True, file=None):
        """Initialize CLI emitter.

        Args:
            use_colors: Whether to use ANSI colors (disable for non-TTY output)
            file: Output file (defaults to sys.stderr)
        """
        import sys

        self._use_colors = use_colors and (file or sys.stderr).isatty()
        self._file = file or sys.stderr

    def _colorize(self, text: str, color: str) -> str:
        """Apply ANSI color to text if colors are enabled."""
        if not self._use_colors or color not in self.COLORS:
            return text
        return f"{self.COLORS[color]}{text}{self.COLORS['reset']}"

    async def emit(
        self,
        message: str,
        update_type: str = "progress",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Print notification to terminal."""
        symbol, color = self.TYPE_STYLES.get(update_type, ("•", "dim"))
        formatted = f"{symbol} {self._colorize(message, color)}"
        print(formatted, file=self._file, flush=True)


class TaskEmitter:
    """Emitter that persists notifications to a Task in Redis.

    Notifications (tool reflections, progress updates) are stored on the Task,
    not the Thread. Clients (REST or MCP) can poll the Task for notifications
    and status updates.

    The Thread is only updated with the final result (as a message), which is
    handled separately by the task completion logic, not by this emitter.
    """

    def __init__(
        self,
        task_manager: "TaskManager",
        task_id: str,
    ):
        self._task_manager = task_manager
        self._task_id = task_id

    @property
    def task_id(self) -> str:
        """Return the task ID this emitter is writing to."""
        return self._task_id

    async def emit(
        self,
        message: str,
        update_type: str = "progress",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit notification to task storage."""
        try:
            await self._task_manager.add_task_update(
                self._task_id, message, update_type, metadata
            )
        except Exception as e:
            # Best-effort: don't fail the agent if notification logging fails
            logger.warning(f"Failed to emit task notification: {e}")


class MCPEmitter:
    """Emitter that sends MCP protocol progress notifications.

    This implementation is used when the agent is invoked via MCP, sending
    real-time progress updates to the MCP client (e.g., Claude Desktop).

    The MCP spec requires progress values to be monotonically increasing,
    so this emitter uses a ProgressCounter to generate sequence numbers.

    IMPORTANT: For MCP progress to work, the agent must run synchronously
    within the MCP tool call - not in a background worker like Docket.

    Example using FastMCP Context:
        from fastmcp import Context
        from redis_sre_agent.core.progress import MCPEmitter

        @mcp.tool
        async def triage_sync(query: str, ctx: Context) -> Dict[str, Any]:
            emitter = MCPEmitter.from_fastmcp_context(ctx)
            agent = SRELangGraphAgent(progress_emitter=emitter)
            response = await agent.process_query(...)
            return {"response": response}
    """

    def __init__(
        self,
        send_progress: Any,  # Callable to send MCP progress notification
        counter: Optional[ProgressCounter] = None,
    ):
        """Initialize MCP emitter.

        Args:
            send_progress: Async callable that sends MCP notifications.
                          Signature: (progress: float, total: float | None) -> None
            counter: Optional custom counter; defaults to LocalProgressCounter
        """
        self._send_progress = send_progress
        self._counter = counter or LocalProgressCounter()

    @classmethod
    def from_fastmcp_context(cls, ctx: Any) -> "MCPEmitter":
        """Create an MCPEmitter from a FastMCP Context object.

        Args:
            ctx: FastMCP Context object (from tool function parameter)

        Returns:
            MCPEmitter configured to use the context's report_progress method
        """
        return cls(send_progress=ctx.report_progress)

    async def emit(
        self,
        message: str,
        update_type: str = "progress",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit progress via MCP notification.

        Note: MCP progress notifications don't have a message field in
        report_progress, but we log the message and use the counter for
        the progress value. Clients will see increasing progress numbers.
        """
        try:
            progress = await self._counter.next()
            # FastMCP's report_progress takes (progress, total)
            # We use indeterminate progress (no total) since we don't know
            # how many updates there will be
            await self._send_progress(progress=progress, total=None)
            # Also log the message for debugging
            logger.debug(f"MCP progress {progress}: [{update_type}] {message}")
        except Exception as e:
            # Don't fail the agent if MCP notification fails
            logger.warning(f"Failed to send MCP progress notification: {e}")


class CompositeEmitter:
    """Emitter that forwards updates to multiple child emitters.

    Useful when you want updates delivered to multiple destinations,
    e.g., both MCP notifications and Redis persistence for debugging.
    """

    def __init__(self, emitters: List[ProgressEmitter]):
        self._emitters = emitters

    async def emit(
        self,
        message: str,
        update_type: str = "progress",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit to all child emitters concurrently."""
        if not self._emitters:
            return

        await asyncio.gather(
            *[e.emit(message, update_type, metadata) for e in self._emitters],
            return_exceptions=True,  # Don't fail if one emitter fails
        )


class CallbackEmitter:
    """Emitter that wraps a legacy callback function.

    Provides backward compatibility for code that still uses the old
    progress_callback signature: async def callback(message, update_type, metadata)
    """

    def __init__(self, callback):
        """Initialize with a legacy callback.

        Args:
            callback: Async callable with signature (str, str, Optional[Dict]) -> None
        """
        self._callback = callback

    async def emit(
        self,
        message: str,
        update_type: str = "progress",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Forward to the legacy callback."""
        if self._callback:
            try:
                await self._callback(message, update_type, metadata)
            except TypeError:
                # Some callbacks may not accept metadata
                await self._callback(message, update_type)


# ---------------------------------------------------------------------------
# Emitter Factory - context-aware emitter creation
# ---------------------------------------------------------------------------


def create_emitter(
    *,
    task_id: Optional[str] = None,
    task_manager: Optional["TaskManager"] = None,
    cli: bool = False,
    cli_colors: bool = True,
    additional_emitters: Optional[List[ProgressEmitter]] = None,
) -> ProgressEmitter:
    """Create the appropriate emitter based on context.

    This factory function returns the right emitter for the execution context:
    - If task_id/task_manager provided: TaskEmitter (writes to task)
    - If cli=True: CLIEmitter (prints to terminal)
    - Can combine multiple emitters via CompositeEmitter

    Args:
        task_id: Task ID to emit notifications to (requires task_manager)
        task_manager: TaskManager instance for persisting to Redis
        cli: Whether to emit to CLI (terminal output)
        cli_colors: Whether to use colors in CLI output
        additional_emitters: Extra emitters to include

    Returns:
        ProgressEmitter instance (may be composite if multiple destinations)

    Examples:
        # Task context (REST API, MCP via Docket)
        emitter = create_emitter(task_id=task_id, task_manager=task_manager)

        # CLI context
        emitter = create_emitter(cli=True)

        # Both task and CLI (debugging)
        emitter = create_emitter(task_id=task_id, task_manager=task_manager, cli=True)
    """
    emitters: List[ProgressEmitter] = []

    # Add task emitter if in task context
    if task_id and task_manager:
        emitters.append(TaskEmitter(task_manager=task_manager, task_id=task_id))

    # Add CLI emitter if requested
    if cli:
        emitters.append(CLIEmitter(use_colors=cli_colors))

    # Add any additional emitters
    if additional_emitters:
        emitters.extend(additional_emitters)

    # Return appropriate emitter
    if not emitters:
        return NullEmitter()
    elif len(emitters) == 1:
        return emitters[0]
    else:
        return CompositeEmitter(emitters)


async def create_emitter_for_task(
    task_id: str,
    redis_client=None,
) -> ProgressEmitter:
    """Convenience function to create a TaskEmitter for a given task_id.

    This is useful when you have a task_id but not a TaskManager instance.
    It creates the TaskManager internally.

    Args:
        task_id: The task ID to emit notifications to
        redis_client: Optional Redis client (uses default if not provided)

    Returns:
        TaskEmitter configured for the given task
    """
    from redis_sre_agent.core.tasks import TaskManager

    task_manager = TaskManager(redis_client=redis_client)
    return TaskEmitter(task_manager=task_manager, task_id=task_id)

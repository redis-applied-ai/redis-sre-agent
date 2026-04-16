"""Shared LangGraph checkpoint helpers."""

from __future__ import annotations

import logging
from contextlib import ExitStack, contextmanager
from typing import Any, Dict, Iterator, Optional

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.redis import RedisSaver

from redis_sre_agent import __version__
from redis_sre_agent.core.approvals import ApprovalManager, GraphResumeState, PendingApprovalSummary
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.tasks import TaskManager

logger = logging.getLogger(__name__)

GRAPH_CHECKPOINT_NAMESPACE = "agent_turn"


def resolve_graph_thread_id(
    *,
    session_id: str,
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """Prefer task-scoped checkpoint identity when available."""
    raw_task_id = str((context or {}).get("task_id") or "").strip()
    return raw_task_id or session_id


def build_graph_config(
    *,
    graph_thread_id: str,
    recursion_limit: Optional[int] = None,
    checkpoint_ns: str = GRAPH_CHECKPOINT_NAMESPACE,
) -> Dict[str, Any]:
    """Build the LangGraph runtime config for checkpointed execution."""
    config: Dict[str, Any] = {
        "configurable": {
            "thread_id": graph_thread_id,
            "checkpoint_ns": checkpoint_ns,
        }
    }
    if recursion_limit is not None:
        config["recursion_limit"] = recursion_limit
    return config


@contextmanager
def open_graph_checkpointer(*, durable: bool = True) -> Iterator[Any]:
    """Open a Redis-backed LangGraph checkpointer for the current repo config."""
    redis_url = settings.redis_url.get_secret_value()
    stack = ExitStack()
    try:
        checkpointer = stack.enter_context(RedisSaver.from_conn_string(redis_url=redis_url))
    except Exception as exc:
        stack.close()
        logger.error(
            "Redis checkpoint connection failed; durable resume is unavailable: %s",
            exc,
        )
        if durable:
            raise RuntimeError("Redis-backed graph checkpoint unavailable") from exc
        logger.warning("Falling back to in-memory graph checkpoint for non-durable session path")
        yield InMemorySaver()
        return

    try:
        try:
            checkpointer.setup()
        except Exception as exc:
            logger.warning("Redis checkpoint setup failed: %s", exc)
        yield checkpointer
    finally:
        stack.close()


async def persist_checkpoint_metadata(
    *,
    task_id: Optional[str],
    thread_id: Optional[str],
    graph_thread_id: str,
    graph_type: str,
    checkpointer: RedisSaver,
    config: Dict[str, Any],
    graph_version: str = __version__,
) -> None:
    """Persist the latest checkpoint identifiers for future resume compatibility checks."""
    if not task_id:
        return

    try:
        checkpoint_tuple = checkpointer.get_tuple(config)
        if checkpoint_tuple is None:
            return

        configurable = checkpoint_tuple.config.get("configurable", {})
        checkpoint_id = configurable.get("checkpoint_id")
        checkpoint_ns = configurable.get("checkpoint_ns", GRAPH_CHECKPOINT_NAMESPACE)
        if not checkpoint_id:
            return

        manager = ApprovalManager()
        existing = await manager.get_resume_state(task_id)
        await manager.save_resume_state(
            GraphResumeState(
                task_id=task_id,
                thread_id=(existing.thread_id if existing else None) or thread_id or "",
                graph_thread_id=graph_thread_id,
                graph_type=graph_type,
                graph_version=graph_version,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
                waiting_reason=(
                    existing.waiting_reason
                    if existing and existing.waiting_reason
                    else "checkpoint_ready"
                ),
                pending_approval_id=existing.pending_approval_id if existing else None,
                pending_interrupt_id=existing.pending_interrupt_id if existing else None,
                resume_count=existing.resume_count if existing else 0,
            )
        )
    except Exception as exc:
        logger.warning("Failed to persist checkpoint metadata for task %s: %s", task_id, exc)


async def persist_approval_wait_state(
    *,
    task_id: Optional[str],
    pending_approval: Optional[PendingApprovalSummary] = None,
) -> None:
    """Update resume metadata when a graph pauses on approval."""
    if not task_id:
        return

    try:
        resume_state = await ApprovalManager().get_resume_state(task_id)
        pending = pending_approval
        if pending is None:
            task_state = await TaskManager().get_task_state(task_id)
            pending = task_state.pending_approval if task_state else None
        if not resume_state or not pending:
            return

        await ApprovalManager().save_resume_state(
            GraphResumeState(
                task_id=resume_state.task_id,
                thread_id=resume_state.thread_id,
                graph_thread_id=resume_state.graph_thread_id,
                graph_type=resume_state.graph_type,
                graph_version=resume_state.graph_version,
                checkpoint_ns=resume_state.checkpoint_ns,
                checkpoint_id=resume_state.checkpoint_id,
                waiting_reason="approval_required",
                pending_approval_id=pending.approval_id,
                pending_interrupt_id=pending.interrupt_id,
                resume_count=resume_state.resume_count,
            )
        )
    except Exception as exc:
        logger.warning("Failed to persist approval wait state for task %s: %s", task_id, exc)

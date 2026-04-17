"""Tests for shared graph checkpoint helpers."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.agent.checkpointing import (
    GRAPH_CHECKPOINT_NAMESPACE,
    build_graph_config,
    open_graph_checkpointer,
    persist_checkpoint_metadata,
    persist_approval_wait_state,
    resolve_graph_thread_id,
)


def test_resolve_graph_thread_id_prefers_task_id():
    assert (
        resolve_graph_thread_id(
            session_id="session-1",
            context={"task_id": "task-1"},
        )
        == "task-1"
    )


def test_resolve_graph_thread_id_falls_back_to_session_id():
    assert resolve_graph_thread_id(session_id="session-1", context={}) == "session-1"


def test_build_graph_config_sets_namespace_and_recursion_limit():
    config = build_graph_config(graph_thread_id="task-1", recursion_limit=25)

    assert config["configurable"]["thread_id"] == "task-1"
    assert config["configurable"]["checkpoint_ns"] == GRAPH_CHECKPOINT_NAMESPACE
    assert config["recursion_limit"] == 25


def test_open_graph_checkpointer_uses_redis_saver_setup():
    fake_checkpointer = MagicMock()

    @contextmanager
    def fake_from_conn_string(**_kwargs):
        yield fake_checkpointer

    with patch(
        "redis_sre_agent.agent.checkpointing.RedisSaver.from_conn_string",
        side_effect=fake_from_conn_string,
    ):
        with open_graph_checkpointer() as checkpointer:
            assert checkpointer is fake_checkpointer

    fake_checkpointer.setup.assert_called_once_with()


def test_open_graph_checkpointer_raises_on_connection_error():
    with patch(
        "redis_sre_agent.agent.checkpointing.RedisSaver.from_conn_string",
        side_effect=RuntimeError("connection refused"),
    ):
        with pytest.raises(RuntimeError, match="Redis-backed graph checkpoint unavailable"):
            with open_graph_checkpointer():
                pass


def test_open_graph_checkpointer_uses_memory_saver_for_non_durable_paths():
    fake_memory_saver = MagicMock()

    with (
        patch(
            "redis_sre_agent.agent.checkpointing.RedisSaver.from_conn_string",
            side_effect=RuntimeError("connection refused"),
        ),
        patch("redis_sre_agent.agent.checkpointing.InMemorySaver", return_value=fake_memory_saver),
    ):
        with open_graph_checkpointer(durable=False) as checkpointer:
            assert checkpointer is fake_memory_saver


def test_open_graph_checkpointer_does_not_swallow_body_exceptions():
    fake_checkpointer = MagicMock()

    @contextmanager
    def fake_from_conn_string(**_kwargs):
        yield fake_checkpointer

    with patch(
        "redis_sre_agent.agent.checkpointing.RedisSaver.from_conn_string",
        side_effect=fake_from_conn_string,
    ):
        with pytest.raises(RuntimeError, match="resume failed"):
            with open_graph_checkpointer():
                raise RuntimeError("resume failed")


@pytest.mark.asyncio
async def test_persist_checkpoint_metadata_saves_resume_state():
    fake_checkpointer = MagicMock()
    fake_checkpointer.aget_tuple = AsyncMock(
        return_value=SimpleNamespace(
            config={
                "configurable": {
                    "thread_id": "task-1",
                    "checkpoint_ns": GRAPH_CHECKPOINT_NAMESPACE,
                    "checkpoint_id": "checkpoint-1",
                }
            }
        )
    )
    fake_checkpointer.get_tuple = MagicMock()
    fake_manager = SimpleNamespace(
        get_resume_state=AsyncMock(return_value=None),
        save_resume_state=AsyncMock(),
    )

    with patch("redis_sre_agent.agent.checkpointing.ApprovalManager", return_value=fake_manager):
        await persist_checkpoint_metadata(
            task_id="task-1",
            thread_id="thread-1",
            graph_thread_id="task-1",
            graph_type="chat",
            checkpointer=fake_checkpointer,
            config=build_graph_config(graph_thread_id="task-1"),
        )

    fake_checkpointer.aget_tuple.assert_awaited_once()
    fake_checkpointer.get_tuple.assert_not_called()
    fake_manager.get_resume_state.assert_awaited_once_with("task-1")
    saved_state = fake_manager.save_resume_state.await_args.args[0]
    assert saved_state.task_id == "task-1"
    assert saved_state.thread_id == "thread-1"
    assert saved_state.graph_thread_id == "task-1"
    assert saved_state.checkpoint_id == "checkpoint-1"


@pytest.mark.asyncio
async def test_persist_checkpoint_metadata_falls_back_to_sync_get_tuple():
    fake_checkpointer = MagicMock()
    del fake_checkpointer.aget_tuple
    fake_checkpointer.get_tuple.return_value = SimpleNamespace(
        config={
            "configurable": {
                "thread_id": "task-1",
                "checkpoint_ns": GRAPH_CHECKPOINT_NAMESPACE,
                "checkpoint_id": "checkpoint-1",
            }
        }
    )
    fake_manager = SimpleNamespace(
        get_resume_state=AsyncMock(return_value=None),
        save_resume_state=AsyncMock(),
    )

    with patch("redis_sre_agent.agent.checkpointing.ApprovalManager", return_value=fake_manager):
        await persist_checkpoint_metadata(
            task_id="task-1",
            thread_id="thread-1",
            graph_thread_id="task-1",
            graph_type="chat",
            checkpointer=fake_checkpointer,
            config=build_graph_config(graph_thread_id="task-1"),
        )

    saved_state = fake_manager.save_resume_state.await_args.args[0]
    assert saved_state.task_id == "task-1"
    assert saved_state.thread_id == "thread-1"
    assert saved_state.graph_thread_id == "task-1"
    assert saved_state.checkpoint_id == "checkpoint-1"


@pytest.mark.asyncio
async def test_persist_approval_wait_state_reuses_shared_redis_client():
    fake_redis_client = object()
    fake_resume_state = SimpleNamespace(
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        graph_type="chat",
        graph_version="v1",
        checkpoint_ns=GRAPH_CHECKPOINT_NAMESPACE,
        checkpoint_id="checkpoint-1",
        resume_count=0,
    )
    fake_pending_approval = SimpleNamespace(approval_id="approval-1", interrupt_id="interrupt-1")
    fake_manager = SimpleNamespace(
        get_resume_state=AsyncMock(return_value=fake_resume_state),
        save_resume_state=AsyncMock(),
    )
    fake_task_manager = SimpleNamespace(
        get_task_state=AsyncMock(
            return_value=SimpleNamespace(pending_approval=fake_pending_approval)
        )
    )

    with (
        patch(
            "redis_sre_agent.agent.checkpointing.get_redis_client", return_value=fake_redis_client
        ),
        patch(
            "redis_sre_agent.agent.checkpointing.ApprovalManager",
            return_value=fake_manager,
        ) as mock_approval_manager,
        patch(
            "redis_sre_agent.agent.checkpointing.TaskManager",
            return_value=fake_task_manager,
        ) as mock_task_manager,
    ):
        await persist_approval_wait_state(task_id="task-1")

    mock_approval_manager.assert_called_once_with(redis_client=fake_redis_client)
    mock_task_manager.assert_called_once_with(redis_client=fake_redis_client)
    fake_manager.get_resume_state.assert_awaited_once_with("task-1")
    fake_task_manager.get_task_state.assert_awaited_once_with("task-1")
    fake_manager.save_resume_state.assert_awaited_once()

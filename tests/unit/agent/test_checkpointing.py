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


def test_open_graph_checkpointer_falls_back_to_memory_saver_on_connection_error():
    fake_memory_saver = MagicMock()

    with (
        patch(
            "redis_sre_agent.agent.checkpointing.RedisSaver.from_conn_string",
            side_effect=RuntimeError("connection refused"),
        ),
        patch("redis_sre_agent.agent.checkpointing.InMemorySaver", return_value=fake_memory_saver),
    ):
        with open_graph_checkpointer() as checkpointer:
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

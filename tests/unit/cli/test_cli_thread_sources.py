import json
from unittest.mock import patch

from click.testing import CliRunner

from redis_sre_agent.cli.main import main as cli_main
from redis_sre_agent.core.tasks import TaskState, TaskStatus, TaskUpdate
from redis_sre_agent.core.threads import (
    Thread,
    ThreadMetadata,
)


def _make_thread(thread_id: str = "thread-1") -> Thread:
    """Create a minimal thread (updates are now on TaskState, not Thread)."""
    return Thread(
        thread_id=thread_id,
        messages=[],
        context={},
        metadata=ThreadMetadata(),
    )


def _make_task_with_sources(task_id: str = "task-abc", thread_id: str = "thread-1") -> TaskState:
    """Create a task with knowledge_sources updates."""
    update = TaskUpdate(
        message="Found 1 knowledge fragments",
        update_type="knowledge_sources",
        metadata={
            "task_id": task_id,
            "fragments": [
                {
                    "id": "frag-1",
                    "document_hash": "doc-xyz",
                    "chunk_index": 0,
                    "title": "Example title",
                    "source": "https://example.com/runbook",
                }
            ],
        },
    )
    return TaskState(
        task_id=task_id,
        thread_id=thread_id,
        status=TaskStatus.DONE,
        updates=[update],
    )


def test_thread_sources_cli_json_output(monkeypatch):
    runner = CliRunner()

    async def fake_get_thread(_self, thread_id: str):  # noqa: ARG001
        return _make_thread(thread_id)

    async def fake_get_task_state(_self, task_id: str):  # noqa: ARG001
        return _make_task_with_sources(task_id)

    async def fake_zrange(_self, _key, _start, _end):
        return [b"task-abc"]

    with (
        patch(
            "redis_sre_agent.core.threads.ThreadManager.get_thread",
            new=fake_get_thread,
        ),
        patch(
            "redis_sre_agent.core.tasks.TaskManager.get_task_state",
            new=fake_get_task_state,
        ),
        patch(
            "redis.asyncio.Redis.zrange",
            new=fake_zrange,
        ),
    ):
        result = runner.invoke(cli_main, ["thread", "sources", "thread-1", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["thread_id"] == "thread-1"
    frags = payload.get("fragments") or []
    assert len(frags) == 1
    f = frags[0]
    assert f["id"] == "frag-1"
    assert f["document_hash"] == "doc-xyz"
    assert f["chunk_index"] == 0
    assert f["title"] == "Example title"
    assert "source" in f and f["source"].startswith("http")


def test_thread_sources_cli_human_output(monkeypatch):
    runner = CliRunner()

    async def fake_get_thread(_self, thread_id: str):  # noqa: ARG001
        return _make_thread(thread_id)

    async def fake_get_task_state(_self, task_id: str):  # noqa: ARG001
        return _make_task_with_sources(task_id)

    async def fake_zrange(_self, _key, _start, _end):
        return [b"task-abc"]

    with (
        patch(
            "redis_sre_agent.core.threads.ThreadManager.get_thread",
            new=fake_get_thread,
        ),
        patch(
            "redis_sre_agent.core.tasks.TaskManager.get_task_state",
            new=fake_get_task_state,
        ),
        patch(
            "redis.asyncio.Redis.zrange",
            new=fake_zrange,
        ),
    ):
        result = runner.invoke(cli_main, ["thread", "sources", "thread-1"])  # table output

    assert result.exit_code == 0, result.output
    # Should include table header and key fields
    assert "Knowledge fragments for thread thread-1" in result.output
    assert "Frag ID" in result.output
    assert "Doc Hash" in result.output
    assert "doc-xyz" in result.output

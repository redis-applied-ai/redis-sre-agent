import json
from unittest.mock import patch

from click.testing import CliRunner

from redis_sre_agent.cli.main import main as cli_main
from redis_sre_agent.core.thread_state import (
    ThreadMetadata,
    ThreadState,
    ThreadStatus,
    ThreadUpdate,
)


def _make_state_with_sources(thread_id: str = "thread-1") -> ThreadState:
    update = ThreadUpdate(
        message="Found 1 knowledge fragments",
        update_type="knowledge_sources",
        metadata={
            "task_id": "task-abc",
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
    return ThreadState(
        thread_id=thread_id,
        status=ThreadStatus.DONE,
        updates=[update],
        context={},
        action_items=[],
        metadata=ThreadMetadata(),
        result=None,
        error_message=None,
    )


def test_thread_sources_cli_json_output(monkeypatch):
    runner = CliRunner()

    async def fake_get_thread_state(_self, thread_id: str):  # noqa: ARG001
        return _make_state_with_sources(thread_id)

    with patch(
        "redis_sre_agent.core.thread_state.ThreadManager.get_thread_state",
        new=fake_get_thread_state,
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

    async def fake_get_thread_state(_self, thread_id: str):  # noqa: ARG001
        return _make_state_with_sources(thread_id)

    with patch(
        "redis_sre_agent.core.thread_state.ThreadManager.get_thread_state",
        new=fake_get_thread_state,
    ):
        result = runner.invoke(cli_main, ["thread", "sources", "thread-1"])  # table output

    assert result.exit_code == 0, result.output
    # Should include table header and key fields
    assert "Knowledge fragments for thread thread-1" in result.output
    assert "Frag ID" in result.output
    assert "Doc Hash" in result.output
    assert "doc-xyz" in result.output

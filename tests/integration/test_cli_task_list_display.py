import asyncio
import json

import pytest
from click.testing import CliRunner
from pydantic import SecretStr

from redis_sre_agent.cli.main import main as cli_main

# Mark entire module as integration to support -m integration selection
pytestmark = pytest.mark.integration


def test_task_list_shows_task_id_and_local_time_and_done_status(redis_url):
    """End-to-end: create a task, mark it done, and verify CLI list shows Task ID, local/UTC time, and status done.

    Uses a real Redis (docker-compose integration fixture) and no mocks.
    """
    # Patch settings so CLI uses the integration Redis
    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    try:
        # Clone settings with updated redis_url (minimally mutate the existing instance)
        config_module.settings.redis_url = SecretStr(redis_url)

        runner = CliRunner()

        async def _setup():
            from redis.asyncio import Redis as AsyncRedis

            from redis_sre_agent.core.tasks import TaskManager
            from redis_sre_agent.core.threads import TaskStatus, ThreadManager

            # Create a clean client to the same Redis the CLI will hit
            client = AsyncRedis.from_url(redis_url, decode_responses=False)
            try:
                await client.flushdb()

                tm = ThreadManager(redis_client=client)
                thread_id = await tm.create_thread(user_id="test-user", session_id="s")

                task_mgr = TaskManager(redis_client=client)
                task_id = await task_mgr.create_task(
                    thread_id=thread_id, user_id="test-user", subject="Test task"
                )

                # Mark task done and set a simple result
                await task_mgr.set_task_result(task_id, {"ok": True})
                await task_mgr.update_task_status(task_id, TaskStatus.DONE)

                # Small wait to allow RediSearch to index initial doc (queued). The CLI refreshes status from KV.
                await asyncio.sleep(0.05)

                return thread_id, task_id
            finally:
                await client.aclose()

        thread_id, task_id = asyncio.run(_setup())

        # Invoke CLI and include DONE tasks. Set a wide terminal to avoid Rich truncation.
        env = {"COLUMNS": "220"}
        result = runner.invoke(
            cli_main,
            ["task", "list", "--all", "--limit", "10", "--tz", "UTC"],
            env=env,
        )
        assert result.exit_code == 0, result.output
        out = result.output

        # Headers
        assert "Tasks" in out
        assert "Task ID" in out

        # Should show our task id (or at least its prefix) and status done
        assert (task_id in out) or (task_id[:12] in out)
        assert "done" in out
        # Should show a timezone label (UTC was requested)
        assert "UTC" in out

        # Sanity: thread id also present (may be truncated; check prefix)
        assert (thread_id in out) or (thread_id[:12] in out)
    finally:
        config_module.settings = original_settings


def test_thread_sources_lists_recorded_fragments(redis_url):
    """Record a knowledge_sources update and verify CLI returns it (JSON mode)."""
    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    try:
        config_module.settings.redis_url = SecretStr(redis_url)

        runner = CliRunner()

        async def _setup_and_emit():
            from redis.asyncio import Redis as AsyncRedis

            from redis_sre_agent.core.threads import ThreadManager

            client = AsyncRedis.from_url(redis_url, decode_responses=False)
            try:
                await client.flushdb()

                tm = ThreadManager(redis_client=client)
                thread_id = await tm.create_thread(user_id="u", session_id="s")
                # Emit a knowledge_sources update
                await tm.add_thread_update(
                    thread_id,
                    "Found fragments",
                    "knowledge_sources",
                    {
                        "task_id": "task-xyz",
                        "fragments": [
                            {
                                "id": "frag-1",
                                "document_hash": "doc-abc",
                                "chunk_index": 0,
                                "title": "Example title",
                                "source": "https://example.com/doc",
                            }
                        ],
                    },
                )
                return thread_id
            finally:
                await client.aclose()

        thread_id = asyncio.run(_setup_and_emit())

        # Invoke CLI in JSON mode for stable assertions
        result = runner.invoke(cli_main, ["thread", "sources", thread_id, "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["thread_id"] == thread_id
        frags = payload.get("fragments") or []
        assert len(frags) == 1
        frag = frags[0]
        assert frag["id"] == "frag-1"
        assert frag["document_hash"] == "doc-abc"
        assert frag["chunk_index"] == 0
        assert frag["title"] == "Example title"
        assert frag["source"].startswith("http")
        assert payload.get("task_id") is None  # Filter is optional, not set
    finally:
        config_module.settings = original_settings

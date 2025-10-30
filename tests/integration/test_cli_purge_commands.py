import asyncio

# Force-import purge modules so coverage includes them.
# This does not change behavior; commands are still invoked via Click runner.
import importlib  # noqa: E402
from datetime import datetime, timedelta, timezone

import pytest
from click.testing import CliRunner
from pydantic import SecretStr

from redis_sre_agent.cli.main import main as cli_main

importlib.import_module("redis_sre_agent.cli.threads")
importlib.import_module("redis_sre_agent.cli.tasks")
importlib.import_module("redis_sre_agent.core.tasks")


# Mark entire module as integration to support -m integration selection
pytestmark = pytest.mark.integration


async def _set_thread_created_at(tm, client, thread_id: str, dt: datetime):
    """Set thread created_at to dt in both metadata and FT hash (via upsert)."""
    from redis_sre_agent.core.keys import RedisKeys

    iso = dt.isoformat()
    await client.hset(
        RedisKeys.thread_metadata(thread_id), mapping={"created_at": iso, "updated_at": iso}
    )
    # Upsert search doc to reflect new timestamps numerically
    await tm._upsert_thread_search_doc(thread_id)


async def _set_task_status_and_time(
    task_mgr, client, task_id: str, status: str, updated_dt: datetime
):
    from redis_sre_agent.core.keys import RedisKeys
    from redis_sre_agent.core.tasks import TaskStatus

    # KV status + updated_at in metadata
    await client.set(RedisKeys.task_status(task_id), TaskStatus(status).value)
    await client.hset(RedisKeys.task_metadata(task_id), "updated_at", updated_dt.isoformat())
    # Upsert index to reflect updated_at numerically and status
    await task_mgr._upsert_task_search_doc(task_id)


def test_thread_purge_deletes_old_threads_and_tasks(redis_url):
    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    try:
        config_module.settings.redis_url = SecretStr(redis_url)

        runner = CliRunner()

        async def _setup():
            from redis.asyncio import Redis as AsyncRedis

            from redis_sre_agent.core.tasks import TaskManager, TaskStatus
            from redis_sre_agent.core.threads import ThreadManager

            client = AsyncRedis.from_url(redis_url, decode_responses=False)
            try:
                await client.flushdb()

                tm = ThreadManager(redis_client=client)
                task_mgr = TaskManager(redis_client=client)

                # Create two threads
                t_old = await tm.create_thread(user_id="u1", session_id="s1")
                t_new = await tm.create_thread(user_id="u1", session_id="s1")

                # Create tasks under the old thread
                task_old_1 = await task_mgr.create_task(
                    thread_id=t_old, user_id="u1", subject="old1"
                )
                task_old_2 = await task_mgr.create_task(
                    thread_id=t_old, user_id="u1", subject="old2"
                )
                await task_mgr.update_task_status(task_old_1, TaskStatus.DONE)
                await task_mgr.update_task_status(task_old_2, TaskStatus.DONE)

                now = datetime.now(timezone.utc)
                # Make t_old very old, t_new recent
                await _set_thread_created_at(tm, client, t_old, now - timedelta(days=30))
                await _set_thread_created_at(tm, client, t_new, now - timedelta(hours=1))

                # Also make tasks for t_old appear old in the index
                await _set_task_status_and_time(
                    task_mgr, client, task_old_1, "done", now - timedelta(days=30)
                )
                await _set_task_status_and_time(
                    task_mgr, client, task_old_2, "done", now - timedelta(days=29)
                )

                return t_old, t_new, task_old_1, task_old_2
            finally:
                await client.aclose()

        t_old, t_new, task_old_1, task_old_2 = asyncio.run(_setup())

        # Dry-run first
        res_preview = runner.invoke(
            cli_main, ["thread", "purge", "--older-than", "7d", "--dry-run"]
        )
        assert res_preview.exit_code == 0, res_preview.output
        assert t_old in res_preview.output
        assert t_new not in res_preview.output

        # Purge for real (includes tasks by default)
        res = runner.invoke(cli_main, ["thread", "purge", "--older-than", "7d", "-y"])
        assert res.exit_code == 0, res.output
        assert "Threads deleted:" in res.output

        # Validate: old thread and its tasks removed; new thread remains
        async def _validate():
            from redis.asyncio import Redis as AsyncRedis

            from redis_sre_agent.core.keys import RedisKeys
            from redis_sre_agent.core.redis import SRE_TASKS_INDEX, SRE_THREADS_INDEX

            client = AsyncRedis.from_url(redis_url, decode_responses=False)
            try:
                # Old thread keys gone
                assert not (await client.exists(RedisKeys.thread_metadata(t_old)))
                assert not (await client.exists(RedisKeys.thread_context(t_old)))
                assert not (await client.exists(f"{SRE_THREADS_INDEX}:{t_old}"))
                # Old tasks gone (KV + FT)
                for tid in (task_old_1, task_old_2):
                    assert not (await client.exists(RedisKeys.task_status(tid)))
                    assert not (await client.exists(RedisKeys.task_metadata(tid)))
                    assert not (await client.exists(f"{SRE_TASKS_INDEX}:{tid}"))
                # New thread still present
                assert await client.exists(RedisKeys.thread_metadata(t_new))
                assert await client.exists(f"{SRE_THREADS_INDEX}:{t_new}")
            finally:
                await client.aclose()

        asyncio.run(_validate())
    finally:
        config_module.settings = original_settings


def test_task_purge_by_status_and_age(redis_url):
    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    try:
        config_module.settings.redis_url = SecretStr(redis_url)

        runner = CliRunner()

        async def _setup():
            from redis.asyncio import Redis as AsyncRedis

            from redis_sre_agent.core.tasks import TaskManager, TaskStatus
            from redis_sre_agent.core.threads import ThreadManager

            client = AsyncRedis.from_url(redis_url, decode_responses=False)
            try:
                await client.flushdb()

                tm = ThreadManager(redis_client=client)
                task_mgr = TaskManager(redis_client=client)

                thread_id = await tm.create_thread(user_id="u1", session_id="s1")
                t_done_old = await task_mgr.create_task(
                    thread_id=thread_id, user_id="u1", subject="done-old"
                )
                t_done_new = await task_mgr.create_task(
                    thread_id=thread_id, user_id="u1", subject="done-new"
                )
                t_queued_old = await task_mgr.create_task(
                    thread_id=thread_id, user_id="u1", subject="queued-old"
                )

                await task_mgr.update_task_status(t_done_old, TaskStatus.DONE)
                await task_mgr.update_task_status(t_done_new, TaskStatus.DONE)
                # Leave t_queued_old in queued

                now = datetime.now(timezone.utc)
                await _set_task_status_and_time(
                    task_mgr, client, t_done_old, "done", now - timedelta(days=10)
                )
                await _set_task_status_and_time(
                    task_mgr, client, t_done_new, "done", now - timedelta(hours=1)
                )
                await _set_task_status_and_time(
                    task_mgr, client, t_queued_old, "queued", now - timedelta(days=10)
                )

                return thread_id, t_done_old, t_done_new, t_queued_old
            finally:
                await client.aclose()

        thread_id, t_done_old, t_done_new, t_queued_old = asyncio.run(_setup())

        # Dry-run first: expect to see only the old done task
        res_preview = runner.invoke(
            cli_main,
            ["task", "purge", "--status", "done", "--older-than", "7d", "--dry-run"],
        )
        assert res_preview.exit_code == 0, res_preview.output
        assert t_done_old in res_preview.output
        assert t_done_new not in res_preview.output
        assert t_queued_old not in res_preview.output

        # Purge for real
        res = runner.invoke(
            cli_main,
            ["task", "purge", "--status", "done", "--older-than", "7d", "-y"],
        )
        assert res.exit_code == 0, res.output

        # Validate: old done task removed; others remain
        async def _validate():
            from redis.asyncio import Redis as AsyncRedis

            from redis_sre_agent.core.keys import RedisKeys
            from redis_sre_agent.core.redis import SRE_TASKS_INDEX

            client = AsyncRedis.from_url(redis_url, decode_responses=False)
            try:
                # Old done task gone
                assert not (await client.exists(RedisKeys.task_status(t_done_old)))
                assert not (await client.exists(f"{SRE_TASKS_INDEX}:{t_done_old}"))
                # New done task remains
                assert await client.exists(RedisKeys.task_status(t_done_new))
                # Queued old task remains (we filtered by status=done)
                assert await client.exists(RedisKeys.task_status(t_queued_old))
            finally:
                await client.aclose()

        asyncio.run(_validate())
    finally:
        config_module.settings = original_settings

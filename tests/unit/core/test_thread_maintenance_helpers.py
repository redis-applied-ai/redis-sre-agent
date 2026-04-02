"""Tests for thread maintenance MCP helpers."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _thread_state(
    *,
    subject: str = "",
    user_id: str | None = None,
    tags: list[str] | None = None,
    context: dict | None = None,
    messages: list | None = None,
):
    return SimpleNamespace(
        metadata=SimpleNamespace(subject=subject, user_id=user_id, tags=tags or []),
        context=context or {},
        messages=messages or [],
    )


class TestThreadMaintenanceUtilities:
    def test_parse_duration_and_decode_helpers(self):
        from redis_sre_agent.core.thread_maintenance_helpers import _decode, _parse_duration

        assert _decode(b"abc") == "abc"
        assert _decode("abc") == "abc"
        assert _parse_duration("2h").total_seconds() == 7200
        assert _parse_duration("15m").total_seconds() == 900
        assert _parse_duration("30").total_seconds() == 30

    def test_parse_duration_rejects_invalid_values(self):
        from redis_sre_agent.core.thread_maintenance_helpers import _parse_duration

        with pytest.raises(ValueError, match="Invalid duration"):
            _parse_duration("oops")

    def test_derive_subject_prefers_original_query_then_messages(self):
        from redis_sre_agent.core.thread_maintenance_helpers import _derive_subject

        assert (
            _derive_subject(
                _thread_state(context={"original_query": "Check memory usage\nASAP"}),
            )
            == "Check memory usage\nASAP"
        )
        assert (
            _derive_subject(
                _thread_state(
                    context={},
                    messages=[SimpleNamespace(role="user", content="Investigate slow queries")],
                )
            )
            == "Investigate slow queries"
        )
        assert (
            _derive_subject(
                _thread_state(
                    context={"messages": [{"role": "user", "content": "Legacy message"}]},
                )
            )
            == "Legacy message"
        )
        assert _derive_subject(_thread_state()) is None


class TestThreadReindexHelpers:
    @pytest.mark.asyncio
    async def test_reindex_threads_helper_drops_recreates_and_backfills(self):
        from redis_sre_agent.core.thread_maintenance_helpers import reindex_threads_helper

        client = AsyncMock()
        client.zrevrange.side_effect = [[b"thread-1"], []]

        thread_manager = AsyncMock()

        index = AsyncMock()
        index.exists.side_effect = [True, False]

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_threads_index",
                new_callable=AsyncMock,
                return_value=index,
            ),
        ):
            result = await reindex_threads_helper(drop=True, limit=0, start=0)

        assert result == {
            "status": "completed",
            "processed": 1,
            "dropped": True,
            "index": "sre_threads",
        }
        index.drop.assert_awaited_once()
        index.create.assert_awaited_once()
        thread_manager._upsert_thread_search_doc.assert_awaited_once_with("thread-1")

    @pytest.mark.asyncio
    async def test_reindex_threads_helper_falls_back_to_ft_dropindex(self):
        from redis_sre_agent.core.thread_maintenance_helpers import reindex_threads_helper

        client = AsyncMock()
        client.zrevrange.side_effect = [[]]

        thread_manager = AsyncMock()

        index = AsyncMock()
        index.exists.side_effect = [True, True]
        index.drop.side_effect = RuntimeError("no drop")

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_threads_index",
                new_callable=AsyncMock,
                return_value=index,
            ),
        ):
            result = await reindex_threads_helper(drop=True, limit=0, start=0)

        assert result["processed"] == 0
        client.execute_command.assert_awaited_once_with("FT.DROPINDEX", "sre_threads")

    @pytest.mark.asyncio
    async def test_reindex_threads_helper_tolerates_exists_and_drop_failures(self):
        from redis_sre_agent.core.thread_maintenance_helpers import reindex_threads_helper

        client = AsyncMock()
        client.zrevrange.side_effect = [[]]

        thread_manager = AsyncMock()

        index = AsyncMock()
        index.exists.side_effect = [RuntimeError("missing"), True]
        index.drop.side_effect = RuntimeError("no drop")
        client.execute_command.side_effect = RuntimeError("still no drop")

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_threads_index",
                new_callable=AsyncMock,
                return_value=index,
            ),
        ):
            result = await reindex_threads_helper(drop=True, limit=0, start=0)

        assert result == {
            "status": "completed",
            "processed": 0,
            "dropped": False,
            "index": "sre_threads",
        }
        index.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reindex_threads_helper_ignores_ft_dropindex_failures(self):
        from redis_sre_agent.core.thread_maintenance_helpers import reindex_threads_helper

        client = AsyncMock()
        client.zrevrange.side_effect = [[]]
        client.execute_command.side_effect = RuntimeError("still no drop")

        thread_manager = AsyncMock()

        index = AsyncMock()
        index.exists.side_effect = [True, True]
        index.drop.side_effect = RuntimeError("no drop")

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_threads_index",
                new_callable=AsyncMock,
                return_value=index,
            ),
        ):
            result = await reindex_threads_helper(drop=True, limit=0, start=0)

        assert result == {
            "status": "completed",
            "processed": 0,
            "dropped": False,
            "index": "sre_threads",
        }
        index.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_backfill_threads_helper_applies_limit(self):
        from redis_sre_agent.core.thread_maintenance_helpers import backfill_threads_helper

        client = AsyncMock()
        client.zrevrange.side_effect = [[b"thread-1", b"thread-2"], []]
        thread_manager = AsyncMock()

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            result = await backfill_threads_helper(limit=1, start=0)

        assert result == {"status": "completed", "processed": 1, "index": "sre_threads"}
        thread_manager._upsert_thread_search_doc.assert_awaited_once_with("thread-1")


class TestThreadSubjectBackfills:
    @pytest.mark.asyncio
    async def test_backfill_scheduled_subjects_updates_subjects_and_tags(self):
        from redis_sre_agent.core.thread_maintenance_helpers import (
            backfill_scheduled_thread_subjects_helper,
        )

        client = AsyncMock()
        client.zrevrange.side_effect = [[b"thread-1"], []]
        thread_manager = AsyncMock()
        state = _thread_state(
            subject="",
            user_id="scheduler",
            tags=[],
            context={"schedule_name": "Nightly Check", "automated": True},
        )
        thread_manager.get_thread.return_value = state

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            result = await backfill_scheduled_thread_subjects_helper(
                limit=0, start=0, dry_run=False
            )

        assert result == {
            "status": "completed",
            "scanned": 1,
            "subjects_updated": 1,
            "tags_updated": 1,
            "dry_run": False,
        }
        thread_manager.set_thread_subject.assert_awaited_once_with("thread-1", "Nightly Check")
        assert state.metadata.tags == ["scheduled"]
        thread_manager._save_thread_state.assert_awaited_once_with(state)

    @pytest.mark.asyncio
    async def test_backfill_scheduled_subjects_supports_dry_run(self):
        from redis_sre_agent.core.thread_maintenance_helpers import (
            backfill_scheduled_thread_subjects_helper,
        )

        client = AsyncMock()
        client.zrevrange.side_effect = [[b"thread-1"], []]
        thread_manager = AsyncMock()
        thread_manager.get_thread.return_value = _thread_state(
            subject="Unknown",
            user_id="scheduler",
            tags=["scheduled"],
            context={"schedule_name": "Nightly Check"},
        )

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            result = await backfill_scheduled_thread_subjects_helper(limit=0, start=0, dry_run=True)

        assert result["status"] == "dry_run"
        thread_manager.set_thread_subject.assert_not_called()
        thread_manager._save_thread_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_backfill_scheduled_subjects_skips_missing_state(self):
        from redis_sre_agent.core.thread_maintenance_helpers import (
            backfill_scheduled_thread_subjects_helper,
        )

        client = AsyncMock()
        client.zrevrange.side_effect = [[b"thread-1"], []]
        thread_manager = AsyncMock()
        thread_manager.get_thread.return_value = None

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            result = await backfill_scheduled_thread_subjects_helper(
                limit=0, start=0, dry_run=False
            )

        assert result == {
            "status": "completed",
            "scanned": 1,
            "subjects_updated": 0,
            "tags_updated": 0,
            "dry_run": False,
        }

    @pytest.mark.asyncio
    async def test_backfill_scheduled_subjects_honors_limit(self):
        from redis_sre_agent.core.thread_maintenance_helpers import (
            backfill_scheduled_thread_subjects_helper,
        )

        client = AsyncMock()
        client.zrevrange.side_effect = [[b"thread-1", b"thread-2"], []]
        thread_manager = AsyncMock()
        thread_manager.get_thread.side_effect = [
            _thread_state(
                subject="",
                user_id="scheduler",
                tags=[],
                context={"schedule_name": "Nightly Check"},
            ),
            _thread_state(
                subject="",
                user_id="scheduler",
                tags=[],
                context={"schedule_name": "Should Not Be Reached"},
            ),
        ]

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            result = await backfill_scheduled_thread_subjects_helper(
                limit=1, start=0, dry_run=False
            )

        assert result == {
            "status": "completed",
            "scanned": 1,
            "subjects_updated": 1,
            "tags_updated": 1,
            "dry_run": False,
        }

    @pytest.mark.asyncio
    async def test_backfill_empty_subjects_updates_subject_and_truncates(self):
        from redis_sre_agent.core.thread_maintenance_helpers import (
            backfill_empty_thread_subjects_helper,
        )

        client = AsyncMock()
        client.scan.side_effect = [(0, [b"sre_threads:thread-1"])]
        thread_manager = AsyncMock()
        thread_manager.get_thread.return_value = _thread_state(
            subject="Untitled",
            context={"original_query": "A" * 90},
        )

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            result = await backfill_empty_thread_subjects_helper(limit=0, start=0, dry_run=False)

        assert result == {
            "status": "completed",
            "scanned": 1,
            "subjects_updated": 1,
            "dry_run": False,
        }
        subject = thread_manager.set_thread_subject.await_args.args[1]
        assert subject.endswith("...")
        assert len(subject) == 80

    @pytest.mark.asyncio
    async def test_backfill_empty_subjects_supports_dry_run_and_skips_missing_state(self):
        from redis_sre_agent.core.thread_maintenance_helpers import (
            backfill_empty_thread_subjects_helper,
        )

        client = AsyncMock()
        client.scan.side_effect = [(0, [b"sre_threads:thread-1", b"sre_threads:thread-2"])]
        thread_manager = AsyncMock()
        thread_manager.get_thread.side_effect = [
            None,
            _thread_state(
                subject="", context={"messages": [{"role": "user", "content": "Legacy"}]}
            ),
        ]

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            result = await backfill_empty_thread_subjects_helper(limit=0, start=0, dry_run=True)

        assert result == {
            "status": "dry_run",
            "scanned": 2,
            "subjects_updated": 1,
            "dry_run": True,
        }
        thread_manager.set_thread_subject.assert_not_called()

    @pytest.mark.asyncio
    async def test_backfill_empty_subjects_handles_break_limit_and_skip_paths(self):
        from redis_sre_agent.core.thread_maintenance_helpers import (
            backfill_empty_thread_subjects_helper,
        )

        client = AsyncMock()
        client.scan.side_effect = [
            (0, []),
            (0, [b"sre_threads:thread-1", b"sre_threads:thread-2"]),
            (0, [b"sre_threads:thread-3", b"sre_threads:thread-4"]),
        ]
        thread_manager = AsyncMock()
        thread_manager.get_thread.side_effect = [
            _thread_state(subject="Healthy subject"),
            _thread_state(subject="", context={}),
            _thread_state(subject="", context={"original_query": "Recovered subject"}),
            _thread_state(subject="", context={"original_query": "Ignored by limit"}),
        ]

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            empty_result = await backfill_empty_thread_subjects_helper(
                limit=0, start=0, dry_run=False
            )
            skip_result = await backfill_empty_thread_subjects_helper(
                limit=0, start=0, dry_run=False
            )
            limited_result = await backfill_empty_thread_subjects_helper(
                limit=1, start=0, dry_run=False
            )

        assert empty_result == {
            "status": "completed",
            "scanned": 0,
            "subjects_updated": 0,
            "dry_run": False,
        }
        assert skip_result == {
            "status": "completed",
            "scanned": 2,
            "subjects_updated": 0,
            "dry_run": False,
        }
        assert limited_result == {
            "status": "completed",
            "scanned": 1,
            "subjects_updated": 1,
            "dry_run": False,
        }
        thread_manager.set_thread_subject.assert_awaited_once_with("thread-3", "Recovered subject")

    @pytest.mark.asyncio
    async def test_backfill_empty_subjects_treats_start_as_skip_count(self):
        from redis_sre_agent.core.thread_maintenance_helpers import (
            backfill_empty_thread_subjects_helper,
        )

        client = AsyncMock()
        client.scan.side_effect = [(0, [b"sre_threads:thread-1", b"sre_threads:thread-2"])]
        thread_manager = AsyncMock()
        thread_manager.get_thread.return_value = _thread_state(
            subject="", context={"original_query": "Recovered subject"}
        )

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            result = await backfill_empty_thread_subjects_helper(limit=0, start=1, dry_run=False)

        assert result == {
            "status": "completed",
            "scanned": 1,
            "subjects_updated": 1,
            "dry_run": False,
        }
        client.scan.assert_awaited_once_with(cursor=0, match="sre_threads:*", count=1000)
        thread_manager.get_thread.assert_awaited_once_with("thread-2")
        thread_manager.set_thread_subject.assert_awaited_once_with("thread-2", "Recovered subject")


class TestThreadPurgeHelper:
    @pytest.mark.asyncio
    async def test_purge_threads_helper_requires_scope(self):
        from redis_sre_agent.core.thread_maintenance_helpers import purge_threads_helper

        result = await purge_threads_helper(confirm=True)

        assert result == {
            "error": "Refusing to purge without a scope. Provide older_than or purge_all.",
            "status": "failed",
        }

    @pytest.mark.asyncio
    async def test_purge_threads_helper_requires_confirmation(self):
        from redis_sre_agent.core.thread_maintenance_helpers import purge_threads_helper

        result = await purge_threads_helper(older_than="7d", confirm=False)

        assert result == {
            "error": "Confirmation required",
            "status": "cancelled",
            "dry_run": False,
        }

    @pytest.mark.asyncio
    async def test_purge_threads_helper_supports_dry_run(self):
        from redis_sre_agent.core.thread_maintenance_helpers import purge_threads_helper

        client = AsyncMock()
        client.scan.side_effect = [(0, [b"sre_threads:thread-1"])]
        client.hget.return_value = b"2010-01-01T00:00:00+00:00"

        with patch(
            "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
            return_value=client,
        ):
            result = await purge_threads_helper(older_than="3650d", dry_run=True)

        assert result == {
            "status": "dry_run",
            "scanned": 1,
            "deleted": 0,
            "deleted_tasks": 0,
            "matched": ["thread-1"],
            "dry_run": True,
            "include_tasks": True,
        }

    @pytest.mark.asyncio
    async def test_purge_threads_helper_applies_older_than_even_with_purge_all(self):
        from redis_sre_agent.core.thread_maintenance_helpers import purge_threads_helper

        client = AsyncMock()
        client.scan.side_effect = [(0, [b"sre_threads:thread-1", b"sre_threads:thread-2"])]
        client.hget.side_effect = [
            b"2010-01-01T00:00:00+00:00",
            datetime.now(timezone.utc).isoformat().encode(),
        ]
        client.zrevrange.return_value = []

        thread_manager = AsyncMock()
        thread_manager.delete_thread.return_value = True

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            result = await purge_threads_helper(
                purge_all=True,
                older_than="3650d",
                confirm=True,
            )

        assert result == {
            "status": "purged",
            "scanned": 2,
            "deleted": 1,
            "deleted_tasks": 0,
            "matched": ["thread-1"],
            "dry_run": False,
            "include_tasks": True,
        }

    @pytest.mark.asyncio
    async def test_purge_threads_helper_deletes_threads_and_tasks(self):
        from redis_sre_agent.core.thread_maintenance_helpers import purge_threads_helper

        client = AsyncMock()
        client.scan.side_effect = [(0, [b"sre_threads:thread-1"])]
        client.hget.side_effect = [b"1"]
        client.zrevrange.return_value = [b"task-1"]

        thread_manager = AsyncMock()
        thread_manager.delete_thread.return_value = True

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.delete_task_core",
                new_callable=AsyncMock,
            ) as mock_delete_task,
        ):
            result = await purge_threads_helper(purge_all=True, confirm=True)

        assert result == {
            "status": "purged",
            "scanned": 1,
            "deleted": 1,
            "deleted_tasks": 1,
            "matched": ["thread-1"],
            "dry_run": False,
            "include_tasks": True,
        }
        mock_delete_task.assert_awaited_once_with(task_id="task-1", redis_client=client)
        thread_manager.delete_thread.assert_awaited_once_with("thread-1")

    @pytest.mark.asyncio
    async def test_purge_threads_helper_ignores_task_and_delete_errors(self):
        from redis_sre_agent.core.thread_maintenance_helpers import purge_threads_helper

        client = AsyncMock()
        client.scan.side_effect = [(0, [b"sre_threads:thread-1"])]
        client.hget.side_effect = [b"1"]
        client.zrevrange.return_value = [b"task-1"]

        thread_manager = AsyncMock()
        thread_manager.delete_thread.return_value = False

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.delete_task_core",
                new_callable=AsyncMock,
                side_effect=RuntimeError("ignore me"),
            ),
        ):
            result = await purge_threads_helper(purge_all=True, confirm=True)

        assert result == {
            "status": "purged",
            "scanned": 1,
            "deleted": 0,
            "deleted_tasks": 0,
            "matched": ["thread-1"],
            "dry_run": False,
            "include_tasks": True,
        }

    @pytest.mark.asyncio
    async def test_purge_threads_helper_handles_empty_and_ineligible_threads(self):
        from redis_sre_agent.core.thread_maintenance_helpers import purge_threads_helper

        client = AsyncMock()
        client.scan.side_effect = [
            (0, []),
            (0, [b"sre_threads:thread-1", b"sre_threads:thread-2"]),
            (0, [b"sre_threads:thread-3"]),
        ]
        client.hget.side_effect = [
            b"9999999999",
            RuntimeError("bad timestamp"),
            b"1",
        ]

        thread_manager = AsyncMock()
        thread_manager.delete_thread.return_value = True
        client.delete.side_effect = [RuntimeError("thread doc delete failed")]

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            empty_result = await purge_threads_helper(purge_all=True, confirm=True)
            skipped_result = await purge_threads_helper(
                older_than="3650d", include_tasks=False, confirm=True
            )
            deleted_result = await purge_threads_helper(purge_all=True, confirm=True)

        assert empty_result == {
            "status": "purged",
            "scanned": 0,
            "deleted": 0,
            "deleted_tasks": 0,
            "matched": [],
            "dry_run": False,
            "include_tasks": True,
        }
        assert skipped_result == {
            "status": "purged",
            "scanned": 2,
            "deleted": 0,
            "deleted_tasks": 0,
            "matched": [],
            "dry_run": False,
            "include_tasks": False,
        }
        assert deleted_result == {
            "status": "purged",
            "scanned": 1,
            "deleted": 1,
            "deleted_tasks": 0,
            "matched": ["thread-3"],
            "dry_run": False,
            "include_tasks": True,
        }

    @pytest.mark.asyncio
    async def test_purge_threads_helper_ignores_stray_task_doc_delete_errors(self):
        """Thread purges should not scan the full task keyspace per thread."""
        from redis_sre_agent.core.thread_maintenance_helpers import purge_threads_helper

        client = AsyncMock()
        client.scan.side_effect = [(0, [b"sre_threads:thread-1"])]
        client.hget.return_value = b"1"
        client.zrevrange.return_value = []

        thread_manager = AsyncMock()
        thread_manager.delete_thread.return_value = True

        with (
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.get_redis_client",
                return_value=client,
            ),
            patch(
                "redis_sre_agent.core.thread_maintenance_helpers.ThreadManager",
                return_value=thread_manager,
            ),
        ):
            result = await purge_threads_helper(purge_all=True, confirm=True)

        assert result == {
            "status": "purged",
            "scanned": 1,
            "deleted": 1,
            "deleted_tasks": 0,
            "matched": ["thread-1"],
            "dry_run": False,
            "include_tasks": True,
        }
        client.scan.assert_awaited_once()

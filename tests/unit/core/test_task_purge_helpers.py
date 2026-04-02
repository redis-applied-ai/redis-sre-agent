"""Tests for task purge helpers."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.task_purge_helpers import _decode, _parse_duration, purge_tasks_helper


class TestParseDuration:
    """Test duration parsing used by task purging."""

    def test_parse_duration_supports_suffixes(self):
        assert _parse_duration("7d") == timedelta(days=7)
        assert _parse_duration("24h") == timedelta(hours=24)
        assert _parse_duration("15m") == timedelta(minutes=15)
        assert _parse_duration("30s") == timedelta(seconds=30)
        assert _parse_duration("45") == timedelta(seconds=45)

    def test_parse_duration_rejects_invalid_values(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            _parse_duration("nope")

    def test_decode_handles_strings_and_none(self):
        assert _decode("task-1") == "task-1"
        assert _decode(None) == ""


class TestPurgeTasksHelper:
    """Test bulk task purge helper behavior."""

    @pytest.mark.asyncio
    async def test_purge_tasks_helper_requires_scope(self):
        result = await purge_tasks_helper(confirm=True)

        assert result == {
            "error": "Refusing to purge without a scope. Provide older_than/status or purge_all.",
            "status": "failed",
        }

    @pytest.mark.asyncio
    async def test_purge_tasks_helper_requires_confirmation_when_not_dry_run(self):
        result = await purge_tasks_helper(status="done", confirm=False)

        assert result == {
            "error": "Confirmation required",
            "status": "cancelled",
            "dry_run": False,
        }

    @pytest.mark.asyncio
    async def test_purge_tasks_helper_supports_dry_run_without_confirmation(self):
        redis_client = AsyncMock()
        redis_client.scan = AsyncMock(
            side_effect=[
                (0, [b"sre_tasks:task-1"]),
            ]
        )
        redis_client.hmget = AsyncMock(return_value=[b"done", b"1", b"1"])

        result = await purge_tasks_helper(
            status="done",
            dry_run=True,
            redis_client=redis_client,
        )

        assert result == {
            "status": "dry_run",
            "scanned": 1,
            "deleted": 0,
            "matched": ["task-1"],
            "dry_run": True,
        }

    @pytest.mark.asyncio
    async def test_purge_tasks_helper_deletes_matching_tasks(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        redis_client = AsyncMock()
        redis_client.scan = AsyncMock(
            side_effect=[
                (1, [b"sre_tasks:task-1"]),
                (0, [b"sre_tasks:task-2"]),
            ]
        )
        redis_client.hmget = AsyncMock(
            side_effect=[
                [
                    b"done",
                    str(datetime.now(timezone.utc).timestamp()).encode(),
                    str(cutoff.timestamp()).encode(),
                ],
                [
                    b"queued",
                    str(datetime.now(timezone.utc).timestamp()).encode(),
                    str(datetime.now(timezone.utc).timestamp()).encode(),
                ],
            ]
        )

        with patch(
            "redis_sre_agent.core.task_purge_helpers.delete_task_core",
            new_callable=AsyncMock,
        ) as mock_delete:
            result = await purge_tasks_helper(
                status="done",
                older_than="1d",
                confirm=True,
                redis_client=redis_client,
            )

        assert result == {
            "status": "purged",
            "scanned": 2,
            "deleted": 1,
            "matched": ["task-1"],
            "dry_run": False,
        }
        mock_delete.assert_awaited_once_with(task_id="task-1", redis_client=redis_client)

    @pytest.mark.asyncio
    async def test_purge_tasks_helper_supports_iso_timestamps_and_purge_all_filters(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        redis_client = AsyncMock()
        redis_client.scan = AsyncMock(
            side_effect=[
                (0, [b"sre_tasks:task-1", b"sre_tasks:task-2"]),
            ]
        )
        redis_client.hmget = AsyncMock(
            side_effect=[
                [
                    b"done",
                    datetime.now(timezone.utc).isoformat().encode(),
                    cutoff.isoformat().encode(),
                ],
                [
                    b"queued",
                    cutoff.isoformat().encode(),
                    datetime.now(timezone.utc).isoformat().encode(),
                ],
            ]
        )

        with patch(
            "redis_sre_agent.core.task_purge_helpers.delete_task_core",
            new_callable=AsyncMock,
        ) as mock_delete:
            result = await purge_tasks_helper(
                purge_all=True,
                status="done",
                older_than="1d",
                confirm=True,
                redis_client=redis_client,
            )

        assert result == {
            "status": "purged",
            "scanned": 2,
            "deleted": 1,
            "matched": ["task-1"],
            "dry_run": False,
        }
        mock_delete.assert_awaited_once_with(task_id="task-1", redis_client=redis_client)

    @pytest.mark.asyncio
    async def test_purge_tasks_helper_falls_back_to_updated_at_when_created_at_missing(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        redis_client = AsyncMock()
        redis_client.scan = AsyncMock(side_effect=[(0, [b"sre_tasks:task-1"])])
        redis_client.hmget = AsyncMock(
            return_value=[
                b"done",
                cutoff.isoformat().encode(),
                b"",
            ]
        )

        with patch(
            "redis_sre_agent.core.task_purge_helpers.delete_task_core",
            new_callable=AsyncMock,
        ) as mock_delete:
            result = await purge_tasks_helper(
                status="done",
                older_than="1d",
                confirm=True,
                redis_client=redis_client,
            )

        assert result == {
            "status": "purged",
            "scanned": 1,
            "deleted": 1,
            "matched": ["task-1"],
            "dry_run": False,
        }
        mock_delete.assert_awaited_once_with(task_id="task-1", redis_client=redis_client)

    @pytest.mark.asyncio
    async def test_purge_tasks_helper_ignores_hmget_and_delete_errors(self):
        redis_client = AsyncMock()
        redis_client.scan = AsyncMock(side_effect=[(0, [b"sre_tasks:task-1"])])
        redis_client.hmget = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(
            "redis_sre_agent.core.task_purge_helpers.delete_task_core",
            new_callable=AsyncMock,
            side_effect=RuntimeError("delete failed"),
        ) as mock_delete:
            result = await purge_tasks_helper(
                purge_all=True,
                confirm=True,
                redis_client=redis_client,
            )

        assert result == {
            "status": "purged",
            "scanned": 1,
            "deleted": 0,
            "matched": ["task-1"],
            "dry_run": False,
        }
        mock_delete.assert_awaited_once_with(task_id="task-1", redis_client=redis_client)

    @pytest.mark.asyncio
    async def test_purge_tasks_helper_handles_empty_scan(self):
        redis_client = AsyncMock()
        redis_client.scan = AsyncMock(return_value=(0, []))

        result = await purge_tasks_helper(
            purge_all=True,
            confirm=True,
            redis_client=redis_client,
        )

        assert result == {
            "status": "purged",
            "scanned": 0,
            "deleted": 0,
            "matched": [],
            "dry_run": False,
        }

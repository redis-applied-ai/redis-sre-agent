"""Unit tests for schedule storage functionality."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.schedule_storage import (
    delete_schedule,
    find_schedules_needing_runs,
    get_schedule,
    store_schedule,
    update_schedule_last_run,
    update_schedule_next_run,
)


@pytest.fixture
def sample_schedule():
    """Sample schedule data for testing."""
    return {
        "id": "test-schedule-123",
        "name": "Test Schedule",
        "description": "A test schedule",
        "interval_type": "hours",
        "interval_value": 2,
        "instructions": "Run test command",
        "enabled": True,
        "created_at": datetime.now(timezone.utc).timestamp(),
        "updated_at": datetime.now(timezone.utc).timestamp(),
        "next_run_at": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
        "last_run_at": None,
    }


class TestScheduleStorage:
    """Test schedule storage operations."""

    @pytest.mark.asyncio
    async def test_store_schedule_success(self, sample_schedule):
        """Test successful schedule storage."""
        with patch("redis_sre_agent.core.schedule_storage.get_redis_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.hset.return_value = 1

            result = await store_schedule(sample_schedule)

            assert result is True
            mock_client.hset.assert_called()

    @pytest.mark.asyncio
    async def test_store_schedule_failure(self, sample_schedule):
        """Test schedule storage failure."""
        with patch("redis_sre_agent.core.schedule_storage.get_redis_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.hset.side_effect = Exception("Redis error")

            result = await store_schedule(sample_schedule)

            assert result is False

    @pytest.mark.asyncio
    async def test_get_schedule_success(self, sample_schedule):
        """Test successful schedule retrieval."""
        with patch("redis_sre_agent.core.schedule_storage.get_redis_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            # Mock Redis hash data (bytes keys/values)
            redis_data = {
                b"id": b"test-schedule-123",
                b"name": b"Test Schedule",
                b"enabled": b"true",
                b"interval_type": b"hours",
                b"interval_value": b"2",
            }
            mock_client.hgetall.return_value = redis_data

            result = await get_schedule("test-schedule-123")

            assert result is not None
            assert result["id"] == "test-schedule-123"
            assert result["name"] == "Test Schedule"
            assert result["enabled"] is True
            assert result["interval_value"] == 2

    @pytest.mark.asyncio
    async def test_get_schedule_not_found(self):
        """Test schedule retrieval when not found."""
        with patch("redis_sre_agent.core.schedule_storage.get_redis_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.hgetall.return_value = {}

            result = await get_schedule("nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_delete_schedule_success(self):
        """Test successful schedule deletion."""
        with patch("redis_sre_agent.core.schedule_storage.get_redis_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.delete.return_value = 1

            result = await delete_schedule("test-schedule-123")

            assert result is True
            mock_client.delete.assert_called_with("sre_schedules:test-schedule-123")

    @pytest.mark.asyncio
    async def test_update_schedule_next_run_success(self):
        """Test successful next run time update."""
        next_run_time = datetime.now(timezone.utc) + timedelta(hours=2)

        with patch("redis_sre_agent.core.schedule_storage.get_redis_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.hset.return_value = 1
            mock_client.hget.return_value = str(next_run_time.timestamp()).encode()

            result = await update_schedule_next_run("test-schedule-123", next_run_time)

            assert result is True
            # Should call hset twice (next_run_at and updated_at)
            assert mock_client.hset.call_count == 2

    @pytest.mark.asyncio
    async def test_update_schedule_last_run_success(self):
        """Test successful last run time update."""
        last_run_time = datetime.now(timezone.utc)

        with patch("redis_sre_agent.core.schedule_storage.get_redis_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.hset.return_value = 1

            result = await update_schedule_last_run("test-schedule-123", last_run_time)

            assert result is True
            # Should call hset twice (last_run_at and updated_at)
            assert mock_client.hset.call_count == 2


class TestScheduleQueries:
    """Test schedule query operations."""

    @pytest.mark.asyncio
    async def test_find_schedules_needing_runs_with_due_schedules(self):
        """Test finding schedules that need to run."""
        current_time = datetime.now(timezone.utc)

        # Mock schedule that needs to run (next_run_at is in the past)
        due_schedule = {
            "id": "due-schedule",
            "name": "Due Schedule",
            "enabled": "true",  # RedisVL stores as string
            "next_run_at": str(
                (current_time - timedelta(minutes=30)).timestamp()
            ),  # RedisVL stores as timestamp string
        }

        # Mock the RedisVL index and query
        mock_index = AsyncMock()
        mock_query_result = [due_schedule]
        mock_index.query.return_value = mock_query_result
        mock_index.__aenter__.return_value = mock_index
        mock_index.__aexit__.return_value = None

        with patch("redis_sre_agent.core.schedule_storage.get_schedules_index") as mock_get_index:
            mock_get_index.return_value = mock_index

            result = await find_schedules_needing_runs(current_time)

            assert len(result) == 1
            assert result[0]["id"] == "due-schedule"

    @pytest.mark.asyncio
    async def test_find_schedules_needing_runs_no_due_schedules(self):
        """Test finding schedules when none are due."""
        current_time = datetime.now(timezone.utc)

        # Mock schedule that doesn't need to run (next_run_at is in the future)
        future_schedule = {
            "id": "future-schedule",
            "name": "Future Schedule",
            "enabled": True,
            "next_run_at": (current_time + timedelta(hours=1)).isoformat(),
        }

        with (
            patch("redis_sre_agent.core.schedule_storage.list_schedules") as mock_list,
            patch("redis_sre_agent.core.schedule_storage.get_schedules_index") as mock_get_index,
        ):
            mock_list.return_value = [future_schedule]
            mock_index = MagicMock()
            mock_index.__aenter__.return_value = mock_index
            mock_index.__aexit__.return_value = None

            # Ensure index path returns no results for isolation
            async def _q(_):
                return []

            mock_index.query = _q
            mock_get_index.return_value = mock_index

            result = await find_schedules_needing_runs(current_time)

            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_find_schedules_needing_runs_disabled_schedules(self):
        """Test that disabled schedules are not returned."""
        current_time = datetime.now(timezone.utc)

        # Mock disabled schedule that would otherwise be due
        disabled_schedule = {
            "id": "disabled-schedule",
            "name": "Disabled Schedule",
            "enabled": False,
            "next_run_at": (current_time - timedelta(minutes=30)).isoformat(),
        }

        with (
            patch("redis_sre_agent.core.schedule_storage.list_schedules") as mock_list,
            patch("redis_sre_agent.core.schedule_storage.get_schedules_index") as mock_get_index,
        ):
            mock_list.return_value = [disabled_schedule]
            mock_index = MagicMock()
            mock_index.__aenter__.return_value = mock_index
            mock_index.__aexit__.return_value = None

            async def _q(_):
                return []

            mock_index.query = _q
            mock_get_index.return_value = mock_index

            result = await find_schedules_needing_runs(current_time)

            assert len(result) == 0

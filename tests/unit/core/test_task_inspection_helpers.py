"""Tests for task inspection helpers."""

from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.task_inspection_helpers import get_task_helper, list_tasks_helper
from redis_sre_agent.core.tasks import TaskStatus


class TestListTasksHelper:
    """Test shared helpers for task list inspection."""

    @pytest.mark.asyncio
    async def test_list_tasks_helper_defaults(self):
        """Default listing should preserve CLI-like queued/in-progress behavior."""
        with patch(
            "redis_sre_agent.core.task_inspection_helpers.list_tasks",
            new_callable=AsyncMock,
        ) as mock_list:
            mock_list.return_value = [
                {
                    "task_id": "task-123",
                    "thread_id": "thread-456",
                    "status": TaskStatus.IN_PROGRESS,
                    "updates": [],
                    "result": None,
                    "tool_calls": None,
                    "error_message": None,
                    "metadata": {"subject": "Health check"},
                    "context": {},
                }
            ]

            result = await list_tasks_helper()

        assert result == {
            "tasks": [
                {
                    "task_id": "task-123",
                    "thread_id": "thread-456",
                    "status": "in_progress",
                    "updates": [],
                    "result": None,
                    "tool_calls": [],
                    "error_message": None,
                    "metadata": {"subject": "Health check"},
                    "context": {},
                }
            ],
            "count": 1,
            "user_id": None,
            "status": None,
            "show_all": False,
            "limit": 50,
        }
        mock_list.assert_awaited_once_with(
            user_id=None,
            status_filter=None,
            show_all=False,
            limit=50,
        )

    @pytest.mark.asyncio
    async def test_list_tasks_helper_with_status_string(self):
        """Explicit status filters should be validated and normalized."""
        with patch(
            "redis_sre_agent.core.task_inspection_helpers.list_tasks",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_list:
            result = await list_tasks_helper(status="done", limit=250, user_id="user-123")

        assert result["tasks"] == []
        assert result["status"] == "done"
        assert result["limit"] == 100
        mock_list.assert_awaited_once_with(
            user_id="user-123",
            status_filter=TaskStatus.DONE,
            show_all=False,
            limit=100,
        )

    @pytest.mark.asyncio
    async def test_list_tasks_helper_show_all_and_min_limit(self):
        """Show-all queries should clamp low limits and skip status filtering."""
        with patch(
            "redis_sre_agent.core.task_inspection_helpers.list_tasks",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_list:
            result = await list_tasks_helper(show_all=True, limit=0)

        assert result["show_all"] is True
        assert result["limit"] == 1
        mock_list.assert_awaited_once_with(
            user_id=None,
            status_filter=None,
            show_all=True,
            limit=1,
        )

    @pytest.mark.asyncio
    async def test_list_tasks_helper_invalid_status(self):
        """Invalid status filters should fail clearly."""
        with pytest.raises(ValueError, match="Invalid task status filter"):
            await list_tasks_helper(status="bogus")


class TestGetTaskHelper:
    """Test shared helpers for single-task inspection."""

    @pytest.mark.asyncio
    async def test_get_task_helper_normalizes_payload(self):
        """Single-task helper should normalize status enums and tool calls."""
        with patch(
            "redis_sre_agent.core.task_inspection_helpers.get_task_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "task_id": "task-123",
                "thread_id": "thread-456",
                "status": TaskStatus.DONE,
                "updates": [{"message": "done"}],
                "result": {"summary": "ok"},
                "tool_calls": [{"name": "redis_info"}],
                "error_message": None,
                "metadata": {"subject": "Health check"},
                "context": {"kind": "triage"},
            }

            result = await get_task_helper("task-123")

        assert result["status"] == "done"
        assert result["tool_calls"] == [{"name": "redis_info"}]
        mock_get.assert_awaited_once_with(task_id="task-123")

    @pytest.mark.asyncio
    async def test_get_task_helper_preserves_string_status(self):
        """String statuses should pass through without conversion."""
        with patch(
            "redis_sre_agent.core.task_inspection_helpers.get_task_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "task_id": "task-123",
                "thread_id": "thread-456",
                "status": "queued",
                "updates": [],
                "result": None,
                "tool_calls": None,
                "error_message": None,
                "metadata": {},
                "context": {},
            }

            result = await get_task_helper("task-123")

        assert result["status"] == "queued"
        assert result["tool_calls"] == []

    @pytest.mark.asyncio
    async def test_get_task_helper_preserves_missing_status(self):
        """Missing statuses should remain null rather than stringified."""
        with patch(
            "redis_sre_agent.core.task_inspection_helpers.get_task_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "task_id": "task-123",
                "thread_id": "thread-456",
                "status": None,
                "updates": [],
                "result": None,
                "tool_calls": None,
                "error_message": None,
                "metadata": {},
                "context": {},
            }

            result = await get_task_helper("task-123")

        assert result["status"] is None

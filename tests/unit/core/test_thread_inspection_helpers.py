"""Tests for thread inspection helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.thread_inspection_helpers import (
    get_thread_sources_helper,
    get_thread_trace_helper,
)


class TestGetThreadSourcesHelper:
    """Test shared helpers for thread source inspection."""

    @pytest.mark.asyncio
    async def test_get_thread_sources_helper_collects_fragments(self):
        """Knowledge-source updates should be flattened into fragment rows."""
        mock_client = AsyncMock()
        mock_client.zrange.return_value = [b"task-1", "task-2"]
        task_state = SimpleNamespace(
            updates=[
                SimpleNamespace(
                    update_type="knowledge_sources",
                    timestamp="2026-03-25T12:00:00Z",
                    metadata={
                        "fragments": [
                            {
                                "id": "frag-1",
                                "document_hash": "doc-1",
                                "chunk_index": 3,
                                "title": "KB Article",
                                "source": "redis.io",
                            }
                        ]
                    },
                ),
                SimpleNamespace(
                    update_type="progress",
                    timestamp="2026-03-25T12:01:00Z",
                    metadata={},
                ),
            ]
        )

        with (
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.get_redis_client",
                return_value=mock_client,
            ),
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.ThreadManager.get_thread",
                new_callable=AsyncMock,
                return_value=object(),
            ),
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.TaskManager.get_task_state",
                new_callable=AsyncMock,
                side_effect=[task_state, None],
            ) as mock_get_task,
        ):
            result = await get_thread_sources_helper("thread-123")

        assert result == {
            "thread_id": "thread-123",
            "task_id": None,
            "fragments": [
                {
                    "timestamp": "2026-03-25T12:00:00Z",
                    "task_id": "task-1",
                    "id": "frag-1",
                    "document_hash": "doc-1",
                    "chunk_index": 3,
                    "title": "KB Article",
                    "source": "redis.io",
                }
            ],
            "count": 1,
        }
        mock_client.zrange.assert_awaited_once()
        assert mock_get_task.await_count == 2

    @pytest.mark.asyncio
    async def test_get_thread_sources_helper_filters_task_and_ignores_bad_updates(self):
        """Task filters should narrow results while malformed updates are ignored."""
        mock_client = AsyncMock()
        mock_client.zrange.return_value = ["task-1", "task-2"]
        task_state = SimpleNamespace(
            updates=[
                SimpleNamespace(
                    update_type="knowledge_sources",
                    timestamp="2026-03-25T12:00:00Z",
                    metadata={"fragments": [object()]},
                ),
                SimpleNamespace(
                    update_type="knowledge_sources",
                    timestamp="2026-03-25T12:01:00Z",
                    metadata={"fragments": [{"id": "frag-2"}]},
                ),
            ]
        )

        with (
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.get_redis_client",
                return_value=mock_client,
            ),
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.ThreadManager.get_thread",
                new_callable=AsyncMock,
                return_value=object(),
            ),
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.TaskManager.get_task_state",
                new_callable=AsyncMock,
                return_value=task_state,
            ) as mock_get_task,
        ):
            result = await get_thread_sources_helper("thread-123", task_id="task-2")

        assert result["count"] == 1
        assert result["fragments"][0]["task_id"] == "task-2"
        assert result["fragments"][0]["id"] == "frag-2"
        mock_get_task.assert_awaited_once_with("task-2")

    @pytest.mark.asyncio
    async def test_get_thread_sources_helper_returns_not_found_payload(self):
        """Missing threads should return an empty error payload."""
        with (
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.get_redis_client",
                return_value=AsyncMock(),
            ),
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.ThreadManager.get_thread",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await get_thread_sources_helper("thread-missing")

        assert result == {
            "error": "Thread thread-missing not found",
            "thread_id": "thread-missing",
            "task_id": None,
            "fragments": [],
            "count": 0,
        }


class TestGetThreadTraceHelper:
    """Test shared helpers for thread trace inspection."""

    @pytest.mark.asyncio
    async def test_get_thread_trace_helper_summarizes_trace(self):
        """Trace helper should summarize tool calls and derive citations."""
        trace = {
            "message_id": "msg-123",
            "otel_trace_id": "otel-123",
            "created_at": "2026-03-25T12:00:00Z",
            "tool_envelopes": [
                {
                    "tool_key": "knowledge.search",
                    "name": "knowledge_search",
                    "args": {"query": "memory"},
                    "status": "success",
                    "summary": "Found memory docs",
                    "data": {
                        "results": [
                            {
                                "id": "doc-1",
                                "title": "Memory Tuning",
                                "source": "redis.io",
                                "score": 0.98,
                            }
                        ]
                    },
                },
                {
                    "tool_key": "redis.info",
                    "name": "redis_info",
                    "args": {},
                    "status": "success",
                    "data": {"used_memory": 123},
                },
            ],
        }

        with (
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.get_redis_client",
                return_value=AsyncMock(),
            ),
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.ThreadManager.get_message_trace",
                new_callable=AsyncMock,
                return_value=trace,
            ),
        ):
            result = await get_thread_trace_helper("msg-123")

        assert result["message_id"] == "msg-123"
        assert result["tool_call_count"] == 2
        assert result["tool_calls"][0]["name"] == "knowledge_search"
        assert result["tool_calls"][0]["result_preview"] == "Found memory docs"
        assert "data" not in result["tool_calls"][0]
        assert result["citations"] == [
            {
                "title": "Memory Tuning",
                "source": "redis.io",
                "score": 0.98,
                "document_id": "doc-1",
            }
        ]
        assert result["citation_count"] == 1

    @pytest.mark.asyncio
    async def test_get_thread_trace_helper_includes_tool_data_when_requested(self):
        """Full tool data should be included when explicitly requested."""
        trace = {
            "message_id": "msg-123",
            "tool_envelopes": [
                {
                    "tool_key": "redis.info",
                    "name": "redis_info",
                    "args": {},
                    "status": "failed",
                    "data": {"error": "boom"},
                }
            ],
        }

        with (
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.get_redis_client",
                return_value=AsyncMock(),
            ),
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.ThreadManager.get_message_trace",
                new_callable=AsyncMock,
                return_value=trace,
            ),
        ):
            result = await get_thread_trace_helper("msg-123", include_tool_data=True)

        assert result["tool_call_count"] == 1
        assert result["tool_calls"][0]["status"] == "failed"
        assert result["tool_calls"][0]["data"] == {"error": "boom"}
        assert result["citation_count"] == 0

    @pytest.mark.asyncio
    async def test_get_thread_trace_helper_returns_not_found_payload(self):
        """Missing traces should return an empty error payload."""
        with (
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.get_redis_client",
                return_value=AsyncMock(),
            ),
            patch(
                "redis_sre_agent.core.thread_inspection_helpers.ThreadManager.get_message_trace",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await get_thread_trace_helper("msg-missing")

        assert result == {
            "error": "No decision trace found for message msg-missing",
            "message_id": "msg-missing",
            "tool_calls": [],
            "tool_call_count": 0,
            "citations": [],
            "citation_count": 0,
        }

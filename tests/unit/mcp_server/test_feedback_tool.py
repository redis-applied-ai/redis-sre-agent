"""Tests for the redis_sre_submit_feedback MCP tool (US-007).

Tests use real Redis (skip when unavailable) following the pattern established
in tests/unit/core/test_feedback.py. The tool is called directly rather than
through the MCP transport layer, matching the style of TestSkillTools in
test_mcp_server.py.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio

from redis_sre_agent.core.feedback import TaskNotFoundError
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.mcp_server.server import (
    redis_sre_get_feedback,
    redis_sre_list_feedback,
    redis_sre_submit_feedback,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator:
    """Provide a real Redis client; skip the test if Redis is unreachable."""
    client = get_redis_client()
    try:
        await client.ping()
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def task_factory(redis_client):
    """Create real task-status keys so submit_feedback accepts the task_id.

    Mirrors the fixture in tests/unit/core/test_feedback.py.
    """
    created: list[str] = []

    async def _make(*, thread_id: str | None = "thr-test") -> str:
        task_id = f"tsk-{uuid.uuid4().hex[:12]}"
        await redis_client.set(RedisKeys.task_status(task_id), "done")
        mapping: dict = {"created_at": "2026-01-01T00:00:00+00:00"}
        if thread_id is not None:
            mapping["thread_id"] = thread_id
        await redis_client.hset(RedisKeys.task_metadata(task_id), mapping=mapping)
        created.append(task_id)
        return task_id

    yield _make

    for task_id in created:
        await redis_client.delete(
            RedisKeys.task_status(task_id),
            RedisKeys.task_metadata(task_id),
            RedisKeys.feedback_task(task_id),
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMCPSubmitFeedback:
    """Tests for redis_sre_submit_feedback MCP tool."""

    @pytest.mark.asyncio
    async def test_mcp_submit_feedback(self, task_factory):
        """Happy path: returns a FeedbackRecord-shaped dict with correct fields."""
        task_id = await task_factory()

        result = await redis_sre_submit_feedback(
            task_id=task_id,
            verdict="up",
            comment="Excellent diagnosis",
        )

        assert isinstance(result, dict)
        assert result["task_id"] == task_id
        assert result["verdict"] == "up"
        assert result["comment"] == "Excellent diagnosis"
        assert "created_at" in result
        assert "updated_at" in result
        # Must not be an error-shaped dict.
        assert "error" not in result
        assert "status" not in result

    @pytest.mark.asyncio
    async def test_mcp_withdrawn_and_repeated_write(self, task_factory):
        """Withdrawn verdicts and identical resubmits preserve the existing row."""
        task_id = await task_factory()

        first = await redis_sre_submit_feedback(
            task_id=task_id,
            verdict="down",
            comment="needs more evidence",
        )
        withdrawn = await redis_sre_submit_feedback(task_id=task_id, verdict="withdrawn")

        assert withdrawn["verdict"] == "withdrawn"
        assert withdrawn["comment"] is None
        assert withdrawn["created_at"] == first["created_at"]

        resubmit = await redis_sre_submit_feedback(task_id=task_id, verdict="withdrawn")
        assert resubmit["created_at"] == withdrawn["created_at"]
        assert resubmit["updated_at"] == withdrawn["updated_at"]

    @pytest.mark.asyncio
    async def test_mcp_validation_raises(self, task_factory):
        """Invalid verdict propagates as ValidationError — NOT a success-shaped dict.

        Deliberately verifies the anti-pattern from redis_sre_general_chat
        (swallowing errors into {"error": ..., "status": "failed"}) is absent.
        """
        task_id = await task_factory()

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            await redis_sre_submit_feedback(task_id=task_id, verdict="maybe")

        # Confirm the tool has no try/except that would swallow the error: the
        # exception must propagate, never become {"error": ..., "status": "failed"}.

    @pytest.mark.asyncio
    async def test_mcp_unknown_task_raises(self, redis_client):
        """Non-existent task_id propagates TaskNotFoundError — NOT a success-shaped dict.

        Depends on `redis_client` so the test skips cleanly when Redis is unreachable
        rather than surfacing a ConnectionError from the not-found probe.
        """
        bogus_task_id = f"tsk-nonexistent-{uuid.uuid4().hex[:8]}"

        with pytest.raises(TaskNotFoundError):
            await redis_sre_submit_feedback(task_id=bogus_task_id, verdict="down")


# ---------------------------------------------------------------------------
# Phase-2: redis_sre_get_feedback tests (US-006)
# ---------------------------------------------------------------------------


class TestMCPGetFeedback:
    """Tests for redis_sre_get_feedback MCP tool."""

    @pytest.mark.asyncio
    async def test_mcp_get_feedback_success(self, task_factory):
        """Happy path: returns a FeedbackView-shaped dict with feedback + task keys."""
        task_id = await task_factory()
        await redis_sre_submit_feedback(task_id=task_id, verdict="up", comment="Great")

        result = await redis_sre_get_feedback(task_id=task_id)

        assert isinstance(result, dict)
        assert "feedback" in result
        assert "task" in result
        assert result["feedback"]["task_id"] == task_id
        assert result["feedback"]["verdict"] == "up"
        assert result["feedback"]["comment"] == "Great"

    @pytest.mark.asyncio
    async def test_mcp_get_feedback_returns_none_when_no_feedback(self, task_factory):
        """Known task with no feedback returns None — NOT a success-shaped error dict."""
        task_id = await task_factory()

        result = await redis_sre_get_feedback(task_id=task_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_mcp_get_feedback_unknown_task_raises(self, redis_client):
        """Non-existent task_id propagates TaskNotFoundError — NOT a success-shaped dict.

        Depends on `redis_client` so the test skips cleanly when Redis is unreachable
        rather than surfacing a ConnectionError from the not-found probe.
        """
        bogus_task_id = f"tsk-nonexistent-{uuid.uuid4().hex[:8]}"

        with pytest.raises(TaskNotFoundError):
            await redis_sre_get_feedback(task_id=bogus_task_id)


# ---------------------------------------------------------------------------
# Phase-2: redis_sre_list_feedback tests (US-006)
# ---------------------------------------------------------------------------


class TestMCPListFeedback:
    """Tests for redis_sre_list_feedback MCP tool."""

    @pytest.mark.asyncio
    async def test_mcp_list_feedback_returns_items_and_count(self, task_factory):
        """Two seeded tasks with feedback appear in the result with correct shape."""
        task_id_1 = await task_factory()
        task_id_2 = await task_factory()
        await redis_sre_submit_feedback(task_id=task_id_1, verdict="up")
        await redis_sre_submit_feedback(task_id=task_id_2, verdict="down")

        result = await redis_sre_list_feedback()

        assert isinstance(result, dict)
        assert "items" in result
        assert "count" in result
        # At least our two seeded items are present (other tests may leave data).
        assert result["count"] >= 2
        assert len(result["items"]) == result["count"]
        # Each item must have feedback + task keys.
        for item in result["items"]:
            assert "feedback" in item
            assert "task" in item

    @pytest.mark.asyncio
    async def test_mcp_list_feedback_filters(self, task_factory):
        """Verdict filter returns only matching items."""
        task_up = await task_factory()
        task_down_1 = await task_factory()
        task_down_2 = await task_factory()
        await redis_sre_submit_feedback(task_id=task_up, verdict="up")
        await redis_sre_submit_feedback(task_id=task_down_1, verdict="down")
        await redis_sre_submit_feedback(task_id=task_down_2, verdict="down")

        result = await redis_sre_list_feedback(verdict="down")

        assert isinstance(result, dict)
        # All returned items must have verdict="down".
        for item in result["items"]:
            assert item["feedback"]["verdict"] == "down"
        # Our two down items must appear.
        returned_ids = {item["feedback"]["task_id"] for item in result["items"]}
        assert task_down_1 in returned_ids
        assert task_down_2 in returned_ids
        assert task_up not in returned_ids

    @pytest.mark.asyncio
    async def test_mcp_list_feedback_filters_withdrawn(self, task_factory):
        """The withdrawn verdict participates in list filtering like up/down."""
        task_up = await task_factory()
        task_withdrawn = await task_factory()
        await redis_sre_submit_feedback(task_id=task_up, verdict="up")
        await redis_sre_submit_feedback(task_id=task_withdrawn, verdict="withdrawn")

        result = await redis_sre_list_feedback(verdict="withdrawn")

        assert isinstance(result, dict)
        for item in result["items"]:
            assert item["feedback"]["verdict"] == "withdrawn"
        returned_ids = {item["feedback"]["task_id"] for item in result["items"]}
        assert task_withdrawn in returned_ids
        assert task_up not in returned_ids

    @pytest.mark.asyncio
    async def test_mcp_list_feedback_limit_clamp(self, task_factory):
        """limit=10000 is clamped to 500; result never exceeds 500 items."""
        result = await redis_sre_list_feedback(limit=10000)

        assert isinstance(result, dict)
        assert result["count"] <= 500
        assert len(result["items"]) <= 500

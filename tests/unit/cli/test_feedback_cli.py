"""CLI tests for the `feedback` subgroup (US-008, US-005).

These tests run against a real Redis instance (localhost:7843). Each test that
needs Redis is guarded by the `redis_available` fixture and cleans up after
itself. Tests that only exercise argument validation / error paths mock out
Redis entirely and run without a live server.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from click.testing import CliRunner

from redis_sre_agent.cli.feedback import feedback
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis_client():
    """Real Redis client; skip test if Redis unreachable."""
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
    """Create minimal task rows so submit_feedback accepts the task_id."""
    created: list[str] = []

    async def _make(*, thread_id: str | None = "thr-test", status: str = "done") -> str:
        task_id = f"tsk-{uuid.uuid4().hex[:12]}"
        await redis_client.set(RedisKeys.task_status(task_id), status)
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


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUpDownWithdraw:
    """AC: up / down / withdraw subcommands write JSON to stdout."""

    def test_up_down_withdraw(self, runner, task_factory):
        task_id = asyncio.get_event_loop().run_until_complete(task_factory())

        # up
        result = runner.invoke(feedback, ["up", task_id])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["verdict"] == "up"
        assert data["task_id"] == task_id

        # down with comment
        result = runner.invoke(feedback, ["down", task_id, "--comment", "foo"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["verdict"] == "down"
        assert data["comment"] == "foo"

        # withdraw
        result = runner.invoke(feedback, ["withdraw", task_id])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["verdict"] == "withdrawn"

    def test_comment_preserves_shell_like_text(self, runner, task_factory):
        """Comments with spaces, quotes, and punctuation round-trip through JSON."""
        task_id = asyncio.get_event_loop().run_until_complete(task_factory())
        comment = 'needs "INFO commandstats" output; ops/sec > 42'

        result = runner.invoke(feedback, ["down", task_id, "--comment", comment])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["comment"] == comment


class TestShow:
    """AC: show returns FeedbackView or null; exit contract."""

    def test_show_returns_null_exit_zero_when_no_feedback(self, runner, task_factory):
        task_id = asyncio.get_event_loop().run_until_complete(task_factory())
        result = runner.invoke(feedback, ["show", task_id])
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "null"

    def test_show_exits_nonzero_on_unknown_task(self, runner, redis_client):
        nonexistent = f"tsk-{uuid.uuid4().hex[:12]}"
        result = runner.invoke(feedback, ["show", nonexistent])
        assert result.exit_code != 0
        assert nonexistent in result.output or "not found" in result.output.lower()

    def test_show_returns_record_after_submission(self, runner, task_factory):
        task_id = asyncio.get_event_loop().run_until_complete(task_factory())
        runner.invoke(feedback, ["up", task_id, "--comment", "nice"])
        result = runner.invoke(feedback, ["show", task_id])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        # show now returns FeedbackView with feedback + task keys
        assert data["feedback"]["verdict"] == "up"
        assert data["feedback"]["comment"] == "nice"

    def test_show_emits_feedback_view(self, runner, task_factory):
        """AC-10: show returns FeedbackView JSON with feedback + task keys."""
        task_id = asyncio.get_event_loop().run_until_complete(task_factory())
        runner.invoke(feedback, ["up", task_id, "--comment", "great"])
        result = runner.invoke(feedback, ["show", task_id])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "feedback" in data, f"Expected 'feedback' key, got: {list(data.keys())}"
        assert "task" in data, f"Expected 'task' key, got: {list(data.keys())}"
        assert data["feedback"]["verdict"] == "up"
        assert data["task"]["task_id"] == task_id


class TestList:
    """AC: list subcommand uses SCAN, filters, and handles --limit."""

    def test_list_filters_by_verdict(self, runner, task_factory):
        """Submit feedback for 3 tasks (mix of up/down); list --verdict down shows only down."""

        async def _setup():
            t1 = await task_factory()
            t2 = await task_factory()
            t3 = await task_factory()
            return t1, t2, t3

        t1, t2, t3 = asyncio.get_event_loop().run_until_complete(_setup())

        runner.invoke(feedback, ["up", t1])
        runner.invoke(feedback, ["down", t2])
        runner.invoke(feedback, ["down", t3])

        result = runner.invoke(feedback, ["list", "--verdict", "down"])
        assert result.exit_code == 0, result.output
        # t1 (up) must NOT appear, t2 and t3 (down) must appear
        assert t2 in result.output
        assert t3 in result.output
        assert t1 not in result.output

    def test_list_uses_scan_not_keys(self, runner, task_factory):
        """If the implementation calls redis.keys(), this test will fail."""
        task_id = asyncio.get_event_loop().run_until_complete(task_factory())
        runner.invoke(feedback, ["up", task_id])

        # Patch the redis client so that calling `keys` raises an error.
        original_get_redis_client = get_redis_client

        def _patched_get_redis_client():
            real_client = original_get_redis_client()

            async def _keys_forbidden(*args, **kwargs):
                raise AssertionError("feedback list must not call redis.keys() — use scan instead")

            real_client.keys = _keys_forbidden
            return real_client

        with patch(
            "redis_sre_agent.core.feedback.get_redis_client", side_effect=_patched_get_redis_client
        ):
            result = runner.invoke(feedback, ["list"])
        assert result.exit_code == 0, result.output

    def test_list_clamps_limit_500(self, runner, redis_client):
        """--limit 1000 is clamped to 500; command succeeds."""
        result = runner.invoke(feedback, ["list", "--limit", "1000"])
        # Implementation choice: clamp to 500 (exit 0)
        assert result.exit_code == 0, result.output

    def test_list_rejects_limit_below_one(self, runner):
        """--limit 0 exits non-zero so callers do not silently get no rows."""
        result = runner.invoke(feedback, ["list", "--limit", "0"])
        assert result.exit_code != 0
        assert "limit" in result.output.lower()

    def test_list_default_is_jsonl(self, runner, task_factory):
        """AC-11: default output is JSON Lines — one FeedbackView per line."""

        async def _setup():
            t1 = await task_factory()
            t2 = await task_factory()
            return t1, t2

        t1, t2 = asyncio.get_event_loop().run_until_complete(_setup())
        runner.invoke(feedback, ["up", t1])
        runner.invoke(feedback, ["down", t2])

        result = runner.invoke(feedback, ["list"])
        assert result.exit_code == 0, result.output

        lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
        assert len(lines) >= 2, f"Expected at least 2 lines, got: {lines}"

        for line in lines:
            obj = json.loads(line)
            assert "feedback" in obj, f"Missing 'feedback' key in line: {line}"
            assert "task" in obj, f"Missing 'task' key in line: {line}"

    def test_list_table_flag_columns(self, runner, task_factory):
        """AC-12: --table renders Rich table with six column headers."""
        task_id = asyncio.get_event_loop().run_until_complete(task_factory())
        runner.invoke(feedback, ["up", task_id, "--comment", "test"])

        result = runner.invoke(feedback, ["list", "--table"])
        assert result.exit_code == 0, result.output

        output_lower = result.output.lower()
        assert "task_id" in output_lower, f"Missing 'task_id' column in: {result.output}"
        assert "status" in output_lower, f"Missing 'status' column in: {result.output}"
        assert "verdict" in output_lower, f"Missing 'verdict' column in: {result.output}"
        assert "updated_at" in output_lower, f"Missing 'updated_at' column in: {result.output}"

    def test_list_table_truncates_long_comment(self, runner, task_factory):
        """Long comments are shortened in table output while JSONL keeps full text."""
        task_id = asyncio.get_event_loop().run_until_complete(task_factory())
        long_comment = ("a" * 40) + ("b" * 40)
        runner.invoke(feedback, ["down", task_id, "--comment", long_comment])

        table_result = runner.invoke(feedback, ["list", "--table", "--verdict", "down"])
        assert table_result.exit_code == 0, table_result.output
        assert long_comment[:40] in table_result.output
        assert long_comment[40:] not in table_result.output

        json_result = runner.invoke(feedback, ["list", "--verdict", "down"])
        assert json_result.exit_code == 0, json_result.output
        assert long_comment in json_result.output

    def test_list_status_filter(self, runner, task_factory):
        """AC-11: --status filters by task.status."""

        async def _setup():
            t_done = await task_factory(status="done")
            t_failed = await task_factory(status="failed")
            return t_done, t_failed

        t_done, t_failed = asyncio.get_event_loop().run_until_complete(_setup())
        runner.invoke(feedback, ["up", t_done])
        runner.invoke(feedback, ["down", t_failed])

        result = runner.invoke(feedback, ["list", "--status", "done"])
        assert result.exit_code == 0, result.output

        lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
        task_ids_returned = set()
        for line in lines:
            obj = json.loads(line)
            task_ids_returned.add(obj["task"]["task_id"])

        assert t_done in task_ids_returned, "done task should appear"
        assert t_failed not in task_ids_returned, "failed task should not appear with --status done"

    def test_list_status_rejects_unknown(self, runner):
        """AC-11: --status with unknown value exits non-zero and emits error to stderr."""
        result = runner.invoke(feedback, ["list", "--status", "not-a-status"])
        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "not-a-status" in result.output


class TestSinceParser:
    """AC: --since rejects ISO-8601, accepts valid duration units."""

    def test_since_parser_rejects_iso(self, runner):
        result = runner.invoke(feedback, ["list", "--since", "2026-05-18"])
        assert result.exit_code != 0
        assert "ISO-8601" in result.output or "not supported" in result.output

    def test_since_parser_accepts_valid_units(self, runner, redis_client):
        for duration in ["24h", "30m", "7d", "3600s"]:
            result = runner.invoke(feedback, ["list", "--since", duration])
            assert result.exit_code == 0, (
                f"--since {duration} should be accepted but got exit {result.exit_code}: "
                f"{result.output}"
            )

    def test_since_parser_rejects_invalid_format(self, runner):
        result = runner.invoke(feedback, ["list", "--since", "invalid"])
        assert result.exit_code != 0

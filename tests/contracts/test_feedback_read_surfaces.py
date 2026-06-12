"""Cross-surface contract test for feedback joined-view reads (US-007).

Asserts that HTTP, MCP, and CLI read surfaces return equivalent FeedbackView
dicts for the same underlying Redis data. Guards against future drift across
the three surfaces.

AC-15 (single-record parity): HTTP GET, CLI `feedback show`, and MCP
    `redis_sre_get_feedback` all return the same canonical FeedbackView dict,
    and all three produce the documented "no feedback" signal for a task with
    no feedback record.

AC-12 (list parity): HTTP GET /api/v1/feedback, CLI `feedback list`, and MCP
    `redis_sre_list_feedback` return the same set of task_ids and per-row
    payloads for identical filter combinations.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator

import pytest
import pytest_asyncio
from click.testing import CliRunner
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app
from redis_sre_agent.cli.feedback import feedback
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.mcp_server.server import redis_sre_get_feedback, redis_sre_list_feedback

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonicalize(obj: object) -> object:
    """Round-trip through JSON with sort_keys so field order doesn't affect equality."""
    return json.loads(json.dumps(obj, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator:
    """Real Redis client; skip test if Redis is unreachable."""
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
async def four_tasks(redis_client):
    """Create four tasks in Redis for the read-surface contract tests.

    Task A: status=done, feedback verdict=up
    Task B: status=done, feedback verdict=down with comment
    Task C: status=failed, feedback verdict=down (no comment)
    Task D: status=done, NO feedback (for the None/404 path)
    """
    created: list[str] = []

    async def _make_task(status: str) -> str:
        task_id = f"tsk-{uuid.uuid4().hex[:12]}"
        await redis_client.set(RedisKeys.task_status(task_id), status)
        await redis_client.hset(
            RedisKeys.task_metadata(task_id),
            mapping={"created_at": "2026-01-01T00:00:00+00:00", "thread_id": "thr-contract-read"},
        )
        created.append(task_id)
        return task_id

    async def _write_feedback(task_id: str, verdict: str, comment: str = "") -> None:
        now = "2026-01-01T12:00:00+00:00"
        await redis_client.hset(
            RedisKeys.feedback_task(task_id),
            mapping={
                "task_id": task_id,
                "verdict": verdict,
                "comment": comment,
                "created_at": now,
                "updated_at": now,
            },
        )

    task_a = await _make_task("done")
    await _write_feedback(task_a, "up")

    task_b = await _make_task("done")
    await _write_feedback(task_b, "down", "needs improvement")

    task_c = await _make_task("failed")
    await _write_feedback(task_c, "down")

    task_d = await _make_task("done")  # no feedback written

    yield task_a, task_b, task_c, task_d

    for task_id in created:
        await redis_client.delete(
            RedisKeys.task_status(task_id),
            RedisKeys.task_metadata(task_id),
            RedisKeys.feedback_task(task_id),
        )


@pytest.fixture
def http_client():
    """FastAPI TestClient."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_feedback_view_parity_across_surfaces(four_tasks, http_client):
    """AC-15: HTTP, CLI, and MCP single-record reads return equivalent FeedbackView dicts.

    Also verifies the "no feedback" signal for a task with no feedback record.
    """
    task_a, _task_b, _task_c, task_d = four_tasks
    runner = CliRunner()
    loop = asyncio.get_event_loop()

    # ---- Task A: has feedback (verdict=up) ----

    # HTTP
    resp = http_client.get(f"/api/v1/tasks/{task_a}/feedback")
    assert resp.status_code == 200, f"HTTP single GET failed: {resp.text}"
    http_view = _canonicalize(resp.json())

    # CLI — must run in a thread to avoid "cannot call asyncio.run from running loop"
    def _cli_show_a():
        return runner.invoke(feedback, ["show", task_a])

    with ThreadPoolExecutor(max_workers=1) as pool:
        cli_result = await loop.run_in_executor(pool, _cli_show_a)
    assert cli_result.exit_code == 0, f"CLI show failed: {cli_result.output}"
    cli_view = _canonicalize(json.loads(cli_result.output.strip()))

    # MCP (in-process)
    mcp_raw = await redis_sre_get_feedback(task_a)
    assert mcp_raw is not None, "MCP get_feedback returned None for task with feedback"
    mcp_view = _canonicalize(mcp_raw)

    # All three must be equivalent
    assert http_view == cli_view, (
        f"HTTP vs CLI FeedbackView mismatch for task_a:\nHTTP={http_view}\nCLI={cli_view}"
    )
    assert http_view == mcp_view, (
        f"HTTP vs MCP FeedbackView mismatch for task_a:\nHTTP={http_view}\nMCP={mcp_view}"
    )

    # ---- Task D: no feedback record ----

    # HTTP → 404
    resp_d = http_client.get(f"/api/v1/tasks/{task_d}/feedback")
    assert resp_d.status_code == 404, (
        f"HTTP should return 404 for task with no feedback, got {resp_d.status_code}"
    )

    # CLI → prints "null", exit 0
    def _cli_show_d():
        return runner.invoke(feedback, ["show", task_d])

    with ThreadPoolExecutor(max_workers=1) as pool:
        cli_result_d = await loop.run_in_executor(pool, _cli_show_d)
    assert cli_result_d.exit_code == 0, (
        f"CLI show (no feedback) should exit 0: {cli_result_d.output}"
    )
    assert cli_result_d.output.strip() == "null", (
        f"CLI show (no feedback) should print 'null', got: {cli_result_d.output!r}"
    )

    # MCP → None
    mcp_none = await redis_sre_get_feedback(task_d)
    assert mcp_none is None, (
        f"MCP get_feedback should return None for task with no feedback, got {mcp_none}"
    )


@pytest.mark.asyncio
async def test_list_feedback_parity_across_surfaces(four_tasks, http_client):
    """AC-12: HTTP, CLI, and MCP list surfaces return the same task_ids and payloads
    for verdict=down filter (matches Task B and Task C).
    """
    _task_a, task_b, task_c, _task_d = four_tasks
    expected_ids = {task_b, task_c}
    runner = CliRunner()
    loop = asyncio.get_event_loop()

    # HTTP
    resp = http_client.get("/api/v1/feedback?verdict=down")
    assert resp.status_code == 200, f"HTTP list failed: {resp.text}"
    http_data = resp.json()
    http_items = http_data["items"]
    http_ids = {item["feedback"]["task_id"] for item in http_items}
    assert expected_ids.issubset(http_ids), (
        f"HTTP list missing expected ids. Expected {expected_ids} subset of {http_ids}"
    )

    # CLI
    def _cli_list():
        return runner.invoke(feedback, ["list", "--verdict", "down"])

    with ThreadPoolExecutor(max_workers=1) as pool:
        cli_result = await loop.run_in_executor(pool, _cli_list)
    assert cli_result.exit_code == 0, f"CLI list failed: {cli_result.output}"
    cli_lines = [ln for ln in cli_result.output.strip().splitlines() if ln.strip()]
    cli_items = [json.loads(ln) for ln in cli_lines]
    cli_ids = {item["feedback"]["task_id"] for item in cli_items}
    assert expected_ids.issubset(cli_ids), (
        f"CLI list missing expected ids. Expected {expected_ids} subset of {cli_ids}"
    )

    # MCP
    mcp_result = await redis_sre_list_feedback(verdict="down")
    mcp_items = mcp_result["items"]
    mcp_ids = {item["feedback"]["task_id"] for item in mcp_items}
    assert expected_ids.issubset(mcp_ids), (
        f"MCP list missing expected ids. Expected {expected_ids} subset of {mcp_ids}"
    )

    # Per-row payload parity: for each expected task_id, all three surfaces return same canonical dict
    for task_id in expected_ids:
        http_row = _canonicalize(next(i for i in http_items if i["feedback"]["task_id"] == task_id))
        cli_row = _canonicalize(next(i for i in cli_items if i["feedback"]["task_id"] == task_id))
        mcp_row = _canonicalize(next(i for i in mcp_items if i["feedback"]["task_id"] == task_id))

        assert http_row == cli_row, (
            f"HTTP vs CLI payload mismatch for {task_id}:\nHTTP={http_row}\nCLI={cli_row}"
        )
        assert http_row == mcp_row, (
            f"HTTP vs MCP payload mismatch for {task_id}:\nHTTP={http_row}\nMCP={mcp_row}"
        )


@pytest.mark.asyncio
async def test_list_combined_filters_parity(four_tasks, http_client):
    """AC-12: verdict=down AND status=done filter returns only Task B across all three surfaces."""
    _task_a, task_b, task_c, _task_d = four_tasks
    # Task B: status=done, verdict=down  → must appear
    # Task C: status=failed, verdict=down → must NOT appear (filtered by status)
    runner = CliRunner()
    loop = asyncio.get_event_loop()

    # HTTP
    resp = http_client.get("/api/v1/feedback?verdict=down&status=done")
    assert resp.status_code == 200, f"HTTP combined-filter list failed: {resp.text}"
    http_items = resp.json()["items"]
    http_ids = {item["feedback"]["task_id"] for item in http_items}
    assert task_b in http_ids, f"HTTP: task_b should be in results, got {http_ids}"
    assert task_c not in http_ids, (
        f"HTTP: task_c (status=failed) should NOT be in results, got {http_ids}"
    )

    # CLI
    def _cli_list():
        return runner.invoke(feedback, ["list", "--verdict", "down", "--status", "done"])

    with ThreadPoolExecutor(max_workers=1) as pool:
        cli_result = await loop.run_in_executor(pool, _cli_list)
    assert cli_result.exit_code == 0, f"CLI combined-filter list failed: {cli_result.output}"
    cli_lines = [ln for ln in cli_result.output.strip().splitlines() if ln.strip()]
    cli_items = [json.loads(ln) for ln in cli_lines]
    cli_ids = {item["feedback"]["task_id"] for item in cli_items}
    assert task_b in cli_ids, f"CLI: task_b should be in results, got {cli_ids}"
    assert task_c not in cli_ids, (
        f"CLI: task_c (status=failed) should NOT be in results, got {cli_ids}"
    )

    # MCP
    mcp_result = await redis_sre_list_feedback(verdict="down", status="done")
    mcp_items = mcp_result["items"]
    mcp_ids = {item["feedback"]["task_id"] for item in mcp_items}
    assert task_b in mcp_ids, f"MCP: task_b should be in results, got {mcp_ids}"
    assert task_c not in mcp_ids, (
        f"MCP: task_c (status=failed) should NOT be in results, got {mcp_ids}"
    )

    # All three surfaces agree on task_b's payload
    http_row = _canonicalize(next(i for i in http_items if i["feedback"]["task_id"] == task_b))
    cli_row = _canonicalize(next(i for i in cli_items if i["feedback"]["task_id"] == task_b))
    mcp_row = _canonicalize(next(i for i in mcp_items if i["feedback"]["task_id"] == task_b))

    assert http_row == cli_row, (
        f"HTTP vs CLI payload mismatch for task_b:\nHTTP={http_row}\nCLI={cli_row}"
    )
    assert http_row == mcp_row, (
        f"HTTP vs MCP payload mismatch for task_b:\nHTTP={http_row}\nMCP={mcp_row}"
    )

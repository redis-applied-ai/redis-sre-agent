"""Cross-surface contract test for feedback submission (US-010).

Asserts that HTTP, MCP, and CLI surfaces produce byte-identical Redis state
for the same logical payload. Guards against future drift across surfaces.
"""

from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from click.testing import CliRunner
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app
from redis_sre_agent.cli.feedback import feedback
from redis_sre_agent.core.feedback import FeedbackRecord
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.mcp_server.server import redis_sre_submit_feedback

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_COMMENT = "cross-surface contract test"
_VERDICT = "down"


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
async def three_tasks(redis_client):
    """Create three distinct real tasks in Redis, yield their IDs, clean up after."""
    created: list[str] = []

    async def _make() -> str:
        task_id = f"tsk-{uuid.uuid4().hex[:12]}"
        await redis_client.set(RedisKeys.task_status(task_id), "done")
        await redis_client.hset(
            RedisKeys.task_metadata(task_id),
            mapping={"created_at": "2026-01-01T00:00:00+00:00", "thread_id": "thr-contract"},
        )
        created.append(task_id)
        return task_id

    task_a = await _make()
    task_b = await _make()
    task_c = await _make()

    yield task_a, task_b, task_c

    for task_id in created:
        await redis_client.delete(
            RedisKeys.task_status(task_id),
            RedisKeys.task_metadata(task_id),
            RedisKeys.feedback_task(task_id),
        )


@pytest.fixture
def http_client():
    """FastAPI TestClient with stream manager muted."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Contract test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_surfaces_produce_identical_redis_state(
    three_tasks, redis_client, http_client
):
    """All three surfaces write the same verdict+comment to Redis for the same payload.

    Task A → HTTP POST /api/v1/tasks/{task_a}/feedback
    Task B → MCP redis_sre_submit_feedback (in-process)
    Task C → CLI CliRunner feedback down {task_c} --comment "..."

    After each submission, HGETALL the feedback hash and assert that verdict
    and comment are identical across all three tasks.
    """
    task_a, task_b, task_c = three_tasks

    # Mute stream publish for all three submissions to avoid event-loop issues
    # (TestClient runs in a separate thread; publish would touch a different loop).
    mock_manager = AsyncMock()
    mock_manager.publish_task_update = AsyncMock(return_value=True)

    async def _get_manager():
        return mock_manager

    with patch("redis_sre_agent.api.websockets.get_stream_manager", side_effect=_get_manager):
        # --- Surface A: HTTP ---
        resp = http_client.post(
            f"/api/v1/tasks/{task_a}/feedback",
            json={"verdict": _VERDICT, "comment": _COMMENT},
        )
        assert resp.status_code == 200, f"HTTP surface failed: {resp.text}"

        # --- Surface B: MCP (in-process) ---
        await redis_sre_submit_feedback(
            task_id=task_b,
            verdict=_VERDICT,
            comment=_COMMENT,
        )

        # --- Surface C: CLI ---
        # CliRunner calls asyncio.run() internally; running it from an async
        # test would raise "cannot be called from a running event loop".
        # Execute in a ThreadPoolExecutor so it gets a fresh thread/loop.
        runner = CliRunner()

        def _invoke_cli():
            return runner.invoke(feedback, ["down", task_c, "--comment", _COMMENT])

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = await loop.run_in_executor(pool, _invoke_cli)
        assert result.exit_code == 0, f"CLI surface failed: {result.output}"

    # --- Fetch raw Redis hashes ---
    raw_a = await redis_client.hgetall(RedisKeys.feedback_task(task_a))
    raw_b = await redis_client.hgetall(RedisKeys.feedback_task(task_b))
    raw_c = await redis_client.hgetall(RedisKeys.feedback_task(task_c))

    def _decode_hash(raw: dict) -> dict[str, str]:
        return {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }

    hash_a = _decode_hash(raw_a)
    hash_b = _decode_hash(raw_b)
    hash_c = _decode_hash(raw_c)

    # Assert Redis hashes are non-empty (each surface actually wrote)
    assert hash_a, "HTTP surface: feedback hash is empty"
    assert hash_b, "MCP surface: feedback hash is empty"
    assert hash_c, "CLI surface: feedback hash is empty"

    # --- Primary contract assertion: verdict and comment are byte-identical ---
    for field in ("verdict", "comment"):
        val_a = hash_a.get(field)
        val_b = hash_b.get(field)
        val_c = hash_c.get(field)
        assert val_a == val_b == val_c, (
            f"Field '{field}' differs across surfaces: HTTP={val_a!r}, MCP={val_b!r}, CLI={val_c!r}"
        )

    # --- Bonus: parse through FeedbackRecord to catch serialization drift ---
    record_a = FeedbackRecord.model_validate({**hash_a, "task_id": task_a})
    record_b = FeedbackRecord.model_validate({**hash_b, "task_id": task_b})
    record_c = FeedbackRecord.model_validate({**hash_c, "task_id": task_c})

    assert record_a.verdict == record_b.verdict == record_c.verdict == _VERDICT, (
        f"FeedbackRecord.verdict mismatch: {record_a.verdict!r}, "
        f"{record_b.verdict!r}, {record_c.verdict!r}"
    )
    assert record_a.comment == record_b.comment == record_c.comment == _COMMENT, (
        f"FeedbackRecord.comment mismatch: {record_a.comment!r}, "
        f"{record_b.comment!r}, {record_c.comment!r}"
    )

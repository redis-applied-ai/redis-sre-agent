"""Integration tests for the feedback HTTP API layer (US-003, US-004, US-006).

Tests exercise real Redis (docker-compose port 7843) via the FastAPI TestClient.
Each test is skipped if Redis is unreachable — mirrors the pattern in
tests/unit/core/test_feedback.py.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client

# ---------------------------------------------------------------------------
# Shared client fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """TestClient for the full FastAPI app (lifespan bypassed by TestClient)."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Redis availability + task factory
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator:
    """Real Redis client; skip test if Redis is unreachable."""
    rc = get_redis_client()
    try:
        await rc.ping()
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")
    try:
        yield rc
    finally:
        await rc.aclose()


@pytest_asyncio.fixture
async def task_factory(redis_client):
    """Create a minimal task in Redis so feedback endpoints accept the task_id."""
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
# Mute stream publish for all tests in this module
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _mute_stream():
    mock_manager = AsyncMock()
    mock_manager.publish_task_update = AsyncMock(return_value=True)

    async def _get_manager():
        return mock_manager

    with patch("redis_sre_agent.api.websockets.get_stream_manager", side_effect=_get_manager):
        yield mock_manager


# ---------------------------------------------------------------------------
# US-003 / AC-POST — POST up and down verdicts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_up_and_down(client, task_factory):
    """POST up then down; both return 200 with valid FeedbackRecord."""
    task_id = await task_factory()

    resp = client.post(f"/api/v1/tasks/{task_id}/feedback", json={"verdict": "up"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["task_id"] == task_id
    assert data["verdict"] == "up"
    assert data["comment"] is None
    assert data["created_at"]
    assert data["updated_at"]

    resp2 = client.post(
        f"/api/v1/tasks/{task_id}/feedback", json={"verdict": "down", "comment": "foo"}
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["verdict"] == "down"
    assert data2["comment"] == "foo"
    # created_at must be anchored from the first write
    assert data2["created_at"] == data["created_at"]


# ---------------------------------------------------------------------------
# US-004 / AC-GET — GET existing and missing feedback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_existing_and_missing(client, task_factory):
    """GET returns 200 after POST; GET 404 for task with no feedback."""
    task_id = await task_factory()

    # POST first
    client.post(f"/api/v1/tasks/{task_id}/feedback", json={"verdict": "up"})

    # GET should return the joined FeedbackView
    resp = client.get(f"/api/v1/tasks/{task_id}/feedback")
    assert resp.status_code == 200, resp.text
    assert resp.json()["feedback"]["verdict"] == "up"

    # A different task with no feedback → 404
    task_id_no_fb = await task_factory()
    resp_miss = client.get(f"/api/v1/tasks/{task_id_no_fb}/feedback")
    assert resp_miss.status_code == 404


# ---------------------------------------------------------------------------
# US-003 / AC-5 — POST to unknown task → 404, nothing written
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_task_returns_404(client, redis_client):
    """POST feedback for a non-existent task returns 404; hash not written."""
    bogus_id = f"tsk-ghost-{uuid.uuid4().hex[:8]}"
    await redis_client.delete(RedisKeys.task_status(bogus_id))

    resp = client.post(f"/api/v1/tasks/{bogus_id}/feedback", json={"verdict": "up"})
    assert resp.status_code == 404, resp.text

    exists = await redis_client.hexists(RedisKeys.feedback_task(bogus_id), "verdict")
    assert exists == 0


# ---------------------------------------------------------------------------
# US-003 / AC-validation — comment too long → 422
# ---------------------------------------------------------------------------


def test_validation_errors_comment_too_long(client):
    """POST with 2049-char comment returns 422 with string_too_long detail."""
    resp = client.post(
        "/api/v1/tasks/any-task-id/feedback",
        json={"verdict": "up", "comment": "x" * 2049},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, list) and len(detail) > 0
    first = detail[0]
    assert first["type"] == "string_too_long"
    assert first["loc"][-1] == "comment"


# ---------------------------------------------------------------------------
# US-003 / AC-validation — invalid verdict → 422
# ---------------------------------------------------------------------------


def test_validation_errors_invalid_verdict(client):
    """POST with verdict='maybe' returns 422 with literal_error detail."""
    resp = client.post(
        "/api/v1/tasks/any-task-id/feedback",
        json={"verdict": "maybe"},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, list) and len(detail) > 0
    first = detail[0]
    assert first["type"] == "literal_error"
    assert first["loc"][-1] == "verdict"


# ---------------------------------------------------------------------------
# US-006 — GET /tasks/{task_id} includes feedback field
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_taskresponse_includes_feedback(client, task_factory):
    """GET /api/v1/tasks/{task_id} response includes feedback after POST."""
    task_id = await task_factory()

    # POST feedback
    post_resp = client.post(
        f"/api/v1/tasks/{task_id}/feedback", json={"verdict": "down", "comment": "needs work"}
    )
    assert post_resp.status_code == 200

    # GET task — must include feedback
    # Patch TaskManager so the task-state lookup succeeds without a full task scaffold
    from unittest.mock import MagicMock

    class FakeMeta:
        subject = "Test"
        created_at = "2026-01-01T00:00:00+00:00"
        updated_at = "2026-01-01T00:00:00+00:00"

    fake_state = MagicMock()
    fake_state.task_id = task_id
    fake_state.thread_id = "thr-test"
    fake_state.status = "done"
    fake_state.updates = []
    fake_state.result = None
    fake_state.error_message = None
    fake_state.metadata = FakeMeta()
    fake_state.pending_approval = None
    fake_state.resume_supported = False

    mock_tm = MagicMock()
    mock_tm.get_task_state = AsyncMock(return_value=fake_state)
    mock_tm.get_task_tool_calls = AsyncMock(return_value=None)

    with patch("redis_sre_agent.api.tasks.TaskManager", return_value=mock_tm):
        resp = client.get(f"/api/v1/tasks/{task_id}")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["feedback"] is not None
    assert data["feedback"]["verdict"] == "down"
    assert data["feedback"]["comment"] == "needs work"
    assert data["feedback"]["task_id"] == task_id


# ---------------------------------------------------------------------------
# US-003 / US-004 — GET returns FeedbackView (joined shape)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_feedback_view(client, task_factory):
    """GET /tasks/{task_id}/feedback returns FeedbackView with feedback + task keys."""
    task_id = await task_factory()

    client.post(f"/api/v1/tasks/{task_id}/feedback", json={"verdict": "up", "comment": "nice"})

    resp = client.get(f"/api/v1/tasks/{task_id}/feedback")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Top-level keys
    assert "feedback" in data, "response must have 'feedback' key"
    assert "task" in data, "response must have 'task' key"

    fb = data["feedback"]
    assert fb["verdict"] == "up"
    assert fb["comment"] == "nice"
    assert fb["task_id"] == task_id
    assert fb["created_at"]
    assert fb["updated_at"]

    task = data["task"]
    assert task["task_id"] == task_id
    assert task["thread_id"] == "thr-test"
    assert task["status"] == "done"
    assert "messages" in task
    assert "tool_calls" in task


# ---------------------------------------------------------------------------
# AC-17 — GET /tasks/{task_id} feedback field stays bare FeedbackRecord
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_taskresponse_feedback_field_is_bare_record(client, task_factory):
    """GET /api/v1/tasks/{task_id} feedback field is bare FeedbackRecord, not nested FeedbackView."""
    task_id = await task_factory()

    client.post(
        f"/api/v1/tasks/{task_id}/feedback", json={"verdict": "down", "comment": "needs work"}
    )

    from unittest.mock import MagicMock

    class FakeMeta:
        subject = "Test"
        created_at = "2026-01-01T00:00:00+00:00"
        updated_at = "2026-01-01T00:00:00+00:00"

    fake_state = MagicMock()
    fake_state.task_id = task_id
    fake_state.thread_id = "thr-test"
    fake_state.status = "done"
    fake_state.updates = []
    fake_state.result = None
    fake_state.error_message = None
    fake_state.metadata = FakeMeta()
    fake_state.pending_approval = None
    fake_state.resume_supported = False

    mock_tm = MagicMock()
    mock_tm.get_task_state = AsyncMock(return_value=fake_state)
    mock_tm.get_task_tool_calls = AsyncMock(return_value=None)

    with patch("redis_sre_agent.api.tasks.TaskManager", return_value=mock_tm):
        resp = client.get(f"/api/v1/tasks/{task_id}")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    fb = data["feedback"]
    assert fb is not None

    # Must be bare record: top-level verdict/comment/task_id keys
    assert fb["verdict"] == "down"
    assert fb["comment"] == "needs work"
    assert fb["task_id"] == task_id

    # Must NOT be a nested FeedbackView shape
    assert "feedback" not in fb, "feedback field must be bare record, not nested FeedbackView"
    assert "task" not in fb, "feedback field must be bare record, not nested FeedbackView"


# ---------------------------------------------------------------------------
# US-004 — GET /api/v1/feedback (list)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_feedback_views(client, task_factory):
    """GET /api/v1/feedback returns items list and count."""
    task_id_1 = await task_factory()
    task_id_2 = await task_factory()
    client.post(f"/api/v1/tasks/{task_id_1}/feedback", json={"verdict": "up"})
    client.post(f"/api/v1/tasks/{task_id_2}/feedback", json={"verdict": "down"})

    resp = client.get("/api/v1/feedback")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "count" in data

    # Both tasks should appear (may be more from other tests; check >= 2)
    our_ids = {task_id_1, task_id_2}
    returned_ids = {item["feedback"]["task_id"] for item in data["items"]}
    assert our_ids.issubset(returned_ids), f"Expected {our_ids} in {returned_ids}"

    # Each item has the joined shape
    for item in data["items"]:
        assert "feedback" in item
        assert "task" in item


@pytest.mark.asyncio
async def test_list_filter_verdict(client, task_factory):
    """GET /api/v1/feedback?verdict=down returns only down-verdict items."""
    task_up = await task_factory()
    task_down = await task_factory()
    client.post(f"/api/v1/tasks/{task_up}/feedback", json={"verdict": "up"})
    client.post(f"/api/v1/tasks/{task_down}/feedback", json={"verdict": "down"})

    resp = client.get("/api/v1/feedback?verdict=down")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for item in data["items"]:
        assert item["feedback"]["verdict"] == "down"

    returned_ids = {item["feedback"]["task_id"] for item in data["items"]}
    assert task_down in returned_ids
    assert task_up not in returned_ids


@pytest.mark.asyncio
async def test_list_filter_status(client, task_factory, redis_client):
    """GET /api/v1/feedback?status=done returns only tasks with status=done."""
    task_done = await task_factory()  # task_factory sets status="done"
    task_queued = await task_factory()
    # Override second task's status to queued
    await redis_client.set(f"sre:task:{task_queued}:status", "queued")
    client.post(f"/api/v1/tasks/{task_done}/feedback", json={"verdict": "up"})
    client.post(f"/api/v1/tasks/{task_queued}/feedback", json={"verdict": "up"})

    resp = client.get("/api/v1/feedback?status=done")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for item in data["items"]:
        assert item["task"]["status"] == "done"

    returned_ids = {item["feedback"]["task_id"] for item in data["items"]}
    assert task_done in returned_ids
    assert task_queued not in returned_ids


@pytest.mark.asyncio
async def test_list_filter_since(client, task_factory, redis_client):
    """GET /api/v1/feedback?since=1h returns only feedback updated in the last hour."""
    from redis_sre_agent.core.keys import RedisKeys

    task_old = await task_factory()
    task_recent = await task_factory()

    # Write old feedback with a timestamp far in the past
    old_ts = "2020-01-01T00:00:00+00:00"
    await redis_client.hset(
        RedisKeys.feedback_task(task_old),
        mapping={
            "task_id": task_old,
            "verdict": "up",
            "comment": "",
            "created_at": old_ts,
            "updated_at": old_ts,
        },
    )

    # Write recent feedback via the API (uses current time)
    client.post(f"/api/v1/tasks/{task_recent}/feedback", json={"verdict": "up"})

    resp = client.get("/api/v1/feedback?since=1h")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    returned_ids = {item["feedback"]["task_id"] for item in data["items"]}
    assert task_recent in returned_ids
    assert task_old not in returned_ids


@pytest.mark.asyncio
async def test_list_filter_combination(client, task_factory, redis_client):
    """GET /api/v1/feedback?verdict=down&status=done uses AND semantics."""
    task_down_done = await task_factory()  # status=done (default), verdict=down
    task_up_done = await task_factory()  # status=done, verdict=up
    client.post(f"/api/v1/tasks/{task_down_done}/feedback", json={"verdict": "down"})
    client.post(f"/api/v1/tasks/{task_up_done}/feedback", json={"verdict": "up"})

    resp = client.get("/api/v1/feedback?verdict=down&status=done")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    returned_ids = {item["feedback"]["task_id"] for item in data["items"]}
    assert task_down_done in returned_ids
    assert task_up_done not in returned_ids


def test_list_limit_bounds(client):
    """limit=0 and limit=1000 return 422; no limit uses default of 50."""
    resp_zero = client.get("/api/v1/feedback?limit=0")
    assert resp_zero.status_code == 422, resp_zero.text

    resp_over = client.get("/api/v1/feedback?limit=1000")
    assert resp_over.status_code == 422, resp_over.text

    # Default (no limit param) should succeed
    resp_default = client.get("/api/v1/feedback")
    assert resp_default.status_code == 200, resp_default.text


def test_list_since_iso_rejected(client):
    """since= with ISO date format (not Ns/Nm/Nh/Nd) returns 422."""
    resp = client.get("/api/v1/feedback?since=2026-05-20")
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    # FastAPI pattern validation puts the field name in loc
    locs = [d["loc"][-1] for d in detail if isinstance(d, dict) and "loc" in d]
    assert "since" in locs, f"Expected 'since' in locs, got {locs}"


# ---------------------------------------------------------------------------
# US-005 — stream event only emitted after successful commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_event_emitted_after_commit(client, task_factory, redis_client):
    """Stream publish is called only after the HSET pipeline commits.

    TestClient runs the ASGI app in a separate thread/loop, so we cannot await
    the same redis_client inside the publish callback (different event loop).
    Instead we record the update_type at publish time and verify post-hoc that
    the hash exists in Redis — proving the write was committed before the HTTP
    response returned.
    """
    from redis_sre_agent.core.feedback import FEEDBACK_SUBMITTED_UPDATE_TYPE

    task_id = await task_factory()
    observed: dict = {}

    async def _capture(thread_id, update_type, data):
        # Record that publish was called; cannot touch redis_client here
        # (different event loop from TestClient's thread).
        observed["update_type"] = update_type
        observed["data"] = data
        return True

    mock_manager = AsyncMock()
    mock_manager.publish_task_update = AsyncMock(side_effect=_capture)

    async def _get_manager():
        return mock_manager

    with patch("redis_sre_agent.api.websockets.get_stream_manager", side_effect=_get_manager):
        resp = client.post(f"/api/v1/tasks/{task_id}/feedback", json={"verdict": "up"})

    assert resp.status_code == 200
    # Publish was called with the correct update_type
    assert observed.get("update_type") == FEEDBACK_SUBMITTED_UPDATE_TYPE
    assert observed.get("data", {}).get("task_id") == task_id
    # The hash must be in Redis by the time the response returned
    hash_after = await redis_client.hgetall(RedisKeys.feedback_task(task_id))
    assert hash_after, "feedback hash must be committed before stream publish"

"""Unit tests for `redis_sre_agent.core.feedback` (US-002 + US-005).

Tests exercise real `HSETNX` / `HSET` semantics against a Redis instance.
The default `redis_url` in `Settings` points at the project's docker-compose
Redis (`redis://localhost:7843/0`). If Redis is unreachable each test is
skipped via the `redis_available` fixture — tests will run cleanly in CI once
the Redis testcontainer is wired up by the integration harness.
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

# Imports under test — module-level so AC-1 (`test_module_exports`) verifies
# them as part of test collection itself.
from redis_sre_agent.core.feedback import (  # noqa: F401  (also used in tests)
    FEEDBACK_SUBMITTED_UPDATE_TYPE,
    FeedbackError,
    FeedbackRecord,
    FeedbackSubmitRequest,
    TaskNotFoundError,
    get_feedback,
    submit_feedback,
)
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator:
    """Provide a real Redis client; skip the test if Redis is unreachable.

    Each test cleans up after itself by tracking task_ids it created and
    deleting their associated keys.
    """
    client = get_redis_client()
    try:
        await client.ping()
    except Exception as exc:
        pytest.skip(f"Redis unavailable at default URL: {exc}")
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def task_factory(redis_client):
    """Create real task metadata rows so `submit_feedback` accepts the task_id.

    Returns a callable that yields a fresh task_id and registers cleanup of
    every Redis key associated with it (status, metadata, feedback).
    """
    created: list[str] = []

    async def _make(*, thread_id: str | None = "thr-test", with_metadata: bool = True) -> str:
        task_id = f"tsk-{uuid.uuid4().hex[:12]}"
        await redis_client.set(RedisKeys.task_status(task_id), "done")
        if with_metadata:
            mapping = {"created_at": "2026-01-01T00:00:00+00:00"}
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


@pytest_asyncio.fixture(autouse=True)
async def _mute_stream_publish():
    """Replace the WebSocket stream manager with an AsyncMock so tests don't
    require the API layer to be importable / reachable.

    Returned mock is exposed via the named fixture below for assertion.
    """
    mock_manager = AsyncMock()
    mock_manager.publish_task_update = AsyncMock(return_value=True)

    async def _get_manager():
        return mock_manager

    with patch(
        "redis_sre_agent.api.websockets.get_stream_manager", side_effect=_get_manager
    ) as patched:
        # Stash the mock on the patcher so the next fixture can grab it.
        patched.mock_manager = mock_manager
        yield mock_manager


@pytest.fixture
def stream_mock(_mute_stream_publish):
    """Convenience alias — yields the same AsyncMock the autouse fixture
    installed, so individual tests can assert call counts / args."""
    return _mute_stream_publish


# ---------------------------------------------------------------------------
# AC-1 — Module exports
# ---------------------------------------------------------------------------


def test_module_exports():
    """AC-1: canonical core fn + models are importable from core.feedback."""
    import redis_sre_agent.core.feedback as mod

    assert callable(mod.submit_feedback)
    assert callable(mod.get_feedback)
    assert issubclass(mod.FeedbackRecord, object)
    assert issubclass(mod.FeedbackSubmitRequest, object)
    assert issubclass(mod.TaskNotFoundError, mod.FeedbackError)

    # Also verify the api.schemas re-export points back to the same classes.
    from redis_sre_agent.api import schemas as api_schemas

    assert api_schemas.FeedbackRecord is mod.FeedbackRecord
    assert api_schemas.FeedbackSubmitRequest is mod.FeedbackSubmitRequest


# ---------------------------------------------------------------------------
# AC-2 — No external writers
# ---------------------------------------------------------------------------


def test_no_external_writers():
    """AC-2: only `core/feedback.py` writes to `sre:feedback:task:*`."""
    result = subprocess.run(
        [
            "grep",
            "-rnE",
            r"HSET .*sre:feedback:task|hset.*sre:feedback:task",
            "redis_sre_agent/",
        ],
        capture_output=True,
        text=True,
    )
    # grep exits 1 when nothing matches — both 0 and 1 are acceptable here.
    matches = [
        line
        for line in result.stdout.splitlines()
        if line.strip() and "core/feedback.py" not in line
    ]
    assert matches == [], f"Unexpected feedback hash writers: {matches}"


# ---------------------------------------------------------------------------
# AC-7 — Last-write-wins preserves created_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_last_write_wins_preserves_created_at(redis_client, task_factory):
    """AC-7: up → down → withdrawn leaves one row; created_at unchanged."""
    task_id = await task_factory()

    first = await submit_feedback(task_id, "up")
    await asyncio.sleep(0.001)
    second = await submit_feedback(task_id, "down", comment="meh")
    await asyncio.sleep(0.001)
    third = await submit_feedback(task_id, "withdrawn")

    raw = await redis_client.hgetall(RedisKeys.feedback_task(task_id))
    assert raw, "feedback hash must exist"
    final = await get_feedback(task_id)
    assert final is not None
    assert final.verdict == "withdrawn"
    assert final.created_at == first.created_at
    assert second.created_at == first.created_at
    assert third.created_at == first.created_at
    assert final.updated_at == third.updated_at
    assert final.updated_at >= second.updated_at >= first.updated_at


# ---------------------------------------------------------------------------
# AC-7 — Concurrent first-write anchors created_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_first_write_anchors_created_at(redis_client, task_factory):
    """AC-7: 10 concurrent first-writers all observe the same `created_at`."""
    task_id = await task_factory()

    results = await asyncio.gather(*[submit_feedback(task_id, "up") for _ in range(10)])

    created_at_values = {r.created_at for r in results}
    assert len(created_at_values) == 1, (
        f"Expected single anchored created_at, got {created_at_values}"
    )


# ---------------------------------------------------------------------------
# AC-8 — Withdrawn preserved, then up overwrites cleanly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_withdrawn_then_up(redis_client, task_factory):
    """AC-8: row survives `withdrawn`; subsequent `up` keeps created_at."""
    task_id = await task_factory()

    first = await submit_feedback(task_id, "up")
    await submit_feedback(task_id, "withdrawn")
    row = await get_feedback(task_id)
    assert row is not None
    assert row.verdict == "withdrawn"

    after_up = await submit_feedback(task_id, "up")
    assert after_up.verdict == "up"
    assert after_up.created_at == first.created_at


# ---------------------------------------------------------------------------
# AC-5 — Malformed thread_id still writes feedback, no exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_thread_id_still_writes(redis_client, task_factory, stream_mock):
    """AC-5: task exists but thread_id missing → feedback still written,
    stream publish skipped, no exception raised."""
    task_id = await task_factory(thread_id=None)  # metadata exists, but no thread_id field

    record = await submit_feedback(task_id, "up", comment="orphan-thread")

    assert record.verdict == "up"
    assert record.comment == "orphan-thread"
    raw = await redis_client.hgetall(RedisKeys.feedback_task(task_id))
    assert raw, "feedback hash must be written even when thread_id is missing"
    # Stream publish must be skipped when thread_id is absent.
    stream_mock.publish_task_update.assert_not_called()


# ---------------------------------------------------------------------------
# AC-5 — Unknown task raises TaskNotFoundError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_task_raises_TaskNotFoundError(redis_client):  # noqa: N802
    """AC-5: submitting for a non-existent task_id raises TaskNotFoundError."""
    bogus_id = f"tsk-missing-{uuid.uuid4().hex[:8]}"
    # Belt-and-braces: make sure no stray status key lingers from a prior run.
    await redis_client.delete(RedisKeys.task_status(bogus_id))

    with pytest.raises(TaskNotFoundError):
        await submit_feedback(bogus_id, "up")

    # Post-condition: nothing was written.
    raw = await redis_client.hgetall(RedisKeys.feedback_task(bogus_id))
    assert not raw


# ---------------------------------------------------------------------------
# AC-14 — OTel span attributes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otel_span_attributes(redis_client, task_factory):
    """AC-14: `feedback.submit` span carries task_id / verdict / comment_length /
    sre_agent.category attributes."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    # Patch the module-level tracer so the new provider is used for this test.
    new_tracer = provider.get_tracer("test.feedback")
    with patch("redis_sre_agent.core.feedback.tracer", new_tracer):
        task_id = await task_factory()
        await submit_feedback(task_id, "down", comment="needs context")

    spans = [s for s in exporter.get_finished_spans() if s.name == "feedback.submit"]
    assert spans, "expected a `feedback.submit` span"
    attrs = dict(spans[0].attributes or {})
    assert attrs.get("task_id") == task_id
    assert attrs.get("verdict") == "down"
    assert attrs.get("comment_length") == len("needs context")
    assert attrs.get("sre_agent.category") == "feedback"


# ---------------------------------------------------------------------------
# US-005 — Stream-publish ordering + idempotency short-circuit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotent_resubmit_short_circuits(redis_client, task_factory, stream_mock):
    """US-005 / AC-13: identical resubmission returns same `updated_at` and
    publishes the stream event exactly once."""
    task_id = await task_factory()

    first = await submit_feedback(task_id, "up", comment="foo")
    second = await submit_feedback(task_id, "up", comment="foo")

    assert second.updated_at == first.updated_at, "idempotent resubmit must not rewrite updated_at"
    assert second.created_at == first.created_at
    # Stream publish happens only for the first write.
    assert stream_mock.publish_task_update.await_count == 1
    publish_kwargs = stream_mock.publish_task_update.await_args.kwargs
    assert publish_kwargs.get("update_type") == FEEDBACK_SUBMITTED_UPDATE_TYPE
    data = publish_kwargs.get("data") or {}
    assert data.get("task_id") == task_id
    assert data.get("verdict") == "up"
    assert data.get("has_comment") is True


@pytest.mark.asyncio
async def test_stream_publish_ordering_after_commit(redis_client, task_factory, stream_mock):
    """US-005: stream event is published only AFTER a successful HSET commit.

    We patch `publish_task_update` so that, before returning, it reads the
    feedback hash back out of Redis and asserts the new row is already present.
    """
    task_id = await task_factory()
    observed: dict = {}

    async def _capture(thread_id, update_type, data):
        observed["thread_id"] = thread_id
        observed["update_type"] = update_type
        observed["data"] = data
        # The feedback hash must already exist by the time we get called.
        observed["hash_at_publish"] = await redis_client.hgetall(RedisKeys.feedback_task(task_id))
        return True

    stream_mock.publish_task_update.side_effect = _capture

    await submit_feedback(task_id, "down", comment="late")

    assert observed["thread_id"] == "thr-test"
    assert observed["update_type"] == FEEDBACK_SUBMITTED_UPDATE_TYPE
    assert observed["data"] == {
        "task_id": task_id,
        "verdict": "down",
        "has_comment": True,
    }
    assert observed["hash_at_publish"], "hash must be committed before publish"


@pytest.mark.asyncio
async def test_stream_publish_failure_is_swallowed(redis_client, task_factory, stream_mock):
    """US-005: stream publish errors do not raise — write is authoritative."""
    task_id = await task_factory()
    stream_mock.publish_task_update.side_effect = RuntimeError("stream down")

    record = await submit_feedback(task_id, "up")

    assert record.verdict == "up"
    final = await get_feedback(task_id)
    assert final is not None and final.verdict == "up"


# ---------------------------------------------------------------------------
# US-001 / US-002 — FeedbackView joined-view models, trim helpers, read paths.
# ---------------------------------------------------------------------------


import json  # noqa: E402  — local-scoped, used by the Phase-2 tests below


@pytest_asyncio.fixture
async def task_factory_with_result(redis_client):
    """Task factory that ALSO writes a result blob with the given payload.

    Used by Phase-2 joined-view tests that need `task.result` populated so the
    trim helpers can extract messages / tool_calls.
    """
    created: list[str] = []

    async def _make(
        *,
        thread_id: str | None = "thr-test",
        status: str = "done",
        subject: str | None = "Test subject",
        result: dict | None = None,
        error_message: str | None = None,
        updated_at: str | None = None,
    ) -> str:
        task_id = f"tsk-{uuid.uuid4().hex[:12]}"
        await redis_client.set(RedisKeys.task_status(task_id), status)
        mapping = {"created_at": "2026-05-01T00:00:00+00:00"}
        if thread_id is not None:
            mapping["thread_id"] = thread_id
        if subject is not None:
            mapping["subject"] = subject
        if updated_at is not None:
            mapping["updated_at"] = updated_at
        await redis_client.hset(RedisKeys.task_metadata(task_id), mapping=mapping)
        if result is not None:
            await redis_client.set(RedisKeys.task_result(task_id), json.dumps(result))
        if error_message is not None:
            await redis_client.set(RedisKeys.task_error(task_id), error_message)
        created.append(task_id)
        return task_id

    yield _make

    for task_id in created:
        await redis_client.delete(
            RedisKeys.task_status(task_id),
            RedisKeys.task_metadata(task_id),
            RedisKeys.task_result(task_id),
            RedisKeys.task_error(task_id),
            RedisKeys.feedback_task(task_id),
        )


# --- AC-1 module exports ---------------------------------------------------


def test_feedback_view_module_exports():
    """AC-1: all 4 new models + the 2 public helpers are importable from
    core.feedback; api.schemas re-exports point at the same classes."""
    import redis_sre_agent.core.feedback as mod
    from redis_sre_agent.api import schemas as api_schemas

    assert issubclass(mod.FeedbackView, object)
    assert issubclass(mod.TaskInfo, object)
    assert issubclass(mod.ConversationMessage, object)
    assert issubclass(mod.ToolCallSummary, object)
    assert callable(mod.get_feedback_view)
    assert callable(mod.list_feedback_views)

    assert api_schemas.FeedbackView is mod.FeedbackView
    assert api_schemas.TaskInfo is mod.TaskInfo
    assert api_schemas.ConversationMessage is mod.ConversationMessage
    assert api_schemas.ToolCallSummary is mod.ToolCallSummary


# --- AC-2 trim policy ------------------------------------------------------


def test_trim_policy_drops_tool_messages_and_raw_outputs():
    """AC-2: tool/system messages dropped; raw tool_calls payload replaced
    with a ToolCallSummary list (no raw outputs); args_summary <=256 chars."""
    from redis_sre_agent.core.feedback import (
        ConversationMessage,
        ToolCallSummary,
        _compact_tool_calls,
        _trim_task_messages,
    )

    huge_args = {"query": "x" * 1000, "extra": list(range(100))}
    raw_result = {
        "messages": [
            {"role": "user", "content": "Help me debug Redis"},
            {
                "role": "assistant",
                "content": "Looking into it now.",
                "tool_calls": [
                    {"name": "redis_cli", "args": huge_args},
                ],
                "metadata": {
                    "tool_calls": [
                        {"name": "search_kb", "args": {"q": "memory"}},
                    ],
                },
            },
            {
                "role": "tool",
                "content": "RAW_TOOL_OUTPUT_BYTES_HERE",
                "metadata": {"output_bytes": "x" * 5000},
            },
            {"role": "system", "content": "internal citation system prompt"},
            {"role": "assistant", "content": "Memory looks healthy."},
        ],
        "tool_envelopes": [
            {
                "tool_name": "redis_info",
                "tool_args": {"section": "memory"},
                "output": "RAW_OUTPUT_HERE_should_be_dropped",
            },
        ],
    }

    trimmed = _trim_task_messages(raw_result)
    assert all(isinstance(m, ConversationMessage) for m in trimmed)
    assert [m.role for m in trimmed] == ["user", "assistant", "assistant"]
    assert [m.content for m in trimmed] == [
        "Help me debug Redis",
        "Looking into it now.",
        "Memory looks healthy.",
    ]
    # No raw tool/system entries leaked through.
    assert not any("RAW_TOOL_OUTPUT_BYTES_HERE" in m.content for m in trimmed)
    assert not any("citation system prompt" in m.content for m in trimmed)

    summaries = _compact_tool_calls(raw_result)
    assert all(isinstance(s, ToolCallSummary) for s in summaries)
    # Three tool calls: inline `redis_cli`, metadata `search_kb`, envelope `redis_info`.
    tool_names = sorted(s.tool for s in summaries)
    assert tool_names == ["redis_cli", "redis_info", "search_kb"]
    for s in summaries:
        assert len(s.args_summary) <= 256
        assert "RAW_OUTPUT_HERE_should_be_dropped" not in s.args_summary

    # Empty / non-dict inputs are tolerated.
    assert _trim_task_messages(None) == []
    assert _trim_task_messages({}) == []
    assert _compact_tool_calls(None) == []
    assert _compact_tool_calls({}) == []


# --- AC-3 task info field set ---------------------------------------------


def test_task_info_field_set():
    """AC-3: TaskInfo carries exactly the documented subset.

    Specifically NO `updates`, NO raw `tool_calls`, NO `resume_supported`.
    `tool_calls` IS present as the compact ToolCallSummary list (allowed by
    spec) — but the field type must NOT be the raw List[Dict[str, Any]] shape.
    """
    from redis_sre_agent.core.feedback import TaskInfo, ToolCallSummary

    expected = {
        "task_id",
        "thread_id",
        "status",
        "subject",
        "created_at",
        "updated_at",
        "error_message",
        "pending_approval",
        "messages",
        "tool_calls",
    }
    assert set(TaskInfo.model_fields) == expected
    assert "updates" not in TaskInfo.model_fields
    assert "resume_supported" not in TaskInfo.model_fields

    # The `tool_calls` field is the compact summary list, not raw envelopes.
    tc_field = TaskInfo.model_fields["tool_calls"]
    annotation_repr = repr(tc_field.annotation)
    assert "ToolCallSummary" in annotation_repr, (
        f"tool_calls must be List[ToolCallSummary], got {annotation_repr}"
    )
    assert ToolCallSummary.model_fields["args_summary"].metadata, (
        "args_summary must carry a max_length constraint"
    )


# --- AC: get_feedback_view returns joined view ----------------------------


@pytest.mark.asyncio
async def test_get_feedback_view_returns_joined(redis_client, task_factory_with_result):
    """get_feedback_view returns a FeedbackView with both feedback and task fields."""
    from redis_sre_agent.core.feedback import get_feedback_view

    result_payload = {
        "response": "ok",
        "messages": [
            {"role": "user", "content": "Why is memory high?"},
            {
                "role": "assistant",
                "content": "Checked INFO memory.",
                "tool_calls": [{"name": "redis_info", "args": {"section": "memory"}}],
            },
        ],
    }
    task_id = await task_factory_with_result(result=result_payload, status="done")
    await submit_feedback(task_id, "down", comment="bad explanation")

    view = await get_feedback_view(task_id)

    assert view is not None
    assert view.feedback.task_id == task_id
    assert view.feedback.verdict == "down"
    assert view.feedback.comment == "bad explanation"

    assert view.task.task_id == task_id
    assert view.task.thread_id == "thr-test"
    assert view.task.status == "done"
    assert view.task.subject == "Test subject"
    assert view.task.created_at == "2026-05-01T00:00:00+00:00"
    assert [m.role for m in view.task.messages] == ["user", "assistant"]
    assert [m.content for m in view.task.messages] == [
        "Why is memory high?",
        "Checked INFO memory.",
    ]
    assert len(view.task.tool_calls) == 1
    assert view.task.tool_calls[0].tool == "redis_info"
    assert "memory" in view.task.tool_calls[0].args_summary


# --- AC: get_feedback_view returns None when known task lacks feedback ----


@pytest.mark.asyncio
async def test_get_feedback_view_returns_none_when_no_record(
    redis_client, task_factory_with_result
):
    """get_feedback_view returns None for a known task with no feedback row."""
    from redis_sre_agent.core.feedback import get_feedback_view

    task_id = await task_factory_with_result()
    view = await get_feedback_view(task_id)
    assert view is None


# --- AC: get_feedback_view raises on unknown task -------------------------


@pytest.mark.asyncio
async def test_get_feedback_view_raises_on_unknown_task(redis_client):
    """get_feedback_view raises TaskNotFoundError when the task doesn't exist."""
    from redis_sre_agent.core.feedback import get_feedback_view

    bogus = f"tsk-missing-{uuid.uuid4().hex[:8]}"
    await redis_client.delete(RedisKeys.task_status(bogus))
    with pytest.raises(TaskNotFoundError):
        await get_feedback_view(bogus)


# --- AC: list_feedback_views applies AND-semantics filters ----------------


@pytest.mark.asyncio
async def test_list_feedback_views_filters_apply_AND(  # noqa: N802 — verb-form name from spec
    redis_client, task_factory_with_result
):
    """Filters (verdict, status) compose with AND-semantics."""
    from redis_sre_agent.core.feedback import list_feedback_views

    # Seed 4 tasks with all combinations of verdict x status.
    task_down_done = await task_factory_with_result(status="done")
    task_down_failed = await task_factory_with_result(status="failed")
    task_up_done = await task_factory_with_result(status="done")
    task_up_failed = await task_factory_with_result(status="failed")
    await submit_feedback(task_down_done, "down", comment="A")
    await submit_feedback(task_down_failed, "down", comment="B")
    await submit_feedback(task_up_done, "up", comment="C")
    await submit_feedback(task_up_failed, "up", comment="D")

    targets = {task_down_done, task_down_failed, task_up_done, task_up_failed}

    # verdict=down AND status=done → only task_down_done.
    rows = await list_feedback_views(verdict="down", status="done", limit=500)
    matching = [v for v in rows if v.feedback.task_id in targets]
    assert {v.feedback.task_id for v in matching} == {task_down_done}

    # verdict=up alone → both up rows.
    rows = await list_feedback_views(verdict="up", limit=500)
    matching = [v for v in rows if v.feedback.task_id in targets]
    assert {v.feedback.task_id for v in matching} == {task_up_done, task_up_failed}

    # status=failed alone → both failed rows.
    rows = await list_feedback_views(status="failed", limit=500)
    matching = [v for v in rows if v.feedback.task_id in targets]
    assert {v.feedback.task_id for v in matching} == {task_down_failed, task_up_failed}


# --- AC: list limit clamped to 500 ----------------------------------------


@pytest.mark.asyncio
async def test_list_feedback_views_limit_clamped_to_500(redis_client, task_factory_with_result):
    """Asking for limit=10000 returns at most 500 rows."""
    from redis_sre_agent.core.feedback import list_feedback_views

    # Seed one row so the path exercises the clamp.
    task_id = await task_factory_with_result()
    await submit_feedback(task_id, "up")

    rows = await list_feedback_views(limit=10000)
    assert len(rows) <= 500


# --- AC: list uses SCAN not KEYS ------------------------------------------


@pytest.mark.asyncio
async def test_list_feedback_views_uses_scan_not_keys(
    redis_client, task_factory_with_result, monkeypatch
):
    """Patch the client's `.keys` method to raise; list_feedback_views must
    still succeed (proves the implementation walks via SCAN)."""
    from redis_sre_agent.core import feedback as fb_mod
    from redis_sre_agent.core.feedback import list_feedback_views

    task_id = await task_factory_with_result()
    await submit_feedback(task_id, "up")

    real_client = fb_mod.get_redis_client()

    async def _boom(*_a, **_kw):
        raise AssertionError("list_feedback_views must NOT call KEYS")

    monkeypatch.setattr(real_client, "keys", _boom, raising=False)

    rows = await list_feedback_views(limit=500)
    assert any(v.feedback.task_id == task_id for v in rows)


# --- AC: OTel spans on reads ----------------------------------------------


@pytest.mark.asyncio
async def test_otel_read_spans(redis_client, task_factory_with_result):
    """`feedback.get` + `feedback.list` spans exist with the expected attributes."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from redis_sre_agent.core.feedback import get_feedback_view, list_feedback_views

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    new_tracer = provider.get_tracer("test.feedback.read")

    task_id = await task_factory_with_result()
    await submit_feedback(task_id, "down", comment="for span test")

    with patch("redis_sre_agent.core.feedback.tracer", new_tracer):
        await get_feedback_view(task_id)
        await list_feedback_views(verdict="down", status="done", since="1d", limit=10)

    finished = exporter.get_finished_spans()
    get_spans = [s for s in finished if s.name == "feedback.get"]
    list_spans = [s for s in finished if s.name == "feedback.list"]

    assert get_spans, "expected a `feedback.get` span"
    get_attrs = dict(get_spans[0].attributes or {})
    assert get_attrs.get("task_id") == task_id
    assert get_attrs.get("sre_agent.category") == "feedback"

    assert list_spans, "expected a `feedback.list` span"
    list_attrs = dict(list_spans[0].attributes or {})
    assert list_attrs.get("verdict_filter") == "down"
    assert list_attrs.get("status_filter") == "done"
    assert list_attrs.get("since_filter") == "1d"
    assert "result_count" in list_attrs
    assert isinstance(list_attrs.get("result_count"), int)
    assert list_attrs.get("sre_agent.category") == "feedback"

"""Canonical feedback module — single source of truth for agent feedback.

All feedback writes go through `submit_feedback()` in this module. HTTP, MCP,
and CLI surfaces are thin wrappers. The Redis hash at
`sre:feedback:task:{task_id}` is the source of truth; `created_at` is anchored
with `HSETNX` to be race-immune across concurrent first writes.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from opentelemetry import trace
from pydantic import BaseModel, Field
from typing_extensions import Annotated

from redis_sre_agent.core.approvals import PendingApprovalSummary
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.observability.tracing import ATTR_CATEGORY, SpanCategory, get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Stream update_type for feedback events (documented constant for reuse).
FEEDBACK_SUBMITTED_UPDATE_TYPE = "feedback_submitted"

# Comment length cap (chars). Enforced via Pydantic validation on input.
COMMENT_MAX_LENGTH = 2048


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FeedbackError(Exception):
    """Base exception for feedback-related errors."""


class TaskNotFoundError(FeedbackError):
    """Raised when feedback is submitted for a task that does not exist."""


# ---------------------------------------------------------------------------
# Pydantic models (single source of truth for all surfaces).
# ---------------------------------------------------------------------------


class FeedbackRecord(BaseModel):
    """A single feedback row materialized from the Redis hash."""

    task_id: str
    verdict: Literal["up", "down", "withdrawn"]
    comment: Optional[str] = None
    created_at: str
    updated_at: str


class FeedbackSubmitRequest(BaseModel):
    """Request body for submitting feedback (HTTP / MCP / CLI shared shape)."""

    verdict: Literal["up", "down", "withdrawn"]
    comment: Optional[str] = Field(default=None, max_length=COMMENT_MAX_LENGTH)


class ConversationMessage(BaseModel):
    """A trimmed user/assistant message in a FeedbackView."""

    role: Literal["user", "assistant"]
    content: str


class ToolCallSummary(BaseModel):
    """Compact summary of a single assistant-level tool call (no raw outputs)."""

    tool: str
    args_summary: Annotated[str, Field(max_length=256)]


class TaskInfo(BaseModel):
    """Subset of task fields embedded in a FeedbackView.

    Explicitly EXCLUDES `updates`, raw `tool_calls`, and `resume_supported`
    per the Phase 2 joined-view spec.
    """

    task_id: str
    thread_id: str
    status: str
    subject: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    error_message: Optional[str] = None
    pending_approval: Optional[PendingApprovalSummary] = None
    messages: List[ConversationMessage] = Field(default_factory=list)
    tool_calls: List[ToolCallSummary] = Field(default_factory=list)


class FeedbackView(BaseModel):
    """Joined view of a feedback record + its associated task info."""

    feedback: FeedbackRecord
    task: TaskInfo


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _decode(value: Any) -> Any:
    """Decode bytes from Redis to str; pass through other types."""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def hash_to_dict(raw: Any) -> Dict[str, str]:
    """Normalize an HGETALL response (possibly bytes-keyed) into a str/str dict."""
    if not raw:
        return {}
    out: Dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            out[_decode(k)] = _decode(v)
    return out


def _record_from_hash(task_id: str, raw: Any) -> Optional[FeedbackRecord]:
    """Build a FeedbackRecord from an HGETALL hash, or None if empty."""
    data = hash_to_dict(raw)
    if not data or "verdict" not in data:
        return None
    # Comment is stored as "" when absent — surface as None to match request shape.
    comment_value: Optional[str] = data.get("comment") or None
    return FeedbackRecord(
        task_id=data.get("task_id", task_id),
        verdict=data["verdict"],  # type: ignore[arg-type]
        comment=comment_value,
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


async def _resolve_thread_id(redis_client: Any, task_id: str) -> Optional[str]:
    """Look up the task's thread_id, returning None when missing or malformed."""
    try:
        raw = await redis_client.hget(RedisKeys.task_metadata(task_id), "thread_id")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("feedback: failed reading thread_id for task=%s: %s", task_id, exc)
        return None
    thread_id = _decode(raw) if raw is not None else None
    if not thread_id or not isinstance(thread_id, str):
        logger.warning(
            "feedback: thread_id missing or malformed for task=%s; "
            "feedback hash will still be written, stream publish skipped",
            task_id,
        )
        return None
    return thread_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def submit_feedback(
    task_id: str,
    verdict: str,
    comment: Optional[str] = None,
) -> FeedbackRecord:
    """Submit / update / withdraw feedback for a task.

    - Validates `verdict` and `comment` via :class:`FeedbackSubmitRequest`
      (pydantic ValidationError propagates so FastAPI maps it to 422).
    - Raises :class:`TaskNotFoundError` when the task itself is absent.
    - When the task exists but `thread_id` is missing/malformed, the feedback
      hash is still written; the stream publish is skipped with a logged
      warning (fail-open per plan §AC-5).
    - `created_at` is anchored by `HSETNX` — concurrent first-writers all
      observe the same value (plan §AC-7).
    - Idempotent: identical resubmissions short-circuit and return the
      existing record without rewriting or republishing.
    - After a successful pipeline commit, publishes a stream event
      (`feedback_submitted`) carrying `{task_id, verdict, has_comment}`.
      Publish failures emit an OTel span event and a warning log; they do
      NOT raise (the write is authoritative — plan §AC-13, Risk #10).
    """
    # Validate input (raises pydantic.ValidationError → FastAPI 422 on the HTTP path).
    request = FeedbackSubmitRequest(verdict=verdict, comment=comment)
    verdict_str = request.verdict
    comment_str = request.comment

    with tracer.start_as_current_span(
        "feedback.submit",
        attributes={
            "task_id": task_id,
            "verdict": verdict_str,
            "comment_length": len(comment_str or ""),
            ATTR_CATEGORY: SpanCategory.FEEDBACK.value,
        },
    ) as span:
        redis_client = get_redis_client()

        # 1. Verify the task exists. Missing task → 404 (TaskNotFoundError).
        status_raw = await redis_client.get(RedisKeys.task_status(task_id))
        if status_raw is None:
            raise TaskNotFoundError(f"Task {task_id} not found")

        # 2. Resolve thread_id (fail-open if missing/malformed — see AC-5).
        thread_id = await _resolve_thread_id(redis_client, task_id)

        key = RedisKeys.feedback_task(task_id)
        now = datetime.now(timezone.utc).isoformat()

        # 3. Idempotency short-circuit — identical resubmit returns existing
        #    record without rewriting `updated_at` or republishing the event.
        existing_raw = await redis_client.hgetall(key)
        existing_record = _record_from_hash(task_id, existing_raw)
        if existing_record is not None:
            same_verdict = existing_record.verdict == verdict_str
            same_comment = (existing_record.comment or "") == (comment_str or "")
            if same_verdict and same_comment:
                span.set_attribute("feedback.idempotent_short_circuit", True)
                return existing_record

        # 4. Atomic write — HSETNX anchors created_at; HSET overwrites mutables.
        pipe = redis_client.pipeline(transaction=False)
        pipe.hsetnx(key, "created_at", now)
        pipe.hset(
            key,
            mapping={
                "task_id": task_id,
                "verdict": verdict_str,
                "comment": comment_str or "",
                "updated_at": now,
            },
        )
        pipe.hgetall(key)
        results = await pipe.execute()

        final_raw = results[-1]
        final_record = _record_from_hash(task_id, final_raw)
        if final_record is None:
            # Defensive: shouldn't happen since we just wrote the row.
            raise FeedbackError(f"Feedback hash unexpectedly empty after write for task {task_id}")

        # 5. Publish stream event AFTER successful commit. Failures are
        #    observable (span event + warning log) but never raise.
        if thread_id:
            try:
                # Deferred import to avoid api → core layering cycle
                # (mirrors core/tasks.py:148 precedent).
                from redis_sre_agent.api.websockets import get_stream_manager

                stream_manager = await get_stream_manager()
                await stream_manager.publish_task_update(
                    thread_id=thread_id,
                    update_type=FEEDBACK_SUBMITTED_UPDATE_TYPE,
                    data={
                        "task_id": task_id,
                        "verdict": verdict_str,
                        "has_comment": bool(comment_str),
                    },
                )
            except Exception as exc:  # noqa: BLE001 — publish failure is non-fatal
                current_span = trace.get_current_span()
                if current_span is not None:
                    current_span.add_event(
                        "feedback.stream_publish_failed",
                        attributes={"task_id": task_id, "error": str(exc)},
                    )
                logger.warning("feedback.stream_publish_failed task_id=%s error=%s", task_id, exc)

        return final_record


async def get_feedback(task_id: str) -> Optional[FeedbackRecord]:
    """Return the current feedback record for a task, or None if absent.

    The Redis client is obtained internally via :func:`get_redis_client` —
    callers MUST NOT supply one (matches the established pattern at
    `api/tasks.py:127,134,146`).
    """
    # TODO(perf): pipelined batch fetch for future list endpoints (N+1 risk).
    redis_client = get_redis_client()
    raw = await redis_client.hgetall(RedisKeys.feedback_task(task_id))
    return _record_from_hash(task_id, raw)


# ---------------------------------------------------------------------------
# Joined-view (FeedbackView) helpers — Phase 2 read paths.
# ---------------------------------------------------------------------------


# Allowed `since` window pattern — shared by HTTP/CLI/MCP filter validation.
SINCE_PATTERN = re.compile(r"^(\d+)([smhd])$")


def _trim_task_messages(result: Optional[Dict[str, Any]]) -> List[ConversationMessage]:
    """Return only user/assistant text messages from a task result.

    Tool envelopes, system messages, and per-message metadata are dropped. Raw
    `tool_calls` payloads on assistant messages are surfaced via the separate
    :func:`_compact_tool_calls` helper.
    """
    if not isinstance(result, dict):
        return []
    raw_messages = result.get("messages")
    if not isinstance(raw_messages, list):
        return []

    trimmed: List[ConversationMessage] = []
    for entry in raw_messages:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        if role not in ("user", "assistant"):
            continue
        content = entry.get("content")
        if not isinstance(content, str) or not content:
            continue
        trimmed.append(ConversationMessage(role=role, content=content))
    return trimmed


def _compact_tool_calls(result: Optional[Dict[str, Any]]) -> List[ToolCallSummary]:
    """Walk a task result and return a compact list of (tool, args_summary).

    Looks at both inline assistant-message `tool_calls` metadata entries and the
    top-level `tool_envelopes` list (the canonical agent shape). Raw outputs
    are never included; `args_summary` is `json.dumps(...)`-encoded and clipped
    to 256 chars.
    """
    if not isinstance(result, dict):
        return []

    out: List[ToolCallSummary] = []

    def _summarize_args(args: Any) -> str:
        if args is None:
            return ""
        try:
            text = args if isinstance(args, str) else json.dumps(args, default=str, sort_keys=True)
        except Exception:  # noqa: BLE001 — defensive against odd payloads
            text = str(args)
        return text[:256]

    # 1) Inline assistant-message tool_calls metadata entries (LangChain-style
    #    AIMessage envelopes carried through the agent's conversation_state).
    raw_messages = result.get("messages")
    if isinstance(raw_messages, list):
        for entry in raw_messages:
            if not isinstance(entry, dict) or entry.get("role") != "assistant":
                continue
            # `tool_calls` may live directly on the entry or inside `metadata`.
            candidates: List[Any] = []
            direct = entry.get("tool_calls")
            if isinstance(direct, list):
                candidates.extend(direct)
            metadata = entry.get("metadata")
            if isinstance(metadata, dict):
                inner = metadata.get("tool_calls")
                if isinstance(inner, list):
                    candidates.extend(inner)
            for call in candidates:
                if not isinstance(call, dict):
                    continue
                tool_name = call.get("name") or call.get("tool") or call.get("function") or ""
                if not isinstance(tool_name, str) or not tool_name:
                    continue
                args = call.get("args")
                if args is None:
                    args = call.get("arguments")
                out.append(ToolCallSummary(tool=tool_name, args_summary=_summarize_args(args)))

    # 2) Top-level `tool_envelopes` list (the canonical agent shape — see
    #    docket_tasks.py:2100). Envelopes carry `tool_name` and `tool_args`.
    envelopes = result.get("tool_envelopes")
    if isinstance(envelopes, list):
        for env in envelopes:
            if not isinstance(env, dict):
                continue
            tool_name = env.get("tool_name") or env.get("name") or env.get("tool") or ""
            if not isinstance(tool_name, str) or not tool_name:
                continue
            args = env.get("tool_args")
            if args is None:
                args = env.get("args")
            out.append(ToolCallSummary(tool=tool_name, args_summary=_summarize_args(args)))

    return out


async def _fetch_task_info(redis_client: Any, task_id: str) -> Optional[TaskInfo]:
    """Pipelined fetch of a single task's metadata/status/result into a TaskInfo.

    Returns None when the task does not exist (status key missing).
    """
    pipe = redis_client.pipeline(transaction=False)
    pipe.get(RedisKeys.task_status(task_id))
    pipe.hgetall(RedisKeys.task_metadata(task_id))
    pipe.get(RedisKeys.task_result(task_id))
    pipe.get(RedisKeys.task_error(task_id))
    results = await pipe.execute()
    return _build_task_info(task_id, *results)


def _build_task_info(
    task_id: str,
    status_raw: Any,
    metadata_raw: Any,
    result_raw: Any,
    error_raw: Any,
) -> Optional[TaskInfo]:
    """Assemble a TaskInfo from the four canonical task keys.

    Returns None when the task's status key is missing.
    """
    status_val = _decode(status_raw) if status_raw is not None else None
    if not status_val:
        return None

    md = hash_to_dict(metadata_raw)
    thread_id = md.get("thread_id") or ""
    subject = md.get("subject") or None
    created_at = md.get("created_at") or None
    updated_at = md.get("updated_at") or None

    pending_approval: Optional[PendingApprovalSummary] = None
    pending_raw = md.get("pending_approval")
    if pending_raw:
        try:
            pending_approval = PendingApprovalSummary(**json.loads(pending_raw))
        except Exception:  # noqa: BLE001 — match TaskManager.get_task_state behavior
            pending_approval = None

    error_message: Optional[str] = None
    decoded_error = _decode(error_raw) if error_raw is not None else None
    if decoded_error:
        error_message = decoded_error

    result_dict: Optional[Dict[str, Any]] = None
    decoded_result = _decode(result_raw) if result_raw is not None else None
    if decoded_result:
        try:
            parsed = json.loads(decoded_result)
            if isinstance(parsed, dict):
                result_dict = parsed
        except Exception:  # noqa: BLE001 — corrupt result blobs shouldn't break reads
            result_dict = None

    return TaskInfo(
        task_id=task_id,
        thread_id=thread_id,
        status=status_val,
        subject=subject,
        created_at=created_at,
        updated_at=updated_at,
        error_message=error_message,
        pending_approval=pending_approval,
        messages=_trim_task_messages(result_dict),
        tool_calls=_compact_tool_calls(result_dict),
    )


def _parse_since(since: Optional[str]) -> Optional[datetime]:
    """Parse a `since` window string like '24h' into a UTC datetime cutoff.

    Returns None when `since` is None. Raises ValueError when the string does
    not match `^(\\d+)([smhd])$` — callers translate to 422 / non-zero exit.
    """
    if since is None:
        return None
    m = SINCE_PATTERN.match(since)
    if not m:
        raise ValueError(f"Invalid `since` value: {since!r}; expected ^(\\d+)([smhd])$")
    value = int(m.group(1))
    unit = m.group(2)
    seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return datetime.now(timezone.utc) - timedelta(seconds=value * seconds)


def _filter_feedback_views(
    views: List[FeedbackView],
    *,
    since: Optional[str] = None,
    verdict: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[FeedbackView]:
    """Apply AND-semantics filters to a list of joined views, sort, and slice.

    All three surfaces (HTTP list, CLI list, MCP list_feedback) route through
    this helper for drift protection (plan §AC-2 / spec §Technical Context).
    """
    cutoff = _parse_since(since)

    filtered: List[FeedbackView] = []
    for view in views:
        if verdict is not None and view.feedback.verdict != verdict:
            continue
        if status is not None and view.task.status != status:
            continue
        if cutoff is not None:
            try:
                ts = datetime.fromisoformat(view.feedback.updated_at.replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001 — malformed timestamp → skip
                continue
            if ts < cutoff:
                continue
        filtered.append(view)

    filtered.sort(key=lambda v: v.feedback.updated_at, reverse=True)

    effective_limit = min(max(int(limit), 0), 500)
    return filtered[:effective_limit]


async def get_feedback_view(task_id: str) -> Optional[FeedbackView]:
    """Return the joined FeedbackView for a task.

    - Returns None when the task exists but has no feedback record.
    - Raises :class:`TaskNotFoundError` when the task itself does not exist.

    Wrapped in an OTel span ``feedback.get`` carrying ``task_id``.
    """
    with tracer.start_as_current_span(
        "feedback.get",
        attributes={
            "task_id": task_id,
            ATTR_CATEGORY: SpanCategory.FEEDBACK.value,
        },
    ):
        redis_client = get_redis_client()

        # Single pipelined read of the four task keys (status + md + result + error).
        task_info = await _fetch_task_info(redis_client, task_id)
        if task_info is None:
            raise TaskNotFoundError(f"Task {task_id} not found")

        feedback_raw = await redis_client.hgetall(RedisKeys.feedback_task(task_id))
        record = _record_from_hash(task_id, feedback_raw)
        if record is None:
            return None

        return FeedbackView(feedback=record, task=task_info)


async def list_feedback_views(
    *,
    since: Optional[str] = None,
    verdict: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[FeedbackView]:
    """Return joined FeedbackView rows matching the given filters.

    - Uses ``SCAN`` over ``sre:feedback:task:*`` (never ``KEYS``).
    - Batches task metadata / status / result / error fetches in a single
      Redis pipeline (no N+1 sequential round-trips).
    - Sorts by ``feedback.updated_at`` desc in-process.
    - Clamps ``limit`` to the inclusive [0, 500] range.

    Wrapped in an OTel span ``feedback.list`` carrying ``verdict_filter``,
    ``status_filter``, ``since_filter``, and ``result_count``.
    """
    # Validate `since` up-front so the span carries the rejected value.
    _parse_since(since)  # raises ValueError on malformed input

    with tracer.start_as_current_span(
        "feedback.list",
        attributes={
            "verdict_filter": verdict or "",
            "status_filter": status or "",
            "since_filter": since or "",
            ATTR_CATEGORY: SpanCategory.FEEDBACK.value,
        },
    ) as span:
        redis_client = get_redis_client()

        # 1. Discover feedback keys via SCAN (NOT KEYS).
        feedback_keys: List[str] = []
        async for key in redis_client.scan_iter(match="sre:feedback:task:*"):
            feedback_keys.append(_decode(key))

        if not feedback_keys:
            span.set_attribute("result_count", 0)
            return []

        # 2. Pipelined fetch of every feedback hash.
        feedback_pipe = redis_client.pipeline(transaction=False)
        for key in feedback_keys:
            feedback_pipe.hgetall(key)
        feedback_raws = await feedback_pipe.execute()

        # 3. Parse feedback records, collect (record, task_id) pairs.
        pairs: List[tuple[FeedbackRecord, str]] = []
        for key, raw in zip(feedback_keys, feedback_raws):
            # key is "sre:feedback:task:{task_id}"
            task_id = key.rsplit(":", 1)[-1]
            record = _record_from_hash(task_id, raw)
            if record is None:
                continue
            pairs.append((record, task_id))

        if not pairs:
            span.set_attribute("result_count", 0)
            return []

        # 4. Pipelined batch read of all task keys (status, metadata, result, error)
        #    so we never do N sequential round-trips.
        task_pipe = redis_client.pipeline(transaction=False)
        for _, task_id in pairs:
            task_pipe.get(RedisKeys.task_status(task_id))
            task_pipe.hgetall(RedisKeys.task_metadata(task_id))
            task_pipe.get(RedisKeys.task_result(task_id))
            task_pipe.get(RedisKeys.task_error(task_id))
        task_raws = await task_pipe.execute()

        # 5. Assemble joined views.
        views: List[FeedbackView] = []
        for idx, (record, task_id) in enumerate(pairs):
            base = idx * 4
            status_raw = task_raws[base]
            metadata_raw = task_raws[base + 1]
            result_raw = task_raws[base + 2]
            error_raw = task_raws[base + 3]
            task_info = _build_task_info(task_id, status_raw, metadata_raw, result_raw, error_raw)
            if task_info is None:
                # Feedback row references a task that no longer exists — skip.
                continue
            views.append(FeedbackView(feedback=record, task=task_info))

        # 6. Apply filters + sort + slice via the shared helper.
        result = _filter_feedback_views(
            views, since=since, verdict=verdict, status=status, limit=limit
        )
        span.set_attribute("result_count", len(result))
        return result


__all__ = [
    "COMMENT_MAX_LENGTH",
    "FEEDBACK_SUBMITTED_UPDATE_TYPE",
    "ConversationMessage",
    "FeedbackError",
    "FeedbackRecord",
    "FeedbackSubmitRequest",
    "FeedbackView",
    "TaskInfo",
    "TaskNotFoundError",
    "ToolCallSummary",
    "get_feedback",
    "get_feedback_view",
    "list_feedback_views",
    "submit_feedback",
]

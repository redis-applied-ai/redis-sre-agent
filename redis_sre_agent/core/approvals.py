"""Approval domain models and storage helpers."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from ulid import ULID

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode(value: Any) -> Any:
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _iso_to_ts(value: Optional[str]) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


class ApprovalStatus(str, Enum):
    """Lifecycle state for a single approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class ApprovalDecisionType(str, Enum):
    """Decision values accepted during approval consumption."""

    APPROVED = "approved"
    REJECTED = "rejected"


class ActionExecutionStatus(str, Enum):
    """Execution state for the idempotency ledger."""

    PENDING = "pending"
    EXECUTED = "executed"
    SKIPPED = "skipped"
    FAILED = "failed"


class ToolExecutionMode(str, Enum):
    """Approval-gate outcome for a pending tool call."""

    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_APPROVAL = "require_approval"


class ApprovalDecision(BaseModel):
    """Recorded human decision for an approval request."""

    decision: ApprovalDecisionType
    decision_by: Optional[str] = None
    decision_comment: Optional[str] = None
    decision_at: str = Field(default_factory=_now_iso)


class ApprovalRecord(BaseModel):
    """Persisted approval request linked to one graph interrupt."""

    approval_id: str = Field(default_factory=lambda: str(ULID()))
    task_id: str
    thread_id: str
    graph_thread_id: str
    interrupt_id: str
    graph_type: str
    graph_version: str
    tool_name: str
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    tool_args_preview: Dict[str, Any] = Field(default_factory=dict)
    action_kind: str = "write"
    action_hash: str
    target_handles: List[str] = Field(default_factory=list)
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: str = Field(default_factory=_now_iso)
    expires_at: Optional[str] = None
    decision: Optional[ApprovalDecision] = None


class PendingApprovalSummary(BaseModel):
    """UI-friendly view of the active approval on a task."""

    approval_id: str
    interrupt_id: str
    tool_name: str
    summary: str
    requested_at: str
    expires_at: Optional[str] = None
    status: ApprovalStatus = ApprovalStatus.PENDING

    @classmethod
    def from_record(cls, record: ApprovalRecord) -> "PendingApprovalSummary":
        summary = record.tool_name
        if record.target_handles:
            summary = f"{record.tool_name} on {', '.join(record.target_handles)}"
        return cls(
            approval_id=record.approval_id,
            interrupt_id=record.interrupt_id,
            tool_name=record.tool_name,
            summary=summary,
            requested_at=record.requested_at,
            expires_at=record.expires_at,
            status=record.status,
        )


class GraphResumeState(BaseModel):
    """Persisted state needed to resume a paused graph."""

    task_id: str
    thread_id: str
    graph_thread_id: str
    graph_type: str
    graph_version: str
    checkpoint_ns: str
    checkpoint_id: str
    waiting_reason: str
    pending_approval_id: Optional[str] = None
    pending_interrupt_id: Optional[str] = None
    resume_count: int = 0
    updated_at: str = Field(default_factory=_now_iso)


class ActionExecutionLedger(BaseModel):
    """Durable idempotency record for one approved action execution."""

    approval_id: str
    task_id: str
    tool_name: str
    action_hash: str
    status: ActionExecutionStatus = ActionExecutionStatus.PENDING
    executed_at: Optional[str] = None
    result_summary: Optional[str] = None
    error: Optional[str] = None

    @property
    def ledger_key(self) -> str:
        return f"{self.approval_id}:{self.action_hash}"


class ToolExecutionDecision(BaseModel):
    """Decision returned by the approval gate for one tool call."""

    mode: ToolExecutionMode
    tool_name: str
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None
    result_payload: Optional[Dict[str, Any]] = None
    approval_record: Optional[ApprovalRecord] = None
    pending_approval: Optional[PendingApprovalSummary] = None


class ApprovalRequiredError(RuntimeError):
    """Raised when the runtime must stop and await human approval."""

    def __init__(
        self,
        *,
        decision: ToolExecutionDecision,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.decision = decision
        self.approval_record = decision.approval_record
        self.pending_approval = decision.pending_approval
        self.payload = payload
        message = decision.message or "Approval required before executing tool call."
        super().__init__(message)


APPROVAL_INTERRUPT_KIND = "approval_required"


def build_approval_interrupt_payload(
    *,
    decision: ToolExecutionDecision,
) -> Dict[str, Any]:
    """Build the LangGraph interrupt payload for a gated write tool call."""

    if decision.approval_record is None or decision.pending_approval is None:
        raise ValueError("Approval interrupt payload requires approval metadata")

    return {
        "kind": APPROVAL_INTERRUPT_KIND,
        "message": decision.message,
        "approval_id": decision.approval_record.approval_id,
        "interrupt_id": decision.approval_record.interrupt_id,
        "task_id": decision.approval_record.task_id,
        "thread_id": decision.approval_record.thread_id,
        "tool_name": decision.tool_name,
        "summary": decision.pending_approval.summary,
        "target_handles": list(decision.approval_record.target_handles),
        "requested_at": decision.approval_record.requested_at,
        "expires_at": decision.approval_record.expires_at,
        "tool_args_preview": dict(decision.approval_record.tool_args_preview),
        "approval_record": decision.approval_record.model_dump(mode="json"),
        "pending_approval": decision.pending_approval.model_dump(mode="json"),
    }


def extract_approval_required_error(graph_result: Any) -> Optional[ApprovalRequiredError]:
    """Translate a LangGraph interrupt result into ApprovalRequiredError."""

    if not isinstance(graph_result, dict):
        return None

    interrupts = graph_result.get("__interrupt__")
    if not isinstance(interrupts, list):
        return None

    for interrupt_value in interrupts:
        payload = getattr(interrupt_value, "value", interrupt_value)
        if not isinstance(payload, dict):
            continue
        if payload.get("kind") != APPROVAL_INTERRUPT_KIND:
            continue

        approval_record_raw = payload.get("approval_record")
        pending_approval_raw = payload.get("pending_approval")
        approval_record = (
            ApprovalRecord(**approval_record_raw) if isinstance(approval_record_raw, dict) else None
        )
        pending_approval = (
            PendingApprovalSummary(**pending_approval_raw)
            if isinstance(pending_approval_raw, dict)
            else (
                PendingApprovalSummary.from_record(approval_record)
                if approval_record is not None
                else None
            )
        )
        decision = ToolExecutionDecision(
            mode=ToolExecutionMode.REQUIRE_APPROVAL,
            tool_name=str(payload.get("tool_name") or ""),
            message=str(payload.get("message") or "Approval required before executing tool call."),
            approval_record=approval_record,
            pending_approval=pending_approval,
        )
        return ApprovalRequiredError(decision=decision)

    return None


def build_action_hash(
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    target_handles: List[str],
) -> str:
    """Build a stable action hash for an approval-scoped tool call."""

    payload = {
        "tool_name": tool_name,
        "tool_args": tool_args or {},
        "target_handles": target_handles or [],
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_tool_args_preview(
    tool_args: Dict[str, Any],
    *,
    max_value_chars: int = 120,
    max_items: int = 20,
) -> Dict[str, Any]:
    """Return a small preview of tool args suitable for approval displays."""

    preview: Dict[str, Any] = {}
    for index, (key, value) in enumerate((tool_args or {}).items()):
        if index >= max_items:
            preview["__truncated__"] = f"{len(tool_args) - max_items} additional keys omitted"
            break
        if isinstance(value, (str, int, float, bool)) or value is None:
            rendered = value
        else:
            rendered = json.dumps(value, default=str)
        if isinstance(rendered, str) and len(rendered) > max_value_chars:
            rendered = f"{rendered[:max_value_chars].rstrip()}..."
        preview[key] = rendered
    return preview


def build_blocked_tool_result(
    *,
    tool_name: str,
    reason: str,
    detail: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a synthetic tool result when execution is blocked by policy."""

    result = {
        "status": "blocked",
        "tool_name": tool_name,
        "reason": reason,
    }
    if detail:
        result["detail"] = detail
    return result


def build_approval_required_tool_result(
    *,
    approval_record: ApprovalRecord,
    pending_approval: PendingApprovalSummary,
) -> Dict[str, Any]:
    """Return a synthetic tool result when execution pauses for approval."""

    return {
        "status": "approval_required",
        "tool_name": approval_record.tool_name,
        "approval_id": approval_record.approval_id,
        "interrupt_id": approval_record.interrupt_id,
        "action_kind": approval_record.action_kind,
        "action_hash": approval_record.action_hash,
        "requested_at": approval_record.requested_at,
        "expires_at": approval_record.expires_at,
        "tool_args_preview": dict(approval_record.tool_args_preview),
        "target_handles": list(approval_record.target_handles),
        "pending_approval": pending_approval.model_dump(mode="json"),
    }


def approval_expiry_iso(ttl_seconds: int) -> str:
    """Return an ISO timestamp for approval expiry."""

    return (datetime.now(timezone.utc) + timedelta(seconds=max(ttl_seconds, 1))).isoformat()


class ApprovalManager:
    """Manages approval records, resume state, and execution ledgers in Redis."""

    def __init__(self, redis_client=None):
        self._redis = redis_client or get_redis_client()

    async def create_approval(self, record: ApprovalRecord) -> ApprovalRecord:
        payload = record.model_dump(mode="json")
        await self._redis.set(RedisKeys.approval(record.approval_id), json.dumps(payload))
        await self._redis.zadd(
            RedisKeys.task_approvals(record.task_id),
            {record.approval_id: _iso_to_ts(record.requested_at)},
        )
        if record.status == ApprovalStatus.PENDING:
            await self._redis.zadd(
                RedisKeys.approvals_pending(),
                {record.approval_id: _iso_to_ts(record.requested_at)},
            )
        return record

    async def get_approval(self, approval_id: str) -> Optional[ApprovalRecord]:
        raw = await self._redis.get(RedisKeys.approval(approval_id))
        if not raw:
            return None
        raw = _decode(raw)
        try:
            return ApprovalRecord(**json.loads(raw))
        except Exception as exc:
            logger.error("Failed to decode approval %s: %s", approval_id, exc)
            return None

    async def list_task_approvals(
        self,
        task_id: str,
        *,
        newest_first: bool = True,
        limit: Optional[int] = None,
    ) -> List[ApprovalRecord]:
        end = -1 if limit is None else max(limit - 1, 0)
        if newest_first:
            approval_ids = await self._redis.zrevrange(RedisKeys.task_approvals(task_id), 0, end)
        else:
            approval_ids = await self._redis.zrange(RedisKeys.task_approvals(task_id), 0, end)

        approvals: List[ApprovalRecord] = []
        for approval_id in approval_ids:
            record = await self.get_approval(_decode(approval_id))
            if record:
                approvals.append(record)
        return approvals

    async def list_pending_approvals(self, *, limit: Optional[int] = None) -> List[ApprovalRecord]:
        end = -1 if limit is None else max(limit - 1, 0)
        approval_ids = await self._redis.zrange(RedisKeys.approvals_pending(), 0, end)
        approvals: List[ApprovalRecord] = []
        for approval_id in approval_ids:
            record = await self.get_approval(_decode(approval_id))
            if record and record.status == ApprovalStatus.PENDING:
                approvals.append(record)
        return approvals

    async def save_approval(self, record: ApprovalRecord) -> ApprovalRecord:
        payload = record.model_dump(mode="json")
        await self._redis.set(RedisKeys.approval(record.approval_id), json.dumps(payload))
        if record.status == ApprovalStatus.PENDING:
            await self._redis.zadd(
                RedisKeys.approvals_pending(),
                {record.approval_id: _iso_to_ts(record.requested_at)},
            )
        else:
            await self._redis.zrem(RedisKeys.approvals_pending(), record.approval_id)
        return record

    async def record_decision(
        self,
        approval_id: str,
        decision: ApprovalDecision,
    ) -> Optional[ApprovalRecord]:
        record = await self.get_approval(approval_id)
        if not record:
            return None

        record.decision = decision
        record.status = (
            ApprovalStatus.APPROVED
            if decision.decision == ApprovalDecisionType.APPROVED
            else ApprovalStatus.REJECTED
        )
        await self.save_approval(record)
        return record

    async def expire_approval(self, approval_id: str) -> Optional[ApprovalRecord]:
        record = await self.get_approval(approval_id)
        if not record:
            return None
        record.status = ApprovalStatus.EXPIRED
        await self.save_approval(record)
        return record

    async def save_resume_state(self, state: GraphResumeState) -> GraphResumeState:
        await self._redis.set(
            RedisKeys.task_resume_state(state.task_id),
            state.model_dump_json(),
        )
        return state

    async def get_resume_state(self, task_id: str) -> Optional[GraphResumeState]:
        raw = await self._redis.get(RedisKeys.task_resume_state(task_id))
        if not raw:
            return None
        raw = _decode(raw)
        try:
            return GraphResumeState(**json.loads(raw))
        except Exception as exc:
            logger.error("Failed to decode resume state for task %s: %s", task_id, exc)
            return None

    async def delete_resume_state(self, task_id: str) -> bool:
        return bool(await self._redis.delete(RedisKeys.task_resume_state(task_id)))

    async def save_execution_ledger(
        self,
        ledger: ActionExecutionLedger,
    ) -> ActionExecutionLedger:
        await self._redis.set(
            RedisKeys.approval_execution(ledger.approval_id, ledger.action_hash),
            ledger.model_dump_json(),
        )
        return ledger

    async def get_execution_ledger(
        self,
        approval_id: str,
        action_hash: str,
    ) -> Optional[ActionExecutionLedger]:
        raw = await self._redis.get(RedisKeys.approval_execution(approval_id, action_hash))
        if not raw:
            return None
        raw = _decode(raw)
        try:
            return ActionExecutionLedger(**json.loads(raw))
        except Exception as exc:
            logger.error(
                "Failed to decode execution ledger for %s/%s: %s",
                approval_id,
                action_hash,
                exc,
            )
            return None

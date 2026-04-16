# Phase Two HITL Rollout Notes

This note captures the operational shape of the approvals and resume flow that now exists in the repo. It is intentionally internal-only and complements `specs/phase-two-hitl-approvals-spec.md`.

## Behavior Summary

- `agent_permission_mode=read_only` blocks write-classified tools immediately.
- `agent_permission_mode=read_write` allows reads, but pauses write-classified tools behind an approval gate.
- `ToolManager.evaluate_tool_call()` is the single classifier for `allow`, `block`, and `require_approval`.
- `ToolManager.resolve_tool_call()` does not mutate task state directly for approval pauses. It raises `ApprovalRequiredError` with the approval record and pending approval summary.
- `redis_sre_agent/agent/tool_execution.py` is the shared boundary that converts `ApprovalRequiredError` into a LangGraph `interrupt(...)` when running inside a graph node.
- `redis_sre_agent/core/docket_tasks.py` is responsible for persisting the pause into task state, emitting task updates, and resuming later runs.

## Resume Semantics

- Resume is keyed by `task_id` and backed by Redis checkpoint state plus `GraphResumeState`.
- A human decision is recorded against an `approval_id` before any resume attempt continues.
- Re-using the same approval after a completed execution does not replay the write action if the execution ledger already shows `executed`.
- A resumed turn can pause again for a later approval in the same task.
- Expired approvals fail validation before resume continues.

## Audit And Idempotency

- Approval history is stored per task via `ApprovalManager`.
- Each approved write uses an `ActionExecutionLedger` keyed by `approval_id` plus `action_hash`.
- The ledger records `pending`, `executed`, or `failed`, plus execution summary/error details.
- Duplicate resume attempts should return the existing outcome rather than re-running the side effect once the ledger shows `executed`.

## API And MCP Surfaces

- REST:
  - `GET /api/v1/tasks/{task_id}/approvals`
  - `POST /api/v1/tasks/{task_id}/resume`
- MCP:
  - `redis_sre_get_task_approvals`
  - `redis_sre_resume_task`
- Task/thread/websocket payloads expose:
  - `status=awaiting_approval`
  - `pending_approval`
  - `resume_supported`

## Deployment Notes

- Resume requires Redis-backed LangGraph checkpoints. In-memory checkpointing is not sufficient for cross-run approval pauses.
- A deployment between pause and resume is safe only when the stored graph compatibility metadata still matches the resumed runtime expectations.
- Unknown tool action kinds remain a policy boundary. If a new write-capable tool is introduced without classification, treat that as a rollout review item before enabling it in production.
- Approval TTL settings should be reviewed alongside operator workflow expectations so approvals do not expire too aggressively during human handoff.

## Validation Baseline

The current validation pass covered:

- approval gate and shared tool execution:
  - `tests/unit/tools/test_manager.py`
  - `tests/unit/tools/test_manager_approval_gate.py`
  - `tests/unit/agent/test_tool_execution.py`
- resume flow:
  - `tests/unit/core/test_docket_resume.py`
- broader HITL surfaces:
  - `tests/unit/api/test_tasks_api.py`
  - `tests/unit/api/test_websockets.py`
  - `tests/unit/mcp_server/test_mcp_server.py`
  - `tests/unit/core/test_tasks.py`
  - `tests/unit/core/test_task_manager.py`

These should be the minimum regression slice for future changes to approvals, resume, or task-state propagation.

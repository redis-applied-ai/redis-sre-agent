# Phase 2 HITL Approvals and Resume Spec

Status: Proposed

Related:
- Confluence: `SRE Agent Phase Two Scope: Human-in-the-Loop`
- `specs/natural-language-target-discovery-spec.md`
- `specs/late-discovery-default-migration-spec.md`
- `specs/redis-cluster-instance-split-implementation-plan.md`

## Summary

Implement action-scoped approvals and durable human-in-the-loop resume for agent-mediated
write operations in `redis-sre-agent`.

The current runtime already has the right high-level pieces:

- user-facing per-turn `Task` state in Redis
- Docket workers that can start a turn and later run another task
- LangGraph-based agents for both chat and deep triage
- handle-backed target discovery and authenticated tool loading
- Redis already available as the persistence backend

What is missing is the remaining Phase 2 glue:

- a durable graph checkpoint per task turn
- an approval record and decision lifecycle
- a task status that can represent "waiting for human input"
- a resume entrypoint that continues the exact interrupted turn
- a safe gate before write-capable tool execution

This spec intentionally assumes the target-resolution and authenticated client-binding work is
already done. It focuses only on approvals, human-in-the-loop pauses, and resume behavior.

## Problem

Today the codebase cannot safely pause a task at an approval boundary and resume it later.

Current gaps in this repo:

- `SRELangGraphAgent` and `ChatAgent` both compile their graphs with `MemorySaver`, so checkpoint
  state is process-local and disappears once the worker exits.
- graph checkpoint identity is currently driven by `session_id`, not by the per-turn `task_id`,
  which is the correct isolation boundary for resumable turns.
- `TaskStatus` only supports `queued`, `in_progress`, `done`, `failed`, and `cancelled`.
- `TaskResponse`, thread payloads, and WebSocket initial state have no concept of pending approval
  metadata.
- `ToolMetadata` does not encode whether a tool call is read-only, write-capable, or unknown-risk.
- `ToolManager.resolve_tool_call()` invokes the tool immediately; there is no approval gate.
- `process_agent_turn()` assumes a turn ends as `done` or `failed`; there is no "exit cleanly and
  wait for approval" path.

Without these changes, the agent cannot support explicit approval before mutating Redis or admin
state, and it cannot resume safely after the worker exits.

## Goals

- Add explicit human approval before agent-mediated write-capable actions.
- Make approval scoped to one specific interrupted action, not the whole session.
- Use durable Redis-backed LangGraph checkpoints so a fresh worker can resume the turn.
- Add a global permission mode MVP: `read_only` or `read_write`.
- Support multiple approval cycles within the same user-facing task.
- Keep task lifecycle distinct from Docket run lifecycle.
- Make approval requests, decisions, and execution outcomes auditable.
- Surface pending approval state consistently through REST, MCP, and WebSocket consumers.

## Non-goals

- Re-solving target resolution, authenticated client loading, or target-handle attachment.
- Multi-target discovery or comparison orchestration that is already covered elsewhere.
- Per-user RBAC or ABAC.
- A general-purpose policy engine by tool, actor, and resource.
- Reworking direct CLI or explicit destructive MCP endpoints that already use `confirm=true`.
- Redesigning the broader routing and discovery architecture.

## Current-State Constraints

### 1. Docket is already the right execution transport

The Confluence design note is correct for this repo: Docket should not try to pause a running task
in place. `process_agent_turn()` should end normally at the approval boundary, and a later Docket
run should resume from the graph checkpoint.

### 2. Checkpoint isolation must be per task, not per thread

The repo’s user-facing async contract is per-turn `Task`. That means the resumable graph identity
should be `graph_thread_id == task_id`, not the conversation `thread_id`.

Using `thread_id` or `session_id` for checkpoint isolation would allow one turn’s resume state to
collide with later turns in the same conversation.

### 3. Both agent implementations need the same gate

`process_agent_turn()` can route onto either:

- `SRELangGraphAgent` for full triage
- `ChatAgent` for lightweight/default chat

Both use LangGraph and both can execute tools. The approval gate cannot live only in the deep
triage path.

### 4. Interrupted nodes replay from node start

Approval interrupts must occur immediately before side effects. Any work before the interrupt must
be idempotent or replay-safe.

### 5. Bound targets are already opaque handles

The target-discovery path now gives the runtime safe target handles and authenticated provider
attachments without exposing credentials to the model. Approval payloads must preserve that design:
they can include target handles and safe argument previews, but never secrets or private binding
details.

## Proposed Design

### 1. Add a global permission mode

Add a new global setting in `redis_sre_agent/core/config.py`:

- `agent_permission_mode: Literal["read_only", "read_write"] = "read_only"`

Behavior:

- `read_only`
  - read-only tools execute normally
  - write-capable or unknown-risk tools do not execute
  - no approval records are created
  - the graph receives a synthetic blocked result so the model can explain that action mode is
    disabled
- `read_write`
  - read-only tools execute normally
  - write-capable tools require approval through the HITL flow
  - unknown-risk tools remain blocked until explicitly classified

Treating unclassified tools as blocked is the safest repo default, especially for dynamically
loaded MCP tools.

### 2. Add explicit tool action classification

Extend the tool model in `redis_sre_agent/tools/models.py`.

Add:

- `ToolActionKind = "read" | "write" | "unknown"`
- `ToolMetadata.action_kind`
- optional `ToolMetadata.action_summary`
- optional `ToolMetadata.approval_scope`

Rules:

- built-in non-mutating tools must be marked `read`
- built-in mutating tools must be marked `write`
- dynamically loaded MCP tools default to `unknown` unless the MCP provider config classifies them

This is the contract the approval gate uses. `ToolCapability` is not enough because capability says
what kind of information a tool deals with, not whether it mutates state.

### 3. Add approval and resume persistence models

Add a new core module, for example `redis_sre_agent/core/approvals.py`, with these models:

- `ApprovalStatus = pending | approved | rejected | expired | superseded`
- `ApprovalRecord`
- `ApprovalDecision`
- `PendingApprovalSummary`
- `GraphResumeState`
- `ActionExecutionLedger`

Suggested `ApprovalRecord` fields:

- `approval_id`
- `task_id`
- `thread_id`
- `graph_thread_id`
- `interrupt_id`
- `graph_type`
- `graph_version`
- `tool_name`
- `tool_args`
- `tool_args_preview`
- `action_kind`
- `action_hash`
- `target_handles`
- `status`
- `requested_at`
- `expires_at`
- `decision`
- `decision_at`
- `decision_by`
- `decision_comment`

Suggested `GraphResumeState` fields:

- `task_id`
- `thread_id`
- `graph_thread_id`
- `graph_type`
- `graph_version`
- `checkpoint_ns`
- `checkpoint_id`
- `waiting_reason`
- `pending_approval_id`
- `pending_interrupt_id`
- `resume_count`
- `updated_at`

Suggested `ActionExecutionLedger` fields:

- `ledger_key = approval_id + action_hash`
- `task_id`
- `approval_id`
- `tool_name`
- `action_hash`
- `status = pending | executed | skipped | failed`
- `executed_at`
- `result_summary`
- `error`

Redis key additions in `redis_sre_agent/core/keys.py`:

- `sre:approval:{approval_id}`
- `sre:task:{task_id}:approvals`
- `sre:approvals:pending`
- `sre:task:{task_id}:resume_state`
- `sre:approval_execution:{approval_id}:{action_hash}`

### 4. Extend task state for waiting input

Extend `TaskStatus` in `redis_sre_agent/core/tasks.py`:

- add `AWAITING_APPROVAL = "awaiting_approval"`

Extend `TaskState` and API schema responses with:

- `pending_approval: Optional[PendingApprovalSummary]`
- `resume_supported: bool`

`PendingApprovalSummary` should be small and UI-friendly:

- `approval_id`
- `interrupt_id`
- `tool_name`
- `summary`
- `requested_at`
- `expires_at`
- `status`

This is what `GET /tasks/{task_id}`, thread views, and WebSocket initial state should show.

### 5. Use Redis-backed LangGraph checkpointing

Replace `MemorySaver` in both `SRELangGraphAgent` and `ChatAgent` with a shared Redis-backed
checkpointer factory based on `langgraph-checkpoint-redis`, which is already a project
dependency.

Required behavior:

- `graph_thread_id` must equal `task_id`
- checkpoint namespace should be explicit, for example `agent_turn`
- graph version must be recorded in `GraphResumeState`
- the same graph definition must be reconstructible during resume

Add a small helper such as `redis_sre_agent/agent/checkpointing.py` that:

- creates the Redis checkpointer
- returns the `graph_thread_id`
- persists checkpoint metadata needed for resume compatibility checks

### 6. Put the approval gate below both agents

Do not implement approvals as an outer API wrapper around the whole turn. The gate must sit at the
tool-execution boundary shared by both LangGraph agents.

Preferred design:

- add a reusable `ApprovalGate` service
- make the LangGraph tool adapters wrap tool execution with that gate
- keep the actual interrupt inside graph execution, immediately before the tool invoke

The gate contract should look like:

1. inspect tool metadata
2. if `action_kind == read`, invoke normally
3. if `permission_mode == read_only`, return a synthetic blocked result
4. if `action_kind == unknown`, return a synthetic blocked result explaining that the tool is not
   classified for HITL execution
5. if `action_kind == write` and no approved decision has been supplied for this interrupt, create
   `ApprovalRecord` and call LangGraph `interrupt(...)`
6. if `action_kind == write` and an approved decision is supplied, validate it against the exact
   `approval_id`, `interrupt_id`, and `action_hash`, then execute once using the idempotency ledger
7. if a rejection is supplied, return a synthetic rejected result so the agent can continue with
   safe alternatives

This requires moving approval handling below `LGToolNode` construction. The least disruptive
approach is to wrap the `StructuredTool` adapters rather than rewrite the whole graph.

### 7. Approval interrupt payload

The interrupt payload should be explicit and user-facing, but secret-safe.

Suggested shape:

```json
{
  "kind": "approval_required",
  "approval_id": "01H...",
  "interrupt_id": "01I...",
  "task_id": "01J...",
  "thread_id": "01K...",
  "tool_name": "redis_enterprise_scale_database",
  "summary": "Scale database memory from 2 GB to 4 GB",
  "tool_args_preview": {
    "database_id": "db-123",
    "memory_size_gb": 4
  },
  "target_handles": ["tgt_01..."],
  "requested_at": "2026-04-13T20:00:00Z",
  "expires_at": "2026-04-13T21:00:00Z"
}
```

Secrets, raw credentials, private binding details, and opaque auth tokens must never appear here.

### 8. Worker lifecycle

#### Initial run

`process_agent_turn()` should:

1. mark the task `in_progress`
2. run the selected graph with Redis checkpointing and `graph_thread_id = task_id`
3. if the graph interrupts for approval:
   - persist `ApprovalRecord`
   - persist `GraphResumeState`
   - set task status to `awaiting_approval`
   - set `pending_approval`
   - emit a task update and WebSocket stream event
   - exit the Docket run normally without a final assistant message
4. if the graph completes:
   - persist the final assistant message
   - set task result
   - mark task `done`

#### Resume run

Add a dedicated Docket task such as `resume_agent_turn(...)`.

It should:

1. load `GraphResumeState`
2. validate graph compatibility
3. load the approval decision for the pending approval
4. mark task `in_progress`
5. rebuild the same graph with the same checkpointer
6. call `app.ainvoke(Command(resume=...))`
7. either:
   - hit another approval boundary and return to `awaiting_approval`
   - or finish and mark the task `done`

### 9. Approval lifecycle rules

Rules for `ApprovalRecord`:

- approval applies only to one interrupt and one action hash
- approval does not authorize future actions automatically
- approval records are one-time consumable
- approval decisions are immutable after persistence
- expiry must be enforced during resume
- a newer approval request for the same interrupted action should supersede the prior pending one

Rules for execution:

- rejections should allow the graph to continue with a safe explanation when possible
- duplicate approved resumes must return the recorded prior execution outcome
- stale or mismatched `approval_id` / `interrupt_id` / `action_hash` combinations must fail closed

### 10. API and MCP additions

Add REST endpoints:

- `GET /api/v1/tasks/{task_id}/approvals`
  - returns all approval records for the task, newest first
- `GET /api/v1/approvals`
  - filterable by `status`, `task_id`, `thread_id`, `user_id`
  - v1 only needs pending and recent history lookup
- `POST /api/v1/tasks/{task_id}/resume`
  - generic resume endpoint
  - if the task is waiting for approval, payload must include the approval decision

Suggested resume payload:

```json
{
  "approval": {
    "approval_id": "01H...",
    "decision": "approved",
    "decision_by": "user-123",
    "comment": "Proceed"
  }
}
```

Rules:

- approval decisions are one-time consumable
- expired approvals cannot resume execution
- the resume endpoint enqueues a new Docket run; it does not execute inline

Add MCP equivalents:

- `redis_sre_get_task_approvals(task_id)`
- `redis_sre_list_approvals(status=None, task_id=None, thread_id=None)`
- `redis_sre_resume_task(task_id, approval=...)`

### 11. WebSocket and task payload changes

Update:

- `redis_sre_agent/api/schemas.py`
- `redis_sre_agent/api/tasks.py`
- `redis_sre_agent/api/threads.py`
- `redis_sre_agent/api/websockets.py`
- `redis_sre_agent/core/task_events.py`

Required behavior:

- task responses include `awaiting_approval` status and `pending_approval`
- thread views surface the latest task’s pending approval summary
- WebSocket `InitialStateEvent` includes pending approval metadata
- a stream event is emitted when a task enters or leaves `awaiting_approval`

### 12. Audit logging and idempotency

Every write-capable action attempt must create an auditable trail:

- approval requested
- approval approved or rejected
- execution skipped, executed, or failed

Use `approval_id + action_hash` as the execution idempotency key.

That key must prevent duplicate side effects from:

- Docket retries
- worker crashes after approval but before final task completion
- repeated resume requests against the same approval

If a duplicate approved resume is attempted after the action already executed, the runtime should
return the prior outcome instead of executing again.

## Implementation Touchpoints

Primary files to change:

- `redis_sre_agent/core/config.py`
- `redis_sre_agent/core/keys.py`
- `redis_sre_agent/core/tasks.py`
- `redis_sre_agent/core/docket_tasks.py`
- `redis_sre_agent/core/task_events.py`
- `redis_sre_agent/api/schemas.py`
- `redis_sre_agent/api/tasks.py`
- `redis_sre_agent/api/threads.py`
- `redis_sre_agent/api/websockets.py`
- `redis_sre_agent/mcp_server/server.py`
- `redis_sre_agent/tools/models.py`
- `redis_sre_agent/tools/manager.py`
- `redis_sre_agent/agent/langgraph_agent.py`
- `redis_sre_agent/agent/chat_agent.py`

New modules likely needed:

- `redis_sre_agent/core/approvals.py`
- `redis_sre_agent/core/approval_helpers.py`
- `redis_sre_agent/agent/checkpointing.py`

## Delivery Slices

### Slice 1: Task and approval persistence

- add new models and Redis keys
- add `awaiting_approval` task status
- add approval query APIs

### Slice 2: Durable checkpointing

- replace `MemorySaver`
- key checkpoints by `task_id`
- persist `GraphResumeState`

### Slice 3: Tool action classification and gate

- add `ToolActionKind`
- classify built-in tools
- wrap tool execution with approval gate

### Slice 4: Resume flow

- add `POST /tasks/{task_id}/resume`
- add Docket resume task
- handle approved, rejected, and expired decisions

### Slice 5: UI/MCP surface and hardening

- add pending approval payloads to REST, thread, WebSocket, and MCP surfaces
- add audit and idempotency ledger coverage
- verify multiple approval cycles in one task

## Acceptance Criteria

- In `read_only`, agent-mediated write attempts never execute and never create approval records.
- In `read_write`, every classified write attempt creates a pending approval record before any side
  effect occurs.
- When approval is requested, the task transitions to `awaiting_approval` and the Docket run exits
  cleanly.
- Resume continues from the correct checkpoint for the same `task_id`.
- Multiple approval cycles in one task work correctly.
- Rejection allows the graph to continue with a safe explanation instead of failing the turn.
- Repeated resume requests do not duplicate side effects.
- Approval and execution history is queryable through REST and MCP.

## Test Plan

Add targeted unit and integration coverage for:

- `TaskStatus.awaiting_approval` serialization and API responses
- approval record CRUD and query helpers
- `read_only` blocking behavior
- `read_write` interrupt creation behavior
- rejected approval behavior
- expired approval behavior
- idempotent execution ledger behavior on repeated resume
- graph checkpoint isolation by `task_id`
- resume after a fresh worker process
- multiple approval cycles in one task
- WebSocket initial-state and stream payloads including pending approval data

Use test doubles for mutating tools rather than adding test-only branches into production code.

## Open Questions

- What is the authoritative identity for `decision_by` in the first release: raw user id from the
  API caller, dashboard session identity, or an external identity source?
- What is the default approval expiry window?
- Do we want `unknown` tools to be permanently blocked in v1, or configurable per deployment via
  MCP tool metadata overrides?
- What graph compatibility policy do we want when a deployment occurs between interrupt and resume:
  fail closed immediately, or allow compatible version ranges?

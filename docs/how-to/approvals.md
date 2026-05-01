## Approval-Aware Task Flow

This guide explains how mutating tool calls are handled when the agent is configured for human-in-the-loop approvals, how paused tasks appear over the API and UI, and how to approve or reject a pending action.

### Prerequisites

- The API and worker are running.
- You know the task ID or thread ID you want to inspect.
- If API auth is enabled, include the appropriate auth header.

### 1) Enable approval mode

Set these values before starting the API and worker:

```bash
AGENT_PERMISSION_MODE=read_write
AGENT_APPROVAL_TTL_SECONDS=3600
```

Mode behavior:

- `read_only`
  Read-capable tools can still run. Mutating tools are blocked immediately and do not create approval records.
- `read_write`
  Mutating tools pause before side effects, create a pending approval record, and require an explicit decision before execution continues.

If you need only the config reference, see [Configuration How-to](configuration.md) and [Configuration Reference](../reference/configuration.md).

### 2) What a paused task looks like

When a task reaches a gated write, the runtime returns to the operator with:

- `status: "awaiting_approval"`
- `pending_approval`
- `resume_supported: true`

You can see that through either the task endpoint or the thread view:

```bash
curl -fsS http://localhost:8080/api/v1/tasks/<task_id> | jq
curl -fsS http://localhost:8080/api/v1/threads/<thread_id> | jq
```

The `pending_approval` payload is intentionally small and UI-friendly. It includes:

- `approval_id`
- `interrupt_id`
- `tool_name`
- `summary`
- `requested_at`
- `expires_at`
- `status`

The current UI surfaces the same state in `TaskMonitor`, including the pending approval summary, recent approval history, and approve/reject controls.

### 3) Inspect approval history

List the task’s approval records before making a decision:

```bash
curl -fsS http://localhost:8080/api/v1/tasks/<task_id>/approvals | jq
```

This returns task-scoped approval records, newest first. Use it when:

- you want to confirm which approval is currently pending
- the task has already gone through multiple approval cycles
- you need to audit who approved or rejected a prior action

### 4) Approve or reject and resume

To continue the paused task, call the resume endpoint with the active `approval_id`.

Approve:

```bash
curl -fsS -X POST http://localhost:8080/api/v1/tasks/<task_id>/resume \
  -H 'Content-Type: application/json' \
  -d '{
    "approval_id": "<approval_id>",
    "decision": "approved",
    "decision_by": "operator@example.com",
    "decision_comment": "Approved after review"
  }' | jq
```

Reject:

```bash
curl -fsS -X POST http://localhost:8080/api/v1/tasks/<task_id>/resume \
  -H 'Content-Type: application/json' \
  -d '{
    "approval_id": "<approval_id>",
    "decision": "rejected",
    "decision_by": "operator@example.com",
    "decision_comment": "Rejected pending a maintenance window"
  }' | jq
```

On success, the task is moved back to `in_progress` and the worker resumes the paused graph. Depending on the next step, the task may:

- complete normally
- fail
- return to `awaiting_approval` if another mutating tool needs its own decision

### 5) UI expectations

The current UI behavior matches the approval-aware API flow:

- `TaskMonitor` remains visible while the task is in `awaiting_approval`
- the pending approval summary is rendered above the message stream
- recent approval history is shown when available
- the operator can use approve/reject buttons to call the resume endpoint directly

This is intended for local and operator workflows. Keep the UI behind your normal authentication layer.

### 6) Operational notes

- Approval is action-scoped, not session-wide. One approval applies only to the specific paused action.
- Expired approvals cannot resume execution. Use the latest pending approval from the task or approval-history response.
- A task can pause for approval more than once in the same overall workflow.
- If `resume_supported` is false, treat the task as non-resumable from the current surface and inspect task history before retrying.

### See also

- [Using the API: Core Workflows](api.md)
- [Configuration How-to](configuration.md)
- [Configuration Reference](../reference/configuration.md)

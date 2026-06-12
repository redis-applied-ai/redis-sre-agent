## Response Feedback

### What this is

The feedback system lets you record a thumbs-up, thumbs-down, or withdrawal on any completed agent task. The rating is available from your web UI, third-party HTTP clients, MCP-connected clients (Claude, Cursor, and similar), and the `redis-sre-agent` CLI. Feedback is anonymous — no authentication is required — and follows last-write-wins semantics, so any surface can update or retract a previous rating at any time.

### HTTP usage

**Port note**: Docker Compose exposes the API on port **8080**; local uvicorn uses port **8000**. Examples below use port 8080. Replace with 8000 if running locally.

#### Submit or update feedback

```bash
# Thumbs-up
curl -fsS -X POST http://localhost:8080/api/v1/tasks/<task_id>/feedback \
  -H 'Content-Type: application/json' \
  -d '{"verdict":"up"}' | jq

# Thumbs-down with an optional comment
curl -fsS -X POST http://localhost:8080/api/v1/tasks/<task_id>/feedback \
  -H 'Content-Type: application/json' \
  -d '{"verdict":"down","comment":"Missed the eviction policy angle"}' | jq
```

Expected 200 response:

```json
{
  "task_id": "task-abc123",
  "verdict": "down",
  "comment": "Missed the eviction policy angle",
  "created_at": "2026-05-18T10:00:00.000000+00:00",
  "updated_at": "2026-05-18T10:05:00.000000+00:00"
}
```

#### Retrieve current feedback

```bash
curl -fsS http://localhost:8080/api/v1/tasks/<task_id>/feedback | jq
```

Returns the `FeedbackRecord` JSON above (200) or a 404 when no feedback has been submitted yet.

#### Validation errors (422)

Invalid input returns a standard Pydantic 422 response. Each problem appears as an item in the `detail` array:

```json
{
  "detail": [
    {
      "type": "literal_error",
      "loc": ["body", "verdict"],
      "msg": "Input should be 'up', 'down' or 'withdrawn'",
      "input": "meh",
      "ctx": {"expected": "'up', 'down' or 'withdrawn'"}
    }
  ]
}
```

### MCP usage

Call `redis_sre_submit_feedback` from any MCP-connected client:

```python
redis_sre_submit_feedback(
    task_id="task-abc123",
    verdict="up",
    comment="Exactly the right diagnosis",   # optional
)
```

Returns the same `FeedbackRecord` dict on success. Unlike most other tools in this server, validation errors (`verdict` outside the enum, `comment` exceeding 2048 chars) and `TaskNotFoundError` propagate as native MCP errors rather than success-shaped `{"error": ..., "status": "failed"}` dicts. Handle them accordingly in your MCP client.

### CLI usage

All feedback commands are under the `feedback` subgroup:

```bash
# Submit thumbs-up
uv run redis-sre-agent feedback up <task_id>
uv run redis-sre-agent feedback up <task_id> --comment "Great diagnosis"

# Submit thumbs-down
uv run redis-sre-agent feedback down <task_id>
uv run redis-sre-agent feedback down <task_id> --comment "Missed the eviction policy angle"

# Withdraw (sets verdict to 'withdrawn'; preserves history)
uv run redis-sre-agent feedback withdraw <task_id>

# Show current feedback for a task
uv run redis-sre-agent feedback show <task_id>

# List recent feedback with optional filters
uv run redis-sre-agent feedback list
uv run redis-sre-agent feedback list --since 24h --verdict down --limit 50
```

**`feedback show` exit-code contract**: exits 0 and prints `null` when the task exists but has no feedback yet; exits non-zero only on hard errors (task not found, Redis error).

**`--since` format**: accepts `<N>{s,m,h,d}` only — for example `30m`, `24h`, `7d`. ISO-8601 dates are rejected in Phase 1.

**`--limit`**: defaults to 50, accepts values up to 500. Values above 500 are clamped to 500.

### Semantics

- **Last-write-wins**: any surface can overwrite a previous rating, including changing from `down` to `up` or withdrawing entirely.
- **Anonymous**: no user identity is recorded; the hash stores only the verdict, optional comment, and timestamps.
- **Withdrawal preserves history**: `withdraw` sets `verdict` to `"withdrawn"` — it does not delete the Redis hash. `created_at` and `updated_at` remain.
- **`created_at` is anchored**: the first write locks `created_at` via `HSETNX`; resubmissions only update `updated_at`.
- **No rating yet**: the absence of the feedback key means no feedback has been submitted. `GET /api/v1/tasks/{task_id}/feedback` returns 404; `feedback show` prints `null`.
- **Idempotent resubmits**: if the verdict and comment are identical to the stored record, the write is short-circuited and the existing record is returned without touching `updated_at` or publishing a stream event.

### Storage layout

Each task's feedback is stored as a single Redis hash:

```
sre:feedback:task:{task_id}
```

Fields:

| Field | Type | Notes |
|-------|------|-------|
| `task_id` | string | Same as the key suffix |
| `verdict` | string | `"up"`, `"down"`, or `"withdrawn"` |
| `comment` | string | Empty string when no comment was provided |
| `created_at` | string | ISO-8601; anchored on first write via `HSETNX` |
| `updated_at` | string | ISO-8601; overwritten on every change |

This layout is the public-ish contract. Tooling that reads feedback directly should treat the hash fields above as stable.

### WebSocket event

After every successful write, a `feedback_submitted` event is published to the task's stream channel:

```
sre:stream:task:{thread_id}
```

Event payload:

```json
{
  "update_type": "feedback_submitted",
  "task_id": "<task_id>",
  "verdict": "down",
  "has_comment": true
}
```

WebSocket subscribers (for example, the web UI) can listen for `update_type == "feedback_submitted"` to refresh the feedback widget in real time. If a task's `thread_id` is missing or malformed, the hash write still succeeds and only the stream publish is skipped (fail-open).

### Phase 2 (not yet available)

The following capabilities are planned but not implemented in the current release:

- Aggregate analytics endpoints (verdict counts, comment trends per asset or time window).
- Learning-loop integration with Agent Memory Service — down-rated answers feed into memory correction signals.
- Eval auto-labeling via the CLI (`feedback list` output as a labeling source for `make test-eval-pr`).
- Optional rate limiting per IP or session.
- Optional categorical reason codes alongside free-text comments.
- Optional `message_id` anchoring to tie feedback to a specific assistant turn within a thread.

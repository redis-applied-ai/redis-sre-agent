# Late-Discovery-First Target Scope Migration

Status: Proposed

## Summary

Move the runtime from eager singular target binding (`instance_id` / `cluster_id`) to a
late-discovery-first model where target resolution, attachment, and authenticated tool loading are
server-side behaviors built around opaque target bindings.

Under the target model introduced by the recent multi-target comparison work, the default path
should be:

1. start with base tools
2. resolve targets from thread state, seed hints, or user language
3. persist opaque bindings
4. attach authenticated tools from those bindings
5. let the agent operate over zero, one, or many targets without switching architectures

This spec defines the migration needed to make that the default behavior across interactive chat,
deep triage, query helpers, MCP entrypoints, schedules, and thread-backed follow-up turns.

## Problem

The current codebase still mixes two scope models:

- legacy singular scope carried by `instance_id` / `cluster_id`
- attached target scope carried by opaque handles and persisted bindings

That creates several failure modes and architectural contradictions:

- unbound tool reload depends on thread-backed attached bindings, but callers still pass singular
  identifiers as the primary happy path
- the runtime still promotes singleton attached targets back into `instance_id` /
  `cluster_id`, which breaks the “one target is just a target set of size 1” model
- thread reload is vulnerable because `ToolManager` expects a real `thread_id`, while agent
  construction frequently passes `session_id`
- schedules, query helpers, MCP adapters, thread search metadata, and memory context still encode
  the old singular contract
- automated runs need non-interactive lazy binding from the initial prompt or instructions, but
  current scheduling paths still assume preconfigured `redis_instance_id`

The result is that multi-target comparison works in key agent paths but the system as a whole has
not yet converged on late discovery as the default architecture.

## Goals

- Make late discovery the default scope model for Redis-targeted execution.
- Treat one target as a target set of size 1, not as a different runtime architecture.
- Preserve zero-scope execution for general chat/knowledge runs.
- Support non-interactive lazy binding for automated runs using the initial message or instructions.
- Keep target discovery, binding, and authenticated tool loading server-side.
- Ensure thread-based follow-up turns can reliably reload attached bindings.
- Migrate compatibility surfaces deliberately instead of leaving parallel entry contracts in place.

## Non-goals

- Removing `RedisInstance` or `RedisCluster` as internal metadata stores.
- Eliminating support-package execution mode.
- Replacing all existing APIs in one flag-day cutover.
- Designing the full post-migration UI or operator workflow for target management.

## Design Principles

1. `N=1` and `N>1` use the same target-binding contract.
2. The LLM chooses among already-bound tool surfaces; it does not authenticate or resolve raw
   target identities itself.
3. `thread_id` and `session_id` are different concepts and must stay explicit.
4. Compatibility inputs may remain temporarily, but only as seed-hint adapters into the new model.
5. Tests for reload and compatibility behavior must land before removing singleton fallbacks.

## Current-State Constraints

### 1. Attached-target reload is thread-based

`ToolManager` reloads attached bindings from thread state only when it has the correct
`thread_id`. That is incompatible with the current agent construction pattern that often passes
`session_id` in that slot.

Implication:

- fixing the `thread_id` / `session_id` contract is a prerequisite for any broader late-binding
  migration

### 2. Singleton compatibility is still live in multiple places

Current runtime behavior still depends on `instance_id` / `cluster_id` after target attachment:

- `process_agent_turn()` promotes a single attached binding back into singular scope
- `attach_target_matches()` writes singleton bindings back into thread context as singular ids
- `SRELangGraphAgent` still uses singular ids for rich single-instance context and cluster fan-out

Implication:

- singleton promotion cannot be removed until those consumers are replaced with a normalized scope
  view

### 3. Non-agent compatibility surfaces still depend on singular scope

The old model is not confined to agent entrypoints. It also exists in:

- thread indexing and thread search metadata
- agent memory preparation
- unified query helper flows
- MCP task entrypoints
- schedule model, helpers, API, CLI, and manual-run flow

Implication:

- removing singular compatibility only in the agents would leave the rest of the system split

## Proposed Model

## 1. Introduce `TurnScope`

Add a normalized turn-scope object that becomes the single runtime contract for execution.

Suggested shape:

- `thread_id: Optional[str]`
- `session_id: Optional[str]`
- `scope_kind: zero_scope | target_bindings | support_package`
- `bindings: list[TargetBinding]`
- `toolset_generation: Optional[int]`
- `prompt_context: dict`
- `seed_hints: dict`
- `resolution_policy: allow_zero_scope | require_target | require_exact | allow_multiple`
- `automation_mode: interactive | automated`
- `support_package_context: Optional[dict]`

Required properties:

- it must represent support-package runs as a first-class variant, not a side channel
- it must be serializable into thread context
- it must treat the binding set as the full target scope, including the single-target case
- it must provide enough metadata for both tool binding and prompt construction
- it must carry the real `thread_id` used for thread-backed binding reload

### Why this matters

Today “scope” is split across `context`, thread state, tool-manager constructor arguments, and
agent-specific prompt branches. `TurnScope` makes that explicit and lets the runtime replace the
old singular contract in one place instead of by scattered conditionals.

## 2. Make `ToolManager` late-binding capable without thread-only reload

`ToolManager` should continue to support thread-backed reload, but it must also support
late-binding from explicitly supplied bindings for threadless or newly initialized flows.

Add a constructor- or setup-level input such as:

- `initial_target_bindings`
- or `initial_scope`

Required behavior:

- if `initial_target_bindings` are supplied, attach them directly
- if no explicit bindings are supplied and a real `thread_id` exists, reload attached bindings from
  thread state
- do not require a pre-bound `redis_instance` / `redis_cluster` for the primary runtime path

This keeps interactive and automated flows on the same architectural path while preserving reload.

## 3. Make target discovery a frontend onto the same scope contract

The existing target-discovery tool path and the centralized turn-resolution path must converge.

Required behavior:

- centralized turn resolution may resolve targets from the current message or instructions
- `resolve_redis_targets` may still be called by the agent
- both paths must produce the same `TargetBinding` / `TurnScope` representation
- both paths must use the same persistence and tool-attachment logic

This prevents the system from keeping two parallel discovery pipelines.

## 4. Stop treating singular ids as canonical scope

`instance_id` and `cluster_id` should become compatibility seed hints, not the canonical
representation of active runtime scope.

Acceptable transitional role:

- caller supplies `instance_id` or `cluster_id`
- runtime converts that to a `TurnScope` with target bindings
- downstream agent and tool-loading code consume `TurnScope`, not the singular fields directly

End-state:

- active Redis target scope is represented by bindings and related scope metadata
- singular ids are no longer required for normal execution

## Interactive and Automated Modes

## Interactive mode

Default behavior:

- start with base tools
- if no target bindings exist, the agent may discover targets from the user’s prompt
- if resolution is ambiguous, the agent may ask follow-up questions
- once resolved, the runtime persists bindings and attaches authenticated tools

## Automated mode

Automated runs cannot depend on a back-and-forth clarification loop.

Default behavior:

- derive scope from the initial message or instructions, plus any stored seed hints
- if policy is `allow_zero_scope`, a zero-target run is valid
- if policy requires targets, resolve before execution
- if required resolution is ambiguous or empty, fail with a structured resolution error

This supports scheduled jobs and similar workflows without reverting to preconfigured singular ids.

## Compatibility Policies

Automation must not use one blanket rule.

Support these policies:

- `allow_zero_scope`
- `require_target`
- `require_exact`
- `allow_multiple`

Examples:

- general scheduled knowledge/chat run: `allow_zero_scope`
- scheduled diagnostics against targets named in instructions: `require_target`
- automated comparison run: `allow_multiple`

## Entry Paths To Migrate

## 1. `process_agent_turn()`

This becomes the main normalization point for runtime scope.

Required behavior:

- load any existing attached bindings from thread state
- merge caller-provided seed hints
- resolve targets from the current message only when policy or missing scope requires it
- build `TurnScope`
- persist updated scope state
- pass normalized scope to routing, tool loading, and prompt construction

`process_agent_turn()` should stop being a place where singular ids are privileged over bindings.

## 2. `ChatAgent` and `SRELangGraphAgent`

Both agents should consume `TurnScope` instead of building primary behavior off raw
`instance_id` / `cluster_id`.

They still need to distinguish:

- zero-scope Redis/knowledge execution
- target-bound execution
- support-package execution

But those should be `TurnScope` branches, not legacy scope branches.

Required outcomes:

- prompt context for single-target runs still stays rich
- cluster-only fan-out behavior still works
- multi-target prompt context still works
- support-package flows remain explicit

## 3. Query helper and MCP task-entry adapters

These remain compatibility adapters during migration.

Required behavior:

- continue accepting legacy `instance_id` / `cluster_id` inputs temporarily
- validate them if provided
- translate them into `TurnScope` seed hints or bindings
- do not treat them as permanent parallel runtime contracts

This includes:

- unified query helpers
- MCP query tools
- MCP chat/triage entrypoints

## 4. Schedules

Schedules need a dual-read/write migration.

Add new schedule fields such as:

- `target_seed_query`
- `target_seed_hints`
- `resolution_policy`
- `allow_zero_scope`

Transitional behavior:

- read existing `redis_instance_id`
- write new fields for new or migrated schedules
- manual runs and cron-triggered runs both resolve through the same scope path

End-state behavior:

- schedules do not require preconfigured singular ids
- schedules can lazy-bind from their own instructions plus structured hints

## 5. Thread metadata and memory context

These are migration-critical compatibility surfaces.

Required work:

- replace thread-index dependence on a single `instance_id` with scope metadata that can represent
  zero, one, or many targets
- update thread listing/search summaries so they remain useful after singular scope disappears
- update agent memory preparation so it can derive asset or scope context from `TurnScope`, not
  only from `instance_id` / `cluster_id`

This work is necessary to avoid regressions outside the main execution path.

## Migration Order

## Phase 0: Test and compatibility baseline

Before deleting any singleton compatibility behavior, add tests for the risky paths:

- attached-target reload when `session_id != thread_id`
- scheduled late-binding from instructions
- CLI or query-created threads with distinct `session_id` / `thread_id`
- singleton attached-target prompt construction after scope normalization
- backward-compatible schedule reads and writes
- support-package and zero-scope `TurnScope` variants

This phase is the gate for later removal.

## Phase 1: Fix identity contract

- make `thread_id` and `session_id` explicit throughout the agent and tool-manager path
- pass the real `thread_id` anywhere attached bindings may need to reload
- add regression coverage for thread-backed reload

## Phase 2: Introduce `TurnScope`

- define `TurnScope`
- add thread serialization/deserialization support
- make centralized resolution produce `TurnScope`
- ensure support-package and zero-scope variants are represented

## Phase 3: Upgrade `ToolManager`

- add explicit late-binding inputs such as `initial_target_bindings`
- keep thread-backed reload as fallback when no bindings are supplied
- preserve current authenticated provider attachment behavior

## Phase 4: Move discovery behind one contract

- make centralized turn resolution and `resolve_redis_targets` produce the same binding/scope
  objects
- remove duplicated discovery-side attachment logic

## Phase 5: Switch agents to `TurnScope`

- make `ChatAgent` and `SRELangGraphAgent` consume normalized scope
- rebuild single-target prompt quality and cluster fan-out from that scope
- keep support-package behavior explicit

## Phase 6: Migrate compatibility adapters

- query helpers
- MCP adapters
- schedule helpers
- schedule API
- schedule CLI
- thread metadata/indexing
- memory context preparation

All of these should move to `TurnScope` or seed-hint adapters.

## Phase 7: Remove singleton compatibility reads and writes

Only after phases 0 through 6 are in place:

- stop writing singleton attached scope back to `instance_id` / `cluster_id`
- stop promoting single attached bindings back into singular scope in runtime paths
- remove downstream reads that still assume singular runtime scope

This is intentionally after the compatibility-adapter migration, not before it.

## Testing Strategy

Minimum required coverage before singleton-removal work is considered complete:

- unit tests for `TurnScope` serialization and thread reload
- unit tests for `ToolManager` with explicit initial bindings
- unit tests for `process_agent_turn()` in zero, one, and many target modes
- unit tests for schedule dual-read/write behavior
- unit tests for query-helper and MCP compatibility adapters
- integration tests for follow-up turns where `session_id != thread_id`
- integration tests for automated target resolution from schedule instructions

## Backward Compatibility

Short-term compatibility is acceptable in these forms:

- callers may still provide `instance_id` / `cluster_id`
- stored schedules may still contain `redis_instance_id`
- thread summaries may temporarily continue exposing legacy scope fields

But all of those should be treated as migration compatibility, not as the steady-state design.

## Resolved Decisions

### 1. Thread summaries use a sibling `ScopeSummary`, not raw `TurnScope`

Thread indexing, thread list/search summaries, and other lightweight metadata surfaces should not
read directly from `TurnScope`.

End-state decision:

- `TurnScope` remains the runtime execution contract
- a sibling normalized `ScopeSummary` becomes the index/search/list contract

`ScopeSummary` should be derived from `TurnScope` and carry only stable summary fields:

- `scope_kind`
- `target_count`
- `target_kinds`
- `target_resource_ids`
- `display_summary`
- `support_package_id`

This keeps thread indexing and list/search payloads compact and queryable without persisting the
entire runtime scope object or exposing prompt-only data.

### 2. `ScopeSummary` replaces singular `instance_id` in thread indexing and summaries

The thread index and thread summary payloads should stop using `instance_id` as the primary asset
field.

End-state index/list fields:

- `scope_kind`: `zero_scope | target_bindings | support_package`
- `target_count`: integer
- `target_kinds`: tag/list field for filtering
- `target_resource_ids`: capped list for exact filtering and lookup
- `display_summary`: human-readable summary such as
  `checkout-cache-prod`, `2 targets: checkout-cache-prod, session-cache-stage`, or
  `support package: RET-4421`

Rules:

- zero-scope threads use `scope_kind=zero_scope`, `target_count=0`, and a blank
  `target_resource_ids`
- single-target threads still use `target_count=1`; they do not get a special singular schema
- multi-target threads use the same fields with `target_count>1`
- `instance_id` remains readable only during migration and should be removed from the thread index
  once `ScopeSummary` backfill is complete

### 3. Memory and indexing consume `ScopeSummary`; runtime logic consumes `TurnScope`

The split is:

- `TurnScope` for routing, prompt construction, target resolution, and tool binding
- `ScopeSummary` for indexing, list/search payloads, and memory asset lookups that need a stable
  summary view

Memory preparation may still derive a concrete asset key from `TurnScope` when a single binding is
present, but thread indexing and other metadata readers should use `ScopeSummary` rather than
reaching into runtime scope internals.

This avoids coupling long-lived metadata surfaces to fields such as `prompt_context`,
`seed_hints`, or mutable binding payload shape.

### 4. Schedule dual-read/write sunset is staged

Schedule compatibility should not be open-ended.

Adopt this staged sunset:

1. Release N:
   add `target_seed_query`, `target_seed_hints`, `resolution_policy`, and `allow_zero_scope`;
   read both old and new fields; write new canonical fields; if a legacy
   `redis_instance_id` is supplied, translate it into `target_seed_hints`
2. Release N+1:
   keep reading `redis_instance_id`, but mark it deprecated in API/CLI help and stop emitting it in
   newly created schedules unless the legacy field was explicitly used
3. Release N+2:
   remove write support for `redis_instance_id`; keep read-only support for stored schedules
4. Cleanup gate:
   remove legacy read support only after stored schedules have been backfilled and one full release
   cycle has passed with no remaining legacy-only schedule records

This gives schedules a bounded migration window while preventing `redis_instance_id` from becoming
an indefinite permanent contract.

### 5. Compatibility adapters are split into permanent seed hints vs removals

Permanent seed-hint adapters:

- user-invoked query surfaces that intentionally allow explicit target pinning
- MCP chat/triage/query entrypoints that accept `instance_id` / `cluster_id`
- CLI query flows that accept explicit target flags

These remain acceptable because they are user-provided seed hints into late discovery, not the
canonical runtime scope model.

Deprecated and removed:

- thread context storage of active runtime `instance_id` / `cluster_id`
- runtime branching that treats singular ids as canonical active scope
- thread index/search metadata keyed by `instance_id`
- schedule storage fields such as `redis_instance_id`
- memory/index/helper code paths that require singular runtime ids instead of `TurnScope` or
  `ScopeSummary`
- any code that promotes a bound singleton target back into singular runtime scope

These are migration shims only and should not survive the late-discovery-first architecture.

## Remaining Questions

No open design questions remain for this migration phase. Any future work should be rollout- or
cleanup-specific, not architectural.

## Deliverable

The migration is complete when:

- the default Redis execution path starts unbound
- scope is represented by `TurnScope`
- one target and many targets use the same binding model
- automated runs can lazy-bind from instructions without interactive clarification
- zero-scope runs remain supported when policy allows them
- thread reload works correctly across turns
- singular ids are no longer the canonical runtime scope model

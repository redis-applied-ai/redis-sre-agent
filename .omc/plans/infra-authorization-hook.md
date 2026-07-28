# Work Plan: Infrastructure Authorization Hook

Status: **pending approval** (consensus — deliberate mode; revised after Architect r1 + Critic r1/r2)
Spec: `.omc/specs/deep-interview-infra-authorization-hook.md`

## Requirements Summary
Add a pluggable, deployment-supplied authorization hook that decides which Redis
clusters and database instances the current principal may access. Called live
every time a target is resolved or listed. This repo owns no principal→target
mapping. Gated by a new `infrastructure_authorization_enabled` flag that (a)
requires `auth_enabled`, (b) requires a configured hook, (c) fails closed.
Identity is the validated JWT claims — never the client-supplied `req.user_id`.

## Design pivot (why not per-entrypoint enforcement)
Two consensus rounds proved that enumerating turn-entry points is whack-a-mole:
the code has ≥4 worker entrypoints that run the agent against a client-supplied
target — `_process_agent_turn_impl` (`docket_tasks.py:1966`), `resume_task_after_approval`
with **two** branches (chat `:2925`, triage `:3039`), `process_chat_turn` (`:1464`,
enqueued from MCP at `mcp_server/server.py:393,523`), and the deep-triage fan-out
child `_run_single_target_triage_child` (`:959`) — plus CLI (`cli/query.py:231`)
and eval (`evaluation/agent_only.py:187`). Guarding each is fragile.

**Root-cause chokepoint:** every path resolves its target through a *small shared
set of resolvers* before executing tools:
- `get_cluster_by_id` (base cluster loader, `core/clusters.py:426`) — every cluster caller routes through it (`:1448, :2342, :2908, :3032`, langgraph `:2859/2868`, ...).
- `get_instance_by_id` (base instance loader, `core/instances.py:822`) — the true instance analog; called DIRECTLY by `process_chat_turn` (`:1442`), the LangGraph `instance_scope_id` branch and `resume_query` (`langgraph_agent.py:1881/2855/2864`), and the `_resolve_instance_for_thread` wrapper itself (`:133`). Guarding the base loader (NOT the wrapper) covers all of them by construction.
- `materialize_bound_target_scope` (bindings; `:628, :2286`).

Enforce inside these resolvers + the listing paths + the catalog. You cannot
obtain a target object without going through a resolver, so all entrypoints are
covered by construction. Identity reaches the resolvers via a **ContextVar** set
once at each trust boundary — no threading `claims` through dozens of signatures
(which is exactly what kept missing sites).

## RALPLAN-DR Summary

### Principles
1. **Fail closed.** Missing prerequisites, no hook, no/expired token, hook error, unresolvable principal → deny.
2. **Single validation path.** All JWT validation stays in `core/auth.py:validate_token`.
3. **Enforce at the resolver chokepoint, not the caller.** A target object cannot exist without passing a guarded resolver; entrypoint enumeration is not a security boundary.
4. **Identity via trust-boundary ContextVar.** Set the principal once where trust is established (API dep, worker-task top); resolvers read it. No per-signature threading.
5. **Additive and off by default.** Byte-for-byte no behavior change when `infrastructure_authorization_enabled=False`.

### Decision Drivers
1. **Security completeness** — no missed execution path; both resume branches + MCP chat covered.
2. **Minimal, non-fragile diff** — one ContextVar + guards in ~3 resolvers + 2 list fns + catalog, vs. edits at ≥8 enqueue sites.
3. **Operational safety** — misconfiguration fails at startup; machine paths don't silently break.

### Viable Options (identity transport)
**Option A — validated JWT claims in a ContextVar, set at each trust boundary (CHOSEN).**
- Pros: cannot miss an execution path (enforced at resolvers); no signature churn; fresh claims for the hook; expiry + spoof rejection via `validate_token`.
- Cons: raw bearer persisted in `thread.context`/task payload on interactive paths (credential at rest); ContextVar must be set at every trust boundary (missing one → fail-closed deny, not a leak — safe failure).

**Option B — thread `claims` explicitly through every call site.**
- Pros: no implicit state; explicit data flow.
- Cons: this is what failed twice — every new call site is a silent-open risk; enormous signature churn across `docket_tasks.py`, `manager.py`, `targets.py`.

**Option C — persist only `sub`; hook does its own lookup.**
- Pros: no token at rest.
- Cons: no fresh claims; hook must resolve everything from subject; still needs a machine-path story. No security gain over A (A avoids token-at-rest on machine paths via service principal).

**Invalidation:** B rejected — proven fragile (Critic r1/r2 each found a missed site). C rejected — hands the hook no claims, contradicting the external-authz framing; no benefit A lacks. Honest correction (Architect antithesis, verified): `validate_token` checks signature/iss/aud/exp only, **not revocation** (`api/auth.py:161` logout note: JWT valid until TTL, no denylist). Revocation is achieved by the **per-turn hook call against its live grant store**, equally under A/B/C — not by token re-validation.

### Pre-mortem (3 failure scenarios)
1. **A resolver path we didn't guard.** A target reaches the agent without passing a guarded resolver (e.g. session-staged ad-hoc instances built via `RedisInstance(**data)` at `docket_tasks.py:195`, or a future new resolver). → Mitigation: guard all three resolvers; a test enumerates `get_cluster_by_id`/instance-resolver/`materialize_bound_target_scope` callers; session-staged ad-hoc connections declared a **non-goal** (not infra-registered targets) or separately gated; add a "deny by default in the resolver" so an unguarded *new* caller of a guarded resolver still fails closed.
2. **ContextVar not set on a trust boundary.** A worker task or API request runs without setting the principal → resolvers see no principal. → Mitigation: set it at the top of every `@sre_task` that runs the agent and in the `require_auth` dependency; unset/None principal with authz on → deny (fail-closed, safe); test asserts each worker task sets it.
3. **Token-at-rest leak / hook exception storm.** Bearer in `thread.context`/Redis logged or replayed; slow/throwing hook blocks or errors every resolve. → Mitigation: single scrubbed key, never logged, short TTL, encrypt-at-rest option; hook wrapped in try/except + bounded timeout → fail closed; results memoized per-principal within a single turn to avoid N calls; allow/deny/error counters.

## Acceptance Criteria
Spec AC-1..AC-15, all testable. Key points:
- AC-1 off → passthrough. AC-2/AC-3 startup errors. AC-4 import-path hook.
- AC-5 REST `query_clusters`/`query_instances` AND catalog/agent-tools return only allowed subset.
- AC-6/AC-6b bound target AND client `instance_id`/`cluster_id` target denied → no tools execute.
- AC-7 deep-triage (both the normal triage and the resume triage branch `:3039`) same denial.
- AC-8 revoke-after-login → next turn denied (hook store, per-turn call).
- AC-9 hook empty for principal (e.g. `system` no grant) → empty.
- AC-10 clusters and instances identical.
- AC-11 missing/expired/invalid bearer → fail closed; spoofed `req.user_id` alone → nothing.
- AC-12 approval-resume (both `:2925` and `:3039` branches) enforces before re-running the gated tool.

## Implementation Steps

### 1. Config flags + cross-field validation — `core/config.py`
Add `infrastructure_authorization_enabled: bool = False` and `infrastructure_authorization_hook: Optional[str] = None`. Add `model_validator` to the pydantic import (currently only `field_validator`, `config.py:9`) and a `@model_validator(mode="after")`: authz⇒`auth_enabled`, authz⇒hook configured, else `ValueError` (AC-2, AC-3). Additive; fires only when flag on.

### 2. Authorization module — new `core/authorization.py`
- **Pinned hook contract:** `TargetRef` (frozen dataclass: `kind`, `resource_id`, `name`, `environment`). `ScopeHook = Callable[[dict, list[TargetRef]], list[TargetRef] | Awaitable[list[TargetRef]]]` returns the allowed subset. This is the ONE contract deployments write against; adapters convert native objects ↔ `TargetRef`.
- `_load_hook()`: import + cache callable from settings; clear error if unimportable.
- Principal ContextVar: `_principal: ContextVar[Optional[dict]]`; `set_principal(claims)`, `current_principal()`, `system_principal()` (fixed claims dict for machine paths).
- `async def scope_targets(targets: list[TargetRef]) -> list[TargetRef]`: authz off → passthrough (AC-1); `current_principal()` falsy → `[]` (AC-11); else call hook (await if coroutine) in try/except + bounded timeout → error/timeout → log (no token) + `[]` (fail closed). Memoize per (principal, turn).
- `async def assert_target_allowed(ref: TargetRef) -> bool`: `bool(await scope_targets([ref]))`.
- allow/deny/error counters.

### 3. Set the principal at every trust boundary (Principle 4)
- **API:** in `require_auth` (`api/auth.py:37`) after `validate_token`, `set_principal(claims)`. Also persist the bare bearer (strip `Bearer ` per `api/auth.py:54`, M3) into the turn `context`/`thread.context` at enqueue for later worker turns; **refresh it on every `create_task` turn** so multi-turn threads don't carry a stale token (Critic M-a).
- **Worker:** at the top of each agent-running `@sre_task` — `process_agent_turn`/`_process_agent_turn_impl`, `resume_task_after_approval`, `process_chat_turn`, and the fan-out child — resolve the principal: bare bearer in context/`thread.context` → `await validate_token(bearer)` → `set_principal(claims)` (fail closed on `AuthError`/`DiscoveryError`); no bearer (continuation/eval) → `set_principal(system_principal())` / stub. One helper called once per task. (Scheduler tasks are disabled under authz, not run as machine paths — step 6; MCP is out of scope and fails closed — no principal set.)
- This single mechanism covers both resume branches (`:2925`, `:3039`) and `process_chat_turn` without per-branch code (closes Critic C1, C2, M-a).
- **M-2 — reset in `finally`.** Capture the `set_principal` token and `_principal.reset(token)` in a `finally` at each task top, so the None-default fail-closed guarantee does not depend on whether docket allocates a fresh `contextvars.Context` per task (cross-task reuse without reset could otherwise leak a prior task's principal — an over-permit, not a safe deny). Cheap; mandatory.

### 4. Enforce inside the base target loaders (Principle 3 — the chokepoint)
Guard the two BASE loaders at their definitions (not wrappers) + the binding materializer:
- `get_cluster_by_id` (`core/clusters.py:426`): after loading, `assert_target_allowed(TargetRef.from_cluster(c))`; deny → return None (fail closed — callers already treat None as not-found).
- `get_instance_by_id` (`core/instances.py:822`): same guard via `TargetRef.from_instance`. This is the fix for Critic C-1 — guarding the wrapper `_resolve_instance_for_thread` would leave `process_chat_turn`/resume instance paths open.
- `materialize_bound_target_scope` (`:628/:2286`): filter materialized bindings through `scope_targets`; drop denied bindings (covers the fan-out child `:959`).
- **Two enforcement modes by intent (AC-6c):**
  - *Implicit/internal resolution* → base loader returns `None` (existing not-found path; silent, fail-closed).
  - *Explicit reference* — where the client supplies `instance_id`/`cluster_id` (`docket_tasks.py:2030`, `process_chat_turn:1442`) or the user names a target: add an **explicit-attach guard** that RAISES `AuthorizationDenied` and halts the turn (AC-6/6b). Do NOT resolve-to-None-and-continue. The denial response is IDENTICAL for exists-but-denied and does-not-exist ("not authorized to access the requested target") so it is not an enumeration oracle.
- **Deep triage MUST report scoped-out targets (AC-7b) — never silent.** Reuse the existing pre-triage checkpoint (`resolve_target_query`, `docket_tasks.py:2259`) and existing message channels:
  1. Resolve against the **UNSCOPED** catalog for detection — NIT-1: wire this explicitly to the M-1 internal-read bypass (an `apply_scope=False` kwarg plumbed `resolve_target_query`→`DiscoveryRequest`→backend→`get_target_catalog`), NOT a `system_principal()` swap (step-2 still calls the hook for `system` and AC-9 lets it return empty). Then partition resolved targets allowed/denied via the hook. **Only name a denied target when the match is HIGH-confidence / exact** (`PublicTargetMatch.confidence`); a low-confidence fuzzy hit on a denied target → treat as no-match, do NOT confirm (bounds the enumeration oracle — decided).
  2. **Some denied** → emit an interim message ("Not authorized for X, Y — triaging Z") via `task_manager.add_task_update` + `_publish_stream_update` (same pattern as the existing "Resolved target scope" `:2299` / "Starting fan-out" `:1110` updates), THEN materialize bindings for the allowed subset and fan out.
  3. **All resolved targets denied** → reply-and-stop. NIT-2: reuse the stop-*plumbing* of `_complete_deep_triage_target_limit_response` (`:2266` — append message → `_complete_task_if_open` → `turn_complete` → return), but with an **unauthorized-reason formatter**, NOT its hardcoded "too many matches / narrow the request" message (`:761,842`) which would mislead a denied user.
  - Confirmed feasible with current architecture: resolution already runs before triage, and reply-first/reply-and-stop are existing patterns. Cost: an unscoped-resolve pass for detection, and reporting confirms existence of a user-named denied target (accepted — a truthful partial-scope note beats a silently-misleading full-looking report). Security still enforced by the `materialize_bound_target_scope` fail-closed drop regardless of the report.
- **M-1 — audit non-agent callers of the base loaders.** Guarding the base loaders also fires for non-agent callers: `core/instance_mutation_helpers.py:42`, `core/cluster_helpers.py:60`, `core/query_helpers.py:78/83`, `api/instances.py:158`, `api/clusters.py:329`, `cli/instance.py:97/655`, `cli/cluster.py:96`, `mcp_server/server.py:257/267`, `targets/redis_binding.py:84/136/143/157/183`. Before implementing: confirm each runs under a set principal (`require_auth` or `system_principal()`), OR add an explicit internal-read bypass sentinel for genuine reconciliation/health reads. A caller reached with no principal under authz-on returns None (safe deny, but breaks that feature) — this is availability, not a leak.
- Deny returns None, which surfaces as "not found" (`docket_tasks.py:1443/1449`). Fail-closed and acceptable; note the misleading message, don't fix unless product wants a distinct "denied" signal.

### 5. Enforce at the listing surfaces — users never SEE inaccessible targets (AC-5)
- **Filter BEFORE count + paginate (critical).** `query_clusters`/`query_instances` count and page server-side (`CountQuery` at `core/clusters.py:248`; `fq.paging(offset, limit)` at `:265` — same shape in `instances.py`). Post-filtering the returned page would (a) leak the true `total` (hidden-target count) and (b) return short/broken pages. When authz is on: fetch the filter-matched set (bounded by the existing `num_results` cap — inventories are small), run `scope_targets` via `TargetRef` adapters, THEN compute `total` and apply `offset`/`limit` in Python. Authz off → keep the existing server-side count/paging path byte-for-byte (Driver 2). Add `Request` to `list_clusters`/`list_instances` (set principal) and to the MCP instance-list path (`mcp_server/server.py:2750` → `query_instances`, service or user principal).
- **Direct get-by-id = 404, never 403.** The base-loader guard (step 4) returns `None` on deny → surfaces as "not found", indistinguishable from non-existent. Do NOT introduce a 403 that would confirm a hidden target's existence.
- Catalog path (agent tools): apply `scope_targets` in `get_target_catalog`/`list_known_targets` (`core/targets.py:918/1033`) after the existing `user_id` filter (its `total`/`has_more` are already computed post-filter — keep that). In-run discovery tools (`tools/target_discovery/provider.py`, `targets/redis_catalog.py:57`) inherit the ContextVar — no signature change (Principle 4 dividend; closes Architect Finding 5).
- **Phase-2 audit (out of scope this hook, flagged):** indirect enumeration that names a target — schedule lists (`api/schedules.py`), thread lists (`api/threads.py`), task lists — can leak an inaccessible target's id/name even though the target APIs are scoped. Note as follow-up; do not silently assume covered.
- `gitnexus_impact` on `get_cluster_by_id`, `get_instance_by_id`, `query_clusters`, `query_instances`, `get_target_catalog` before editing (hot paths).

### 6. Machine-path & non-goal declarations
- Continuation (`core/threads.py:884`), eval (`evaluation/runtime.py:83`, `agent_only.py:187`) → principal set at task top (step 3); eval → test-harness stub principal. (Scheduler is NOT a machine-path here — it is disabled under authz, see below.)
- **MCP is OUT OF SCOPE for authn/authz this phase** — MCP has no authenticated principal today. Consequence to make explicit: with `infrastructure_authorization_enabled` ON, MCP target ops (`mcp_server/server.py:393/523/2750`) hit the guarded base loaders with **no principal → fail closed → MCP sees nothing.** Do NOT paper over this with a blanket service principal. "MCP authn/authz" is separate future work; document the fail-closed behavior so operators know enabling authz gates MCP target access.
- **Scheduler (decided): schedules are DISABLED when authz is enabled — feature unavailable this phase.** Properly scoping a cron run to the creator's *current* access requires acquiring a fresh creator token at run time (token-exchange/OBO or a stored refresh token) — too much to solve now. Instead, when `infrastructure_authorization_enabled` is on:
  - **Block creation** (the real create surfaces): `create_schedule` (`api/schedules.py:57`, `POST /`) and CLI `schedules_create` (`cli/schedules.py:222`) return a clear error ("scheduling is unavailable when infrastructure authorization is enabled"). Also guard `update_schedule` (`api/schedules.py:125`).
  - **No-op ALL execution paths** (Critic C1 — three distinct entrypoints enqueue `process_agent_turn`, not just cron):
    1. `scheduler_task` cron loop (`docket_tasks.py:1787` / enqueue `:1891`);
    2. `trigger_schedule_now` manual-run API (`api/schedules.py:308`, `POST /{id}/trigger`) — guard BEFORE the `docket.add(process_agent_turn)` at `:356`;
    3. CLI `schedules_run_now` (`cli/schedules.py:491`) — guard before the enqueue at `:546`.
    (`trigger_scheduler` at `api/schedules.py:394` enqueues `scheduler_task`, so it is covered by #1.) A deployment that had schedules before flipping the flag must NOT fire them unscoped via ANY of these — that is the exact bypass this feature prevents. Use one shared `_schedules_disabled()` guard at each surface; log the skip.
  - **authz OFF → unchanged:** schedules create and run exactly as today.
  - Follow-up (future phase): re-enable via creator-scoped token-exchange/OBO (`auth_api_client_id`/secret + persisted `sub`), validating + hook-checking each run.
- **Non-goal:** session-staged ad-hoc instances (user-pasted connection details, `RedisInstance(**data)` at `:195`) are not infra-registered targets; out of scope this phase (documented), OR gate separately if required.

### 7. UI — hide Schedules when authz is enabled
Match the backend disablement (step 6) so the UI never offers a dead feature.
- **Signal:** add `infrastructure_authorization_enabled` to `auth_status()` (`core/auth.py:140`) — surfaces automatically via `/health.auth` (`api/health.py:106`), which the UI already fetches (`ui/src/services/sreAgentApi.ts:1138`). Bearer-exempt endpoint, so available pre-login.
- **Nav:** in `useApp.ts` (`navigationItems`), omit the Schedules item when the flag is true.
- **Route:** in `App.tsx:62`, guard `/schedules` — render a clear "Scheduling is unavailable while infrastructure authorization is enabled" notice (preferred over a silent redirect, so a bookmarked link is explained).
- Gate on the **authz** flag, not authn: an authn-only deployment keeps schedules.
- Note: UI dep/build changes need `--renew-anon-volumes` (stale node_modules anon volume) when validating locally.

### 8. Tests — see Expanded Test Plan.

## Expanded Test Plan

**TDD ordering (security boundary → deny paths are the spec):** write these FIRST, before the feature, and watch them fail: (1) the structural enforcement guard, (2) the fail-closed unit cases, (3) the explicit-deny / no-oracle cases. Implement until green. Only then the passthrough/allowed-path tests.

### Structural enforcement guard (THE highest-value test — defends the invariant, not examples)
- **No unguarded target materialization** (AST / import-graph test): assert `RedisInstance` and `RedisCluster` are constructed ONLY inside the guarded base loaders (`get_instance_by_id`, `get_cluster_by_id`, `materialize_bound_target_scope`) or an explicit allowlist. A NEW resolver/bypass path added later fails this test the day it lands — this is what converts "enforced at the paths we knew" into "you cannot add an unguarded path" (the class of miss that took 3 review rounds). Not a "these 3 functions call the hook" check — that inherits the same enumeration blind spot.

### Unit (`tests/unit/core/test_authorization.py`)
- passthrough off (AC-1); fail-closed on no principal (AC-11); fail-closed on hook exception/timeout; sync + async hook; import-path resolution; `assert_target_allowed` T/F; `TargetRef` adapters (3 shapes: cluster/instance/catalog); per-turn memoization; config validator authz⇒authn / authz⇒hook (AC-2, AC-3).
- **Hook returns a superset** (gap #2): a hook that returns a `TargetRef` NOT in the input set → `scope_targets` **intersects** (a bad/hostile hook cannot ADD access). Design invariant + test.
- **Implicit-deny returns None, does NOT raise** (gap #5): the base loader returns `None` on deny (the graceful not-found path for internal callers) — distinct from the explicit-attach hard-deny. Pins the M-1 boundary so an implementer doesn't make the loader raise and break internal callers.
- ContextVar set/get/**reset-in-finally isolation** — a task that sets no principal sees None, not a bleed from a prior task (M-2). (Cross-task reality is covered by an integration test — see below.)

### Integration (`tests/integration/test_authorization_enforcement.py`) — stub hook allowing a subset
- REST `list_clusters`/`list_instances` return only allowed (AC-5); **`total`/`has_more` reflect only accessible targets, paging returns full pages across the allowed set** (AC-5b — count/paginate-after-scope, no hidden-count leak); direct get-by-id on inaccessible → 404 not 403.
- normal turn, disallowed **bound** target → denied, no tools (AC-6); disallowed client `context["instance_id"]`, no binding → denied (AC-6b).
- **`process_chat_turn` (MCP chat) disallowed target → denied** (Critic C1).
- **resume chat (`:2925`) AND resume triage (`:3039`): approve gated tool, revoke, resume → denied, tool does NOT execute** (AC-7/AC-8/AC-12, Critic C2).
- explicit-attach deny: client `instance_id` not allowed → `AuthorizationDenied`, halts, no tools; nonexistent id returns the SAME message (no oracle).
- deep triage report (AC-7b): some denied → interim message names the unauthorized targets + scoped subset before fan-out (assert `add_task_update`/stream fires; fan-out covers only allowed); all denied → reply-and-stop with an unauthorized-reason message (NOT "too many matches"); NO high-confidence resolved target silently dropped; **confidence gate — a low-confidence fuzzy match on a denied target is NOT named/confirmed, a high-confidence/exact one IS** (enumeration-oracle bound).
- deep-triage fan-out drops denied bindings (`:959`); clusters and instances identical (AC-10); in-run `resolve_redis_targets` returns only allowed, cannot attach a denied target.
- **ContextVar cross-task bleed (gap #1) — REAL worker, not unit:** run turn A (user X, allowed) then turn B (no principal / user Y) through the actual docket task path; assert B does NOT inherit X's principal (proves the safety claim independent of docket's context reuse). Plus one **concurrency** test: two overlapping turns, different principals, each sees only its own subset.
- **Full-path token test w/ mock JWKS (gap #3):** signed test JWT → `require_auth` → strip `Bearer ` → persist → **worker re-validate** → hook → scoped result. Exercises the plumbing that already had two bugs (prefix, missing `Request`). Reuse the SSO harness (`tests/unit/core/test_auth_validator.py`, `test_auth_portability.py`).
- **M-1 internal caller still works (gap #4):** a representative non-agent base-loader caller (reconciliation/health/mutation) functions under authz via `system_principal()` or the internal-read bypass — guards against an availability regression.

### Schedules disabled under authz (AC-14)
authz-on → `create_schedule`/CLI-create refused; ALL THREE execution paths enqueue nothing — `scheduler_task` cron, `trigger_schedule_now` (`POST /{id}/trigger`), CLI `schedules_run_now` (assert no `process_agent_turn` enqueued for a pre-existing schedule on each); authz-off → create/trigger/run as today.

### UI (AC-15)
`/health.auth` exposes the authz flag; component test — flag true → Schedules nav omitted and `/schedules` renders the unavailable notice; flag false / authn-only → Schedules present.

### e2e
authz-on boot passes startup with hook+authn; a chat turn denies a hook-rejected target; spoofed `req.user_id` + no bearer → nothing (AC-11).

### Observability
allow/deny/error counters increment; scrub test asserts the bearer never appears in logs (extend: nor in surfaced error messages).

### Evals (`make test-eval-pr` gate — this feature touches routing/triage)
Evals route through the SAME `_process_agent_turn_impl` chokepoint (`evaluation/runtime.py:78-83`), so authz interacts with them two ways:
- **Harness principal injection (required, else authz-on evals fail-closed):** when an eval scenario enables authz, the harness sets a stub principal (via `runtime_overrides.py` / the `_default_turn_processor` path) before invoking. Default authz-OFF → eval suite runs byte-for-byte as today (no regression). Add an authz-ON eval mode.
- **New DETERMINISTIC behavioral evals** (judge response quality — where evals beat string asserts), added to the target-discovery suite (`evals/suites/pr-target-discovery-live.yaml` or a new `authz-scoping` suite) with a stub hook + fake targets so they run in the PR subset:
  - prompt naming allowed + denied targets → judge the response REPORTS the denied ones and triages the rest (AC-7b behavioral outcome);
  - explicit denied target → judge the agent says "not authorized" and does NOT fabricate/hallucinate state about a target it cannot see;
  - "all prod" general reference over a mixed set → judge it scopes and reports the exclusion.
- **No-regression:** run the existing deterministic eval suite authz-off in PR CI (`make test-eval-pr`) — behavior unchanged.
- **Out of evals (kept in unit/integration):** enforcement mechanics (loader returns None, count-before-paginate, ContextVar bleed, structural guard). Evals judge agent-response quality, not enforcement correctness — no duplication.

## Risks and Mitigations
| Risk | Mitigation |
|------|-----------|
| A target reaches the agent bypassing a guarded resolver | Guard all 3 resolvers + resolver-level fail-closed; caller-enumeration test; session-staged ad-hoc = non-goal |
| ContextVar unset on some trust boundary | Set at every `@sre_task` top + `require_auth`; unset+authz-on → deny (safe); per-task test |
| Authz-on breaks continuation/eval | `system_principal()`/stub at those task tops (scheduler is disabled, not run as a machine path; MCP is out of scope, fail-closed) |
| Bearer credential at rest in thread.context/Redis | Single scrubbed key; no logging; short TTL; refresh per turn; encrypt-at-rest option |
| Overstating revocation | Revocation is hook-store-driven per turn (documented); token re-validation = expiry only |
| Hot-path regression on resolvers/list/catalog | Optional/defaulted params + authz-off passthrough; `gitnexus_impact` before edit |
| Hook slowness/exceptions | try/except + timeout → fail closed; per-turn memoization; counters |
| Resume bearer expired during a long approval wait | `validate_token` fails → deny → approved tool won't re-run (fail-closed, correct); document the approval-resume UX expectation (client re-submits) |
| Guarding base loaders wrong-denies internal/admin callers | M-1 caller audit: ensure every `get_*_by_id` caller runs under a principal or a documented internal-read bypass |

## Verification Steps
1. `make test` (unit + integration green) — TDD: structural guard + fail-closed + explicit-deny tests written and failing FIRST, then implemented to green.
1b. `make test-eval-pr` (deterministic eval subset) green — no regression authz-off, plus the new authz-on behavioral evals (AC-7b report, no-hallucination-on-denied). Required gate for routing/triage changes.
2. Boot authz-on + no hook → clear config error; authz-on + authn-off → clear config error.
3. Boot configured w/ stub hook → REST lists, a normal chat turn, and an approve→revoke→resume all honor the stub; schedule create/trigger/CLI-run are all refused and the cron loop fires nothing (AC-14); logs contain no bearer.
4. `ruff check`.

## ADR
- **Decision:** Pluggable, config-registered authorization hook (`TargetRef` contract) keyed off validated JWT claims carried in a trust-boundary ContextVar; enforced inside the shared target resolvers (`get_cluster_by_id`, instance resolver, `materialize_bound_target_scope`), the REST list paths, and the catalog; machine paths use a service principal; fail-closed behind an off-by-default flag requiring authn + a configured hook.
- **Drivers:** security completeness (no missed execution path, both resume branches + MCP chat), minimal non-fragile diff, fail-fast on misconfiguration. (Scheduler and MCP are explicitly deferred — disabled and fail-closed respectively — rather than partially covered.)
- **Alternatives considered:** (B) explicit `claims` threading — rejected, proven fragile (two review rounds each found a missed site); (C) persist `sub` — rejected, no fresh claims, no security gain.
- **Why chosen:** Enforcing at resolvers via a ContextVar is the only approach that cannot silently miss an execution entrypoint, while giving the hook fresh claims and keeping the diff small.
- **Consequences:** bearer persisted in thread.context/task payload (accepted, mitigated); ContextVar must be set at every worker-task top (missing → safe fail-closed deny); session-staged ad-hoc instances explicitly out of scope; resolvers gain an authz dependency.
- **Follow-ups:** encrypt-at-rest for task payloads; gate session-staged ad-hoc instances if needed; token denylist if sub-TTL revocation latency proves unacceptable.

## Changelog
**Architect r1:** REST source-path enforcement; worker client-id target; bearer plumbing (Request+header); enumerated machine enqueue sites; claims into discovery; corrected overstated live-revocation claim.
**Critic r1:** added resume path; pinned `TargetRef`; fixed bearer prefix.
**Critic r2:** pivoted from fragile per-entrypoint enforcement to resolver-chokepoint + trust-boundary ContextVar — closes C1 (`process_chat_turn`/MCP), C2 (resume triage branch `:3039`), M-a (resume identity source: persist+refresh bearer in thread.context, principal set at task top), M-b (spec reconciled to `TargetRef`).
**Test plan (user, TDD):** strengthened caller-guard → structural "no unguarded target materialization" AST test; added hook-superset intersection, implicit-deny-returns-None, real-worker ContextVar cross-task + concurrency, full-path mock-JWKS token, M-1 internal-caller tests; TDD ordering (deny/structural tests first); added Evals subsection — harness principal injection for authz-on, deterministic AC-7b behavioral evals in `make test-eval-pr`, no-regression authz-off, enforcement mechanics stay in unit/integration.
**Critic r6 (AC-7b pass): APPROVE-WITH-NITS.** Mechanism verified real/located; scoped-vs-unscoped resolved via the M-1 `apply_scope=False` bypass (NIT-1); reuse only the stop-plumbing of the limit-response, not its "too many matches" text (NIT-2). Both wired into step 4 / AC-7b. OPEN QUESTION for the user: AC-7b names denied NL-matched targets against the UNSCOPED registry → fuzzy name-guessing can enumerate the registry, an oracle AC-6 deliberately closes for opaque ids. Recommended mitigation: report only HIGH-confidence/exact-name denied matches (treat low-confidence fuzzy hits as "no match", don't confirm) — preserves the "you named X → told unauthorized" UX without turning fuzzing into an enumerator. DECIDED (user): report only high-confidence/exact-name denied matches; low-confidence fuzzy hits are treated as no-match and never confirmed.
**User review 4:** AC-7b strengthened — deep triage MUST report scoped-out targets (interim message + continue, or reply-and-stop if all denied); never silently drop a resolved target. Confirmed feasible: reuses the existing pre-triage resolution checkpoint + `add_task_update`/`_complete_deep_triage_target_limit_response` patterns; requires an unscoped-resolve detection pass.
**Critic r5 (confirming pass): APPROVE-WITH-NITS.** C1/M1/M2 verified closed against code; enqueue sweep found no unlisted schedule execution site. Two stale doc lines fixed (spec service-principal line dropped scheduler/MCP; AC range corrected to AC-1..AC-15). Consensus reached.
**Critic r4:** fixed C1 (schedule disablement missed the manual-trigger API `:308/:356` and CLI-run `:491/:546` paths, and mislabeled run surfaces as create — now blocks real create `:57`/CLI `:222` and no-ops all three execution paths); M1 (AC-7b made implementable — client-id reliable signal + unscoped-resolve+confidence heuristic for NL, or simplify to client-id-only); M2 (purged stale scheduler-service-principal text from step 3, step 6, Risks, Verification step 3, ADR).
**User review 3:** simplified — schedules DISABLED when authz on (block creation + skip existing runs so nothing fires unscoped); creator-scoped scheduling deferred to a future phase (AC-14). UI hides the Schedules page/nav when authz on via a `/health.auth` flag (AC-15).
**User review 2:** confirmed model (system sees full registry, hook filters per user, AC-13).
**User review 1:** explicit client-supplied/named targets hard-deny (not silent None), with identical response for denied/nonexistent (no oracle); deep triage validates named targets before running and reports unauthorized ones, general globs scope silently; MCP declared out-of-scope/fail-closed (no authn today); scheduler identity called out as an open decision.
**Critic r3:** fixed the instance chokepoint from the bypassed wrapper `_resolve_instance_for_thread` to the base loader `get_instance_by_id` (`instances.py:822`) — closes C-1 (instance silent-open on `process_chat_turn`/resume); added M-1 base-loader caller audit, M-2 ContextVar reset-in-finally, `get_instance_by_id` caller-enumeration test, and resume-bearer-expiry risk note. Critic pre-committed this flips to APPROVE-WITH-NITS.

# Deep Interview Spec: Infrastructure Authorization Hook

## Metadata
- Rounds: 4
- Final Ambiguity Score: 13%
- Type: brownfield
- Threshold: 20%
- Status: PASSED

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.92 | 0.35 | 0.322 |
| Constraint Clarity | 0.85 | 0.25 | 0.213 |
| Success Criteria | 0.80 | 0.25 | 0.200 |
| Context Clarity | 0.88 | 0.15 | 0.132 |
| **Total Clarity** | | | **0.867** |
| **Ambiguity** | | | **0.133** |

## Topology
| Component | Status | Description | Coverage |
|-----------|--------|-------------|----------|
| Hook contract + enforcement flag | active | Pluggable `scope` callable + `infrastructure_authorization_enabled` flag, required & fail-closed when on | AC-1..AC-4, AC-9 |
| Enforcement points | active | Filter at list, and validate at chat/deep-triage agent invocation with attached target(s); covers clusters + instances | AC-5..AC-8 |
| Identity provenance | active | Resolved: the validated JWT bearer travels in the turn `context` and is re-validated per turn via `validate_token`; hook keys off claims, NOT `req.user_id` | AC-6, AC-7, AC-11 |

## Goal
Add a single pluggable authorization hook that the deployment supplies. When
`infrastructure_authorization_enabled` is on, the agent calls this hook to
determine which clusters and database instances the current principal may
access, **every time that information is needed**: listing instances, listing
clusters, and at invocation of the chat and deep-triage agents when a target is
attached. This repo does **not** own the principal→target mapping — the hook
delegates to whatever authz system does. Authorization is live (re-checked at
agent-run time) so revocation between login and chat takes effect on the next
turn.

## Constraints
- Authorization is separate from authentication: two flags. `infrastructure_authorization_enabled` **requires** `auth_enabled` (validated at startup, fail-closed — mirrors `core/auth.py` `AuthConfigError` pattern).
- When enabled, a hook **must** be configured; enabled-without-hook fails closed at startup.
- The hook is keyed by the **validated JWT claims**, not `user_id`. `api/tasks.py:137` sets `user_id` from the client-supplied `req.user_id` (spoofable) — it MUST NOT be an authz input. The raw bearer travels in the turn `context` to `process_agent_turn` (`core/docket_tasks.py:3180`) and is re-validated per turn via `core/auth.py:validate_token`. Re-validation enforces **expiry and rejects spoofing** — it does NOT catch pre-TTL revocation (`api/auth.py:161`: JWTs stay valid until TTL, no denylist). **Live revocation comes from calling the hook every turn against its own grant store**, not from the token. On missing/expired/invalid token → fail closed (deny). `user_id` remains only a display/ownership tag.
- **Non-interactive enqueue paths carry no user bearer** (thread continuation, evals). These use an explicit **service principal** (a claims dict the hook recognizes, e.g. the `"system"` grant of AC-9), NOT a raw bearer. Fail-closed still holds if the deployment grants that principal nothing. NOTE: scheduler is DISABLED under authz (AC-14, not a service-principal path) and MCP is out of scope / fail-closed (no authn today) — neither is a service-principal path.
- Tradeoff (accepted): the bearer is persisted in the docket/Redis task payload (credential at rest). Mitigations: short-lived tokens, never log them, encrypt-at-rest if the threat model requires it.
- Applies uniformly across the surfaces SSO already covers (UI, API, CLI) and into the worker where chat/deep-triage agents actually run.
- Enforcement point is the same boundary where `require_auth` already validates (`api/auth.py:37`, `api/websockets.py:45`); reuse the unified catalog path `get_target_catalog()` / `list_known_targets()` (`core/targets.py:918`).
- Clusters and instances are both covered via the unified `TargetCatalogDoc` (`core/targets.py:112`); no per-type special-casing.
- Fail-closed default: authz enabled + no resolvable principal → empty allowed set (deny).

## Non-Goals
- NOT building the principal→target decision logic — it is external and pluggable.
- NOT adding owner/tenant/group fields to `RedisInstance` / `RedisCluster`.
- NOT changing authentication (SSO/authn) behavior.
- NOT per-operation/command RBAC — access is target-level allow/deny, not per-tool.
- NOT caching the approved set at entry (would go stale; live re-check is required).
- NOT supporting scheduled flows under authz this phase — scheduling is disabled when authz is enabled (see AC-14); creator-scoped scheduling is deferred to a future phase.
- NOT covering MCP authn/authz — MCP has no authenticated principal today, so with authz on its target ops fail closed.

## Acceptance Criteria
- [ ] AC-1: authz disabled → catalog/list/agent behavior unchanged (passthrough).
- [ ] AC-2: `infrastructure_authorization_enabled=True` + `auth_enabled=False` → startup error.
- [ ] AC-3: authz enabled + no hook configured → startup error (fail closed).
- [ ] AC-4: hook is resolved from config via an import path / entry-point (following the `TargetIntegrationComponentConfig` pattern in `core/config.py`).
- [ ] AC-5: authz enabled → the REST list endpoints (`query_clusters`/`query_instances`, the surface a user hits), the MCP instance-list path, AND `list_known_targets()`/`get_target_catalog()` (agent tools) return only the hook-allowed subset. Enforcement covers the source-record path, not only the catalog projection.
- [ ] AC-5b: the user never SEES inaccessible targets — scope is applied BEFORE count and pagination, so `total`/`has_more` reflect only accessible targets (no hidden-count leak) and pages are not short/broken. Direct get-by-id on an inaccessible target returns 404 (not 403 — existence must not be confirmed).
- [ ] AC-6: authz enabled → chat agent with an **explicitly attached** target (client `instance_id`/`cluster_id`) not in the allowed set → **hard authorization-denied, turn halts**, no tools execute. NOT a silent resolve-to-None-and-continue. To avoid an enumeration oracle, "exists-but-denied" and "does-not-exist" return the SAME "not authorized to access the requested target" response.
- [ ] AC-7: authz enabled → deep-triage agent, same explicit-deny behavior; token re-validated via `validate_token`, then hook called with the resulting claims.
- [ ] AC-7b: deep triage MUST report which resolved targets are unauthorized before/while proceeding — never silently drop a target the user's query resolved to (a silent partial report is misleading). Mechanism reuses the existing pre-triage resolution checkpoint (`resolve_target_query`, `docket_tasks.py:2259`) and the existing message channels:
  - Resolve against the **UNSCOPED** catalog for detection via an explicit `apply_scope=False` bypass (M-1 internal-read path), NOT a `system_principal()` swap — denied targets are hidden under step-5 scoping, so they must be resolved unscoped to be reportable.
  - **Only HIGH-confidence / exact-name denied matches are named** (to bound the enumeration oracle — see below). A denied target is reported by name only when the NL match is high-confidence or an exact `resource_id`/name match (`PublicTargetMatch.confidence`); a low-confidence fuzzy hit against a denied target is treated as **no match** and NOT confirmed — the user learns nothing about its existence. This preserves the "you named X specifically → told unauthorized" UX without letting vague name-guessing enumerate the registry.
  - **Some denied** → emit an interim message naming the unauthorized targets and the scoped subset ("Not authorized for X, Y — triaging Z"), via `task_manager.add_task_update` + `_publish_stream_update` (same pattern as the existing "Resolved target scope" / "Starting fan-out" updates), THEN fan out over the allowed subset.
  - **All resolved targets denied** → reply-and-stop with the list, reusing the stop-*plumbing* of `_complete_deep_triage_target_limit_response` (`docket_tasks.py:2266`) with an unauthorized-reason message — NOT its "too many matches / narrow the request" text.
  - Reporting a HIGH-confidence/exact-name denied target confirms its existence — accepted and bounded: the user demonstrably knew the near-exact name, so this is not a fuzzing enumerator. Low-confidence fuzzy matches are never confirmed. (Enumeration-oracle decision: report only high-confidence/exact matches.)
  - Security is preserved regardless via the `materialize_bound_target_scope` fail-closed drop; AC-7b governs the report/halt UX so the user is never misled into thinking a partial report is complete.
- [ ] AC-8: revoking access after login → next chat turn against that instance is denied. Mechanism: the hook is called every turn against its live grant store (NOT token re-validation, which only catches TTL expiry).
- [ ] AC-6b: the explicit-attach deny covers the **resolved active target** (the `instance_id`/`cluster_id` from `context`, `docket_tasks.py:2030`), not only parsed target bindings — a turn with a client-supplied disallowed `instance_id` and no binding must still hard-deny.
- [ ] AC-6c: two enforcement modes by intent — enumeration/general reference → silent filter to allowed subset; explicit reference (client id or user-named target) → hard authorization-denied. Same hook/allowed-set, different response.
- [ ] AC-9: authz enabled + no resolvable principal (hook returns empty for the claims, e.g. internal `"system"` with no grant) → empty allowed set.
- [ ] AC-10: hook applies to both clusters and instances identically.
- [ ] AC-11: authz enabled + turn arrives with missing/expired/invalid bearer → fail closed (deny), NOT a fallback to `req.user_id`. A spoofed `req.user_id` with no valid bearer gets nothing.
- [ ] AC-12: the approval-resume path (`resume_task_after_approval`, `core/docket_tasks.py:2777`) enforces before re-running the gated tool — approve a tool, revoke access during the wait, resume → denied, tool does not execute.
- [ ] AC-13: system-level operations see the full registry; only user-driven resolve/list is scoped to the hook subset. (Registry unchanged; authz is a per-user filter.)
- [ ] AC-14: scheduling is DISABLED when authz is enabled (feature unavailable this phase). Create surfaces (`api/schedules.py`, `cli/schedules.py`) return a clear error; the scheduler execution path no-ops/skips existing schedules so pre-existing ones do NOT fire unscoped. Authz off → schedules create and run as today. (Future phase: re-enable via creator-scoped token-exchange/OBO.)
- [ ] AC-15: UI reflects the disablement — `infrastructure_authorization_enabled` is exposed via `/health.auth`; when true the UI hides the Schedules nav item and the `/schedules` route shows a clear "unavailable while infrastructure authorization is enabled" notice. Gated on the authz flag (authn-only deployments keep Schedules).

## Technical Context
- **Hook signature (FINAL — token contract):** `scope(auth_token: str, targets: list[TargetRef]) -> list[TargetRef]`, where `auth_token` is the **validated JWT bearer string** (the hook may decode it OR forward it to an external authz service) and `TargetRef` is a frozen `{kind, resource_id, name, environment}`. The token is authn-validated (signature/iss/aud/exp via the single `validate_token` path) BEFORE the hook runs — the hook never sees an unverified token. Each surface (REST cluster/instance records, catalog docs) adapts native objects ↔ `TargetRef`, so ONE hook serves clusters and instances. The token is carried to enforcement points via a trust-boundary ContextVar (`set_auth_token` in `require_auth` and at each worker-task top), not threaded through every signature. Filtering a list and validating one attached target are the same call (singleton → check non-empty). The engine intersects the hook's result with the input, so a buggy/hostile hook can only REMOVE access. No token / hook error / hook timeout → fail closed. There is no `system_principal`: the only tokenless agent surface is MCP, which is refused when authz is enabled.
- **Config (`core/config.py:243` Settings):** add `infrastructure_authorization_enabled: bool` and `infrastructure_authorization_hook: Optional[str]` (import path), plus a `@model_validator(mode="after")` enforcing authz⇒authn and authz⇒hook-configured.
- **Enforcement wiring:** `get_target_catalog()` / `list_known_targets()` (`core/targets.py`); chat + deep-triage agent invocation in `agent/langgraph_agent.py` (tools loaded per-query off attached target bindings) — validate attached target(s) before the run proceeds. Precedent for an interception boundary: `execute_tool_calls_with_gate` (`agent/tool_execution.py`).
- **Identity source:** the validated JWT bearer. Thread it: `require_auth` (`api/auth.py:37`) → put the raw bearer into the turn `context` at enqueue (`api/tasks.py:162`) → `process_agent_turn` → re-validate with `validate_token` at agent-run time → pass claims to the hook. NEVER use `req.user_id` (`api/tasks.py:137`) as an authz input.

## Interview Transcript
<details>
<summary>Full Q&A (4 rounds)</summary>

### Round 0 (topology)
Confirmed 3 components; identity provenance = SSO claims.

### Round 1
**Q:** Where does the allow-list come from — claims, external service, model field, or contract-only?
**A:** The repo has no mapped clusters/instances; the hook is called to learn what the user can access. Call it every time that info is needed (list instances, list clusters, agent invoked with a target attached).
**Ambiguity:** 38%

### Round 2
**Q:** One env var or two; authz vs authn.
**A:** Keep authentication separate from authorization; if authz enabled, authn must be enabled too.
**Resolution:** Two flags, startup validator enforces authz⇒authn.

### Round 3
**Q:** Behavior on no-logged-in-user paths (worker/CLI/eval).
**A:** SSO is enabled across API, CLI, UI; authorization should mirror it. (CLI authenticates via device-code; tasks persist `user_id`.)

### Round 4
**Q:** Deferred worker run — resolve authz at entry, or re-call hook in worker?
**A:** Worker re-calls the hook when chat and deep-triage agents are triggered; the attached target must be validated live because access can change between login and chatting.
**Resolution:** Live re-check keyed by durable `user_id`, not the bearer token.
**Ambiguity:** 13%
</details>

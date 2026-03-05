# RedisCluster and RedisInstance Split: Revised Implementation Plan

## Objective

Split cluster concerns from database instance concerns while keeping scope minimal:

- Add a first-class `RedisCluster` model.
- Keep `RedisInstance` as the database instance model.
- Keep `instance_type` on `RedisInstance`.
- Add `cluster_type` on `RedisCluster`.
- Keep Redis Cloud subscription/database fields on `RedisInstance` for now.
- Keep legacy `RedisInstance` admin fields in the model/API during transition, but mark them as
  **deprecated** using Pydantic field deprecation (`Field(..., deprecated=True)`).
- Add an automated migration step that creates/links `RedisCluster` records from legacy instance
  admin data when needed.
- Explicit migration rule: if any existing instance has non-empty deprecated enterprise admin
  fields (`admin_url`, `admin_username`, or `admin_password`) and no `cluster_id`, automatically
  create/link a `RedisCluster` and populate `cluster_id`.

---

## Confirmed Scope Decisions

1. Introduce `RedisCluster` without introducing `RedisCloudSubscription` in this change.
2. Enforce validation for cluster objects at model and API layers.
3. Create dedicated request/response models for cluster APIs.
4. Enforce new validation rules in instance and cluster API flows.
5. Preserve legacy instance admin fields as deprecated compatibility fields until sunset.
6. Add automated migration to backfill clusters + `cluster_id` relationships from legacy data,
   including auto-creating clusters from deprecated instance admin fields when needed.
7. Execute migration automatically during service startup (no manual trigger required for normal
   operation).

---

## Target Data Models

## `RedisCluster` (new)

Core fields:

- `id: str`
- `name: str`
- `cluster_type: RedisClusterType` (`oss_cluster | redis_enterprise | redis_cloud | unknown`)
- `environment: str`
- `description: str`
- `notes: Optional[str]`
- `admin_url: Optional[str]`
- `admin_username: Optional[str]`
- `admin_password: Optional[SecretStr]`
- `status: Optional[str]`
- `version: Optional[str]`
- `last_checked: Optional[str]`
- `extension_data: Optional[Dict[str, Any]]`
- `extension_secrets: Optional[Dict[str, SecretStr]]`
- `created_by: str`
- `user_id: Optional[str]`
- `created_at: str`
- `updated_at: str`

Validation rules:

1. `cluster_type` must be enum-valid.
2. `environment` must be one of: `development | staging | production | test`.
3. `name` is required and non-empty after trim.
4. If `cluster_type == redis_enterprise`, all of `admin_url`, `admin_username`, and
   `admin_password` are required.
5. If `cluster_type != redis_enterprise`, reject `admin_url/admin_username/admin_password`.
6. `created_by` must be `user | agent`.

## `RedisInstance` (updated)

Core fields retained:

- `id`, `name`, `connection_url`, `environment`, `usage`, `description`
- `repo_url`, `notes`, `monitoring_identifier`, `logging_identifier`
- `instance_type`
- `status`, `version`, `memory`, `connections`, `last_checked`
- `extension_data`, `extension_secrets`, `created_by`, `user_id`, `created_at`, `updated_at`

Fields added:

- `cluster_id: Optional[str]`

Legacy fields retained (deprecated compatibility fields):

- `admin_url: Optional[str]` (`deprecated=True`)
- `admin_username: Optional[str]` (`deprecated=True`)
- `admin_password: Optional[SecretStr]` (`deprecated=True`)

Cloud fields retained on instance for this phase:

- `redis_cloud_subscription_id`
- `redis_cloud_subscription_type`
- `redis_cloud_database_id`
- `redis_cloud_database_name`

Validation rules:

1. `cluster_id` is optional.
2. If `cluster_id` is provided, it must reference an existing cluster at API/service layer.
3. If `cluster_id` is provided, `instance_type` and `cluster_type` must be compatible.
4. `created_by` must be `user | agent`.
5. During compatibility window, enterprise instances may still supply deprecated `admin_*` fields;
   migration should materialize them to a linked `RedisCluster`.

---

## Compatibility API Contract (Deprecated Legacy Fields)

1. Instance create/update continues to accept `admin_*` fields, but marks them deprecated in schema.
2. Instance responses may continue to return masked `admin_*` fields during transition (deprecated).
3. `cluster_id` is the preferred relationship, and cluster endpoints are the primary credential path.
4. A cluster must be created before an instance can reference it (`cluster_id`
   must point to an existing cluster at create/update time).
5. Automated migration creates clusters + links for existing instances that still use legacy
   `admin_*` fields, and runs automatically on service startup.

---

## Revised Full Execution Plan

## Phase 0: Prep and Baseline

1. Capture baseline tests for instances, API, tool manager, and UI services.
2. Confirm no unrelated local edits are modified by this work.

Deliverable:

- Clean, isolated change set for model split.

## Phase 1: Domain Models and Validation

1. Add `redis_sre_agent/core/clusters.py` with:
   - `RedisClusterType`
   - `RedisCluster`
   - model-level validation rules listed above
   - helper secret serializer for `admin_password`
2. Update `redis_sre_agent/core/instances.py`:
   - add `cluster_id`
   - keep `admin_*` on `RedisInstance` as deprecated fields
   - annotate with Pydantic deprecated metadata (`Field(..., deprecated=True)`) per
     https://docs.pydantic.dev/latest/concepts/fields/#deprecated-fields
   - keep cloud fields
   - enforce instance-level validation for optional `cluster_id` compatibility rules

Deliverable:

- Domain models compile with strict validation.

## Phase 2: Storage and Search Index Layer

1. Update `redis_sre_agent/core/redis.py`:
   - add `SRE_CLUSTERS_INDEX`
   - add cluster schema
   - add `get_clusters_index()`
   - include clusters index in Redis initialization/recreate flows
2. Implement cluster persistence/query functions in `core/clusters.py`:
   - `get_clusters`
   - `query_clusters`
   - `save_clusters`
   - `get_cluster_by_id`
   - `delete_cluster_index_doc`

Deliverable:

- Cluster data persisted and queryable with RediSearch.

## Phase 3: Cluster API with Request/Response Models

1. Add `redis_sre_agent/api/clusters.py` endpoints:
   - `GET /api/v1/clusters`
   - `POST /api/v1/clusters`
   - `GET /api/v1/clusters/{cluster_id}`
   - `PUT /api/v1/clusters/{cluster_id}`
   - `DELETE /api/v1/clusters/{cluster_id}`
2. Add dedicated models:
   - `CreateClusterRequest`
   - `UpdateClusterRequest`
   - `RedisClusterResponse`
   - `ClusterListResponse`
3. Enforce cluster validation at API edge using request models.
   - `cluster_type=redis_enterprise` must include `admin_url`, `admin_username`,
     and `admin_password`.
4. Mask secrets in cluster responses (`admin_password` always masked).

Deliverable:

- Fully typed and validated cluster API surface.

## Phase 4: Instance API Compatibility + Referential Rules

1. Update `redis_sre_agent/api/instances.py` request/response models:
   - add `cluster_id`
   - retain legacy `admin_*` as deprecated request/response fields
   - mark deprecated in Pydantic schema fields
2. Enforce service-layer checks:
   - referenced `cluster_id` exists
   - `instance_type` and `cluster_type` compatibility is valid
3. Keep cloud fields unchanged in instance API models.
4. Add compatibility behavior:
   - if `cluster_id` is absent and deprecated `admin_*` fields are provided, allow create/update
     (with deprecation warning) so migration/backfill can establish linkage.
5. Wire new cluster router in `redis_sre_agent/api/app.py`.

Deliverable:

- Backward-compatible instance API behavior with deprecation + referential validation.

## Phase 5: Tooling and Agent Integration

1. Update `redis_sre_agent/tools/manager.py`:
   - resolve cluster from `instance.cluster_id` when loading instance-scoped providers
2. Update `redis_sre_agent/tools/admin/redis_enterprise/provider.py`:
   - consume admin credentials from `RedisCluster`
3. Update agent enterprise checks in `redis_sre_agent/agent/langgraph_agent.py`:
   - check cluster-level admin configuration (not instance-level)
   - optionally fallback to deprecated instance `admin_*` during transition with warning
4. Keep Redis Cloud provider behavior unchanged for this phase.

Deliverable:

- Enterprise tool/provider path works with cluster model.

## Phase 6: CLI Changes

1. Add `redis_sre_agent/cli/cluster.py` with basic CRUD commands.
2. Register cluster command group in `redis_sre_agent/cli/main.py`.
3. Update `redis_sre_agent/cli/instance.py`:
   - keep admin CLI args but mark as deprecated
   - add `--cluster-id`
   - enforce updated validations

Deliverable:

- CLI supports separated cluster and instance management with deprecated compatibility flags.

## Phase 7: UI and API Client Updates

1. Update `ui/src/services/sreAgentApi.ts`:
   - add `RedisCluster` types and cluster methods
   - update instance request/response types for compatibility mode + deprecation annotations
2. Update `ui/src/pages/Instances.tsx`:
   - keep instance-level admin inputs as deprecated (clearly labeled)
   - add cluster selection/create-edit association UX

Deliverable:

- UI reflects new data model boundaries while preserving deprecated compatibility inputs.

## Phase 8: Data Migration Script

1. Add a migration module (reusable from startup + CLI/manual entrypoint), for example:
   - `redis_sre_agent/core/migrations/instances_to_clusters.py`
2. Implement idempotent, multi-process-safe execution semantics:
   - acquire a Redis distributed lock (`SET ... NX EX`) before mutation
   - use a migration completion marker key with versioning
   - if marker exists, exit cleanly with a no-op summary
3. Load and persist through domain helpers (not raw ad-hoc Redis writes):
   - read via `get_instances()` and `get_clusters()`
   - write via `save_clusters()` then `save_instances()` (ordering avoids dangling `cluster_id`)
4. Define eligibility and type mapping rules:
   - migrate only instances where `cluster_id` is empty and `instance_type in {redis_enterprise, oss_cluster, redis_cloud}`
   - map `instance_type -> cluster_type` as:
     - `redis_enterprise -> redis_enterprise`
     - `oss_cluster -> oss_cluster`
     - `redis_cloud -> redis_cloud`
5. Transfer relevant fields from `RedisInstance` to `RedisCluster`:
   - always transfer: `environment`, `description`, `notes`, `status`, `version`, `last_checked`,
     `created_by`, `user_id`, `created_at`
   - enterprise-only transfer: `admin_url`, `admin_username`, `admin_password`
6. Use safe deduplication with conservative merge behavior:
   - for strong identity cases, reuse existing cluster by deterministic fingerprint
   - for weak-identity cases (especially `oss_cluster`), default to one-cluster-per-instance to
     prevent accidental cross-instance merges
7. Preserve compatibility fields while establishing preferred linkage:
   - keep deprecated instance `admin_*` fields during transition
   - set `instance.cluster_id` and add migration metadata to `extension_data`
     (source/version/timestamp) for auditability and idempotency
8. Add startup automation:
   - invoke migration automatically on API and worker startup
   - do not hide behind a feature flag for normal operation
   - run as best-effort startup task with clear logging and summary metrics
9. Include operational controls:
   - `--dry-run` mode that performs full analysis without writes
   - summary counters: `scanned`, `eligible`, `clusters_created`, `instances_linked`, `skipped`, `errors`

Deliverable:

- Existing deployments are backfilled safely, idempotently, and automatically with auditable linkage.

## Phase 9: Tests and Verification

1. Add/modify any missing unit tests for:
   - cluster model validations
   - instance model updated validations
   - cluster storage/query
   - instance-cluster compatibility checks
2. Add/modify any missing API tests for:
   - cluster request/response models
   - compatibility-mode instance contract with deprecated fields
3. Add integration tests for:
   - enterprise tool loading using cluster credentials
   - end-to-end create cluster -> create instance -> run diagnostics for API
   - end-to-end create cluster -> create instance -> run diagnostics for CLI

Deliverable:

- All changed paths have regression protection.

## Phase 10: Docs and Developer Guides

1. Update API docs and examples:
   - `docs/reference/api.md`
   - `docs/how-to/api.md`
2. Update CLI docs:
   - `docs/reference/cli.md`
3. Add migration instructions and deprecation/sunset notes.

Deliverable:

- Documentation matches behavior and migration path.

---

## Compatibility Matrix (Validation Enforcement)

1. `cluster_id` is optional for all instance types in this phase.
2. If `cluster_id` is provided, it must reference an existing cluster.
3. If `instance_type=redis_enterprise` and `cluster_id` is provided, linked cluster must be `cluster_type=redis_enterprise`.
4. If `instance_type=oss_cluster` and `cluster_id` is provided, linked cluster should be `cluster_type=oss_cluster`.
5. `cluster_type=redis_enterprise` requires `admin_url`, `admin_username`,
   and `admin_password`; non-enterprise cluster types must not provide these fields.
6. If `cluster_id` is present, cluster credentials are authoritative.
7. If `cluster_id` is absent, deprecated instance `admin_*` fields may be used temporarily
   (with warning) until migration/sunset is complete.

---

## Acceptance Criteria

1. New cluster APIs exist with dedicated request/response models.
2. Cluster validations are enforced in both model and API layers.
3. Instance APIs enforce compatibility schema with deprecated fields plus referential/compatibility checks.
4. Enterprise provider uses cluster credentials by default, with explicit deprecated fallback behavior if enabled.
5. Migration script successfully transitions existing instance admin data to linked clusters.
6. Migration covers the explicit compatibility case:
   any instance with deprecated admin fields and missing `cluster_id` is automatically linked
   to a created/reused RedisCluster.
7. Startup path executes migration automatically without manual command invocation.
8. Updated tests pass for backend and UI API client contracts.

---

## Phase-by-Phase Test and Validation Protocol

| Phase | Implementation Checks | Test Execution | Validation With You |
|---|---|---|---|
| Phase 0: Prep and baseline | Confirm no unrelated files are touched by this plan implementation work. | Run baseline targeted tests for instances/API/tool manager/UI API client. | I share baseline pass/fail summary and the exact test set used; you confirm baseline is acceptable before model changes start. |
| Phase 1: Domain models and validation | Confirm `RedisCluster` and updated `RedisInstance` compile and validators match spec. | Add/run unit tests for all model validation rules (enterprise admin required, forbidden admin on non-enterprise, optional cluster link compatibility). | I provide validator matrix (rule -> passing case -> failing case) and file diff; you confirm rules match intent. |
| Phase 2: Storage and index layer | Confirm cluster index schema exists and CRUD/query helpers persist and load correctly. | Run unit/integration tests for `save/get/query/delete` cluster operations and index creation behavior. | I share storage behavior summary with example persisted payload shape and query results; you approve storage contract. |
| Phase 3: Cluster API models/endpoints | Confirm cluster request/response models are in place and API edge validation is active. | Run API tests for cluster CRUD, validation failures, masked secret responses, and required enterprise admin fields. | I provide request/response examples (success + validation errors) and endpoint list; you approve API contract. |
| Phase 4: Instance API compatibility | Confirm instance models include `cluster_id`, keep legacy `admin_*` as deprecated, and enforce referential/type checks when `cluster_id` is provided. | Run API tests for compatibility behavior (legacy admin fields accepted but deprecated), optional `cluster_id`, and cluster compatibility checks for linked instances. | I provide explicit deprecation behavior examples and compatibility impact summary; you confirm transition behavior is acceptable. |
| Phase 5: Tooling and agent integration | Confirm Enterprise provider and tool manager resolve admin credentials from cluster object when a linked cluster is present. | Run unit/integration tests for provider initialization and enterprise diagnostic path using cluster-linked credentials. | I share tool-loading path evidence and enterprise flow behavior; you confirm runtime behavior matches design. |
| Phase 6: CLI changes | Confirm new cluster CLI commands and updated instance CLI flags/validation. | Run CLI unit/integration tests and command smoke tests for cluster CRUD + instance create/update with `--cluster-id`. | I share command examples and expected outputs/errors; you confirm UX and behavior. |
| Phase 7: UI/API client updates | Confirm UI types and API client contracts match compatibility backend API, including deprecation metadata. | Run UI unit tests and relevant e2e flows for instance/cluster creation and association, including deprecated-field flows. | I share UI behavior summary and screenshots/flow notes if needed; you confirm expected workflow. |
| Phase 8: Data migration script + automation | Confirm migration is module-based, idempotent, and lock/marker protected; uses domain storage helpers; maps cluster-capable `instance_type` values to `cluster_type`; transfers required fields safely; sets `cluster_id`; preserves deprecated `admin_*` compatibility fields; and runs automatically at API/worker startup. Confirm conservative dedupe behavior (no unsafe merges for weak identity). | Run migration tests: dry-run, real-run on fixture data, re-run idempotency, startup-triggered run (API and worker), multi-process lock/marker safety checks, conservative dedupe/merge safety checks, rollback/safety checks, and field-transfer fixtures for each supported type (`redis_enterprise`, `oss_cluster`, `redis_cloud`). | I share before/after record counts, cluster creation/linkage counts, sample transformed records (including metadata stamps), and startup-run evidence from logs/metrics; you approve production migration runbook. |
| Phase 9: Full regression | Confirm all changed areas work together end-to-end. | Run `make test` plus targeted integration suites for instances/clusters/tools/API/CLI/UI service contract. | I share full regression results and residual risks/gaps; you approve release-readiness. |
| Phase 10: Docs and guides | Confirm docs reflect final API/CLI/model behavior, deprecations, and sunset plan. | Validate doc snippets against actual commands/endpoints and update generated references if needed. | I provide final doc diff and checklist of updated pages; you confirm documentation completeness. |

### Phase Gate Rule

No phase advances until:

1. The phase test gate passes.
2. I provide a concise implementation and test evidence summary.
3. You explicitly confirm to proceed to the next phase.

### TDD Workflow (Applied in Every Phase)

For each phase, implementation will follow this red/green loop:

1. Write or update tests for that phase first (expected to fail initially).
2. Run only the phase-targeted tests for fast feedback.
3. Implement the minimal code needed to satisfy the failing tests.
4. Re-run the same targeted tests until they pass.
5. Run the broader phase regression suite.
6. Share test evidence and get explicit sign-off before continuing.

### Test Command Checklist

Use this command pattern during each phase:

1. Focused backend test run:
   - `uv run pytest tests/unit/<target_file>.py -q`
   - `uv run pytest -k "<phase_keyword>" -q`
2. Backend unit regression gate:
   - `make test`
3. Backend integration gate (when phase touches integration paths):
   - `make test-integration`
4. Full regression gate before finalization:
   - `make test-all`
5. UI validation gate:
   - `cd ui && npm run e2e` (existing)
   - If UI unit test runner is added in this project phase, run it as part of the phase gate too.

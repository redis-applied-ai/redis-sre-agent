# 0.4.0 Manual QA Plan

## Scope

This plan covers the feature delta from `v0.3.1` to `origin/main` as of 2026-04-29. The main user-facing changes in that range came from:

- `#116` thread subject generation
- `#119` TOML and JSON config support
- `#120` exact-search compatibility improvements
- `#122` expanded MCP admin/query tooling and analyzer-facing query entrypoints
- `#124` natural-language target discovery
- `#131` Agent Memory Server integration
- `#133` multi-target investigation and comparison
- `#135` MCP stdio logging isolation
- `#137` path-based source document updates
- `#138` source identity preservation during `prepare_sources`
- `#141` pluggable target binding/discovery
- `#142` published UI air-gap image support
- `#144` mocked eval runtime and reporting harness
- `#145` HITL approvals and resume
- `#146` pipeline scrape stall fixes and progress visibility
- `#147` runtime triage follow-up fixes
- `#149` Agent Skills package support
- `#150` startup skill grounding provenance
- `#151` local `expand_evidence` execution fixes
- `#153` explicit source-document frontmatter `url`

## Common QA Setup

- Test both CLI and API-driven workflows where both surfaces exist.
- Use Redis 8 for the primary validation path.
- If an older Redis Search deployment is available, include one compatibility pass for exact-search behavior.
- Exercise at least one run with `config.yaml`, one with `config.toml`, and one with `config.json`.
- Capture screenshots or transcripts for failures in task status, approvals, UI, and docs examples.
- For every feature area below, verify the linked docs are current and execute the examples exactly as written before trying edited variants.

## 1. Configuration, Bootstrap, and Operational Safety

Related changes: `#116`, `#119`, `#120`, `#135`, `#147`

Docs to verify:

- `README.md`
- `docs/how-to/configuration.md`
- `docs/reference/configuration.md`
- `docs/operations/gotchas.md`
- `docs/reference/api.md`

Manual checks:

1. Start the app with equivalent settings expressed in YAML, TOML, and JSON and verify the resolved config is identical.
2. Verify explicit config path selection wins over auto-discovered default files when multiple formats exist.
3. Create a thread with and without an initial user message and verify subject generation behaves sensibly and never yields an empty placeholder.
4. Start the MCP server in stdio mode and verify machine-readable stdout is clean while logs route to stderr.
5. Run exact identifier-style knowledge queries on Redis 8 and, if available, an older Redis Search target to confirm graceful compatibility behavior.
6. Trigger a known runtime error path and confirm the surfaced error is actionable instead of silently empty.

Edge cases:

- malformed TOML or JSON
- multiple config files present at once
- empty thread seed message
- quoted literal search phrase vs natural-language query
- stdio startup with verbose logging enabled

## 2. Natural-Language Target Discovery and Binding

Related changes: `#124`, `#141`, `#147`

Docs to verify:

- `docs/how-to/tool-providers.md`
- `docs/how-to/local-dev.md`
- `docs/reference/configuration.md`
- `specs/natural-language-target-discovery-spec.md`

Manual checks:

1. Ask for a known Redis target by friendly name, alias, environment, and partial description and verify the same target is selected consistently.
2. Ask for an ambiguous target and verify the agent asks a clarifying question instead of binding arbitrarily.
3. Ask for a nonexistent target and verify the failure is explicit and safe.
4. Continue an existing thread after a target is attached and verify later turns reuse the binding correctly.
5. Swap discovery and binding configuration to any non-default backend available in test config and verify registry-driven loading still works.

Edge cases:

- alias matches across instance and cluster records
- one query resolving to multiple environments
- missing credentials after successful discovery
- bound thread resumed after process restart

## 3. Multi-Target Investigation and Comparison

Related changes: `#133`, `#147`

Docs to verify:

- `docs/how-to/cli.md`
- `docs/reference/api.md`
- `docs/reference/cli.md`

Manual checks:

1. Ask the chat agent to compare two attached targets and verify evidence is collected per target before summarization.
2. Run the same comparison through any CLI or MCP entrypoint that supports target context and verify the result format is stable.
3. Mix cluster and instance targets in the same comparison and verify the narrative stays explicit about scope.
4. Ask a follow-up question about only one of the compared targets and verify the agent narrows scope correctly.

Edge cases:

- duplicate target selection in the same request
- one healthy target and one failing target
- three or more targets when `allow_multiple=true`
- partial evidence availability on one target only

## 4. Query, Admin, and Thread-Oriented MCP Surfaces

Related changes: `#122`, `#147`

Docs to verify:

- `docs/reference/api.md`
- `docs/reference/cli.md`
- `docs/how-to/cli.md`

Manual checks:

1. Exercise `redis_sre_query` with only free-text input, then with `instance_id`, `cluster_id`, `thread_id`, and `support_package_id`.
2. Validate one create/read/update/delete workflow for instances, clusters, schedules, and support packages in a safe non-production environment.
3. Confirm task, thread, citations, approvals, and source inspection tools return coherent cross-links after a completed run.
4. Verify queue-and-watch flows still work after using the routed query entrypoint.

Edge cases:

- query with both live target and support package context
- query continuation on an old thread
- invalid ids for each object family
- empty result sets from list/search tools

## 5. HITL Approvals and Resume

Related changes: `#145`

Docs to verify:

- `docs/reference/api.md`
- `specs/hitl-approvals-and-resume-spec.md`

Manual checks:

1. Run a read-only task and confirm write-capable actions are blocked or classified correctly.
2. Run a task that requires approval, verify it enters `awaiting_approval`, and inspect approval metadata on the task and thread.
3. Approve the pending action and confirm resume continues the interrupted run instead of starting from scratch.
4. Reject the pending action and verify the task records the rejection cleanly.
5. Trigger two approval boundaries in one logical task and verify both cycles work.

Edge cases:

- repeated resume submission for the same approval
- expired approval
- approval after worker restart
- approval mismatch or stale approval id

## 6. Agent Memory Server Integration

Related changes: `#131`

Docs to verify:

- `docs/how-to/agent-memory-server-integration.md`
- `README.md`

Manual checks:

1. Run a conversation with `user_id` only and verify user-scoped memory recall and later persistence.
2. Run with target scope only and verify asset-scoped recall without unrelated personalization.
3. Run with both `user_id` and target scope and verify both memory classes influence the answer.
4. Run with neither and verify the agent skips long-term memory cleanly.
5. Simulate AMS unavailability and confirm fail-open behavior still preserves live-tool and KB functionality.

Edge cases:

- conflicting user-scoped vs asset-scoped memory
- stale memory contradicted by live telemetry
- first conversation with no prior memory
- memory write after a failed run

## 7. Agent Skills Retrieval, Package Support, and Startup Grounding

Related changes: `#149`, `#150`, `#151`

Docs to verify:

- `docs/how-to/source-document-features.md`
- `docs/how-to/configuration.md`
- `specs/agent-skills-protocol-support-spec.md`

Manual checks:

1. Ingest and retrieve a legacy single-file skill and an Agent Skills package and verify both appear in `skills_check`.
2. Retrieve a package resource with `get_skill_resource` and verify truncation rules and metadata are correct.
3. Confirm startup grounding records skill discovery provenance and that the envelopes are inspectable later.
4. Ask for a workflow that needs `expand_evidence` and verify local-only tool execution works without remote tool-manager routing failures.
5. Verify script, text asset, and helper-file references from a skill package remain retrieval-only and are not executed implicitly.

Edge cases:

- skill package missing `SKILL.md`
- large resource file hitting the character budget
- duplicate skill names across legacy and package formats
- skill retrieval with no query vs tight query

## 8. Source Documents, Front Matter, and Ingestion Identity

Related changes: `#137`, `#138`, `#146`, `#153`

Docs to verify:

- `docs/how-to/pipelines.md`
- `docs/how-to/source-document-features.md`

Manual checks:

1. Add a new markdown document under `source_documents/`, run `prepare_sources`, then ingest and verify it appears in retrieval.
2. Update the same file in place and verify the change is treated as an update, not a duplicate insert.
3. Rename or move the file and verify path-based identity handling produces the expected add/update/delete behavior.
4. Delete a previously ingested source document and verify cleanup behavior is correct.
5. Add front matter with explicit `url` and verify both the stored document and chunk metadata use that URL instead of a `file://` path.
6. Mix standard docs, pinned docs, and skill packages under the source root and verify discovery still classifies them correctly.
7. Run a long scrape/prepare flow and confirm progress visibility updates move forward without apparent stalls.

Edge cases:

- nested source roots
- duplicate content at different paths
- same path with changed frontmatter only
- invalid frontmatter
- explicit `url` present but blank or whitespace-only

## 9. Mocked Eval Runtime, Reporting, and Comparison

Related changes: `#144`, `#150`

Docs to verify:

- `docs/how-to/evals.md`
- `docs/reference/cli.md`
- `specs/mocked-agent-eval-system-spec.md`
- `specs/eval-fixture-layout-spec.md`

Manual checks:

1. Run `eval list` and confirm scenario discovery matches the repo contents.
2. Run one mocked scenario through the supported local workflow and verify reports are generated in the documented location.
3. Run a live-suite command with the documented trigger settings and verify baseline policy handling is correct.
4. Compare a candidate run against a baseline and verify both pass and fail paths are easy to interpret.
5. Confirm scenarios that include skills or startup knowledge show the expected evidence provenance.

Edge cases:

- missing baseline artifact
- missing scenario report in candidate output
- scenario with retrieval disabled vs retrieval enabled
- malformed scenario manifest

## 10. Docker, UI Example, and Air-Gapped Deployment

Related changes: `#125`, `#130`, `#140`, `#142`

Docs to verify:

- `docs/operations/docker-deployment.md`
- `docs/operations/airgap-deployment.md`
- `docs/ui/experimental.md`
- `README.md`

Manual checks:

1. Build and start the local Docker stack and verify the UI, API, and supporting services come up cleanly.
2. Run the `ui/example` dev flow and verify the example app builds, hot reloads, and exercises the updated form paths.
3. Build the air-gap bundle with default options and verify both backend and UI images are present.
4. Repeat the bundle build with `--skip-ui-image`, `--skip-artifacts`, custom tags, and optional push settings and verify the outputs match the docs.
5. Pull and run the published UI air-gap image path described in docs and verify it serves correctly behind the compose profile.

Edge cases:

- npm patch drift after lockfile refresh
- repeated docker rebuilds with cached layers
- running the UI profile only
- incomplete offline environment variables

## 11. Documentation and Example Audit

This is a cross-cutting exit gate for the entire release.

Manual checks:

1. For every feature area above, confirm at least one user-facing doc mentions the feature and links to the right command or API surface.
2. Execute every newly added or materially changed command example in:
   - `README.md`
   - `docs/how-to/*.md`
   - `docs/operations/*.md`
   - `docs/ui/experimental.md`
3. Flag examples that require unstated prerequisites, wrong paths, stale image tags, or incorrect trigger values.
4. Verify generated references remain in sync with the implemented CLI and API.

Exit criteria:

- Every feature added since `v0.3.1` has at least one explicit manual QA pass.
- Every changed example either runs as written or is documented as intentionally illustrative.
- Any doc gaps are recorded as release blockers or immediate follow-up tasks.

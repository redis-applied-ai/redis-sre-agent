# Mocked Agent and Retrieval Eval System

Status: Proposed

## Summary

Build a first-class eval system that can run the existing Redis SRE agents against fully mocked
tooling, mocked targets, and mocked knowledge sources without requiring a live Redis deployment,
live Redis Enterprise cluster, or live external observability systems.

The core requirement is not just static answer grading. The eval runtime must preserve the actual
agent loop:

- real system prompts
- real routing behavior
- real tool schemas
- real tool selection by the LLM
- real multi-turn tool-call discovery
- real startup-context injection for pinned documents and skills

The difference is that every external dependency becomes scenario-controlled. A scenario defines
what targets exist, what tools are visible, what those tools return, what knowledge is available,
and what the agent is expected to discover or follow.

This spec also defines a retrieval-only eval track so we can measure pure retrieval quality
independently from agent reasoning.

## Problem

The repository already has partial evaluation pieces:

- `redis_sre_agent/evaluation/judge.py` provides LLM-as-judge scoring
- `redis_sre_agent/evaluation/retrieval_eval.py` provides retrieval metrics
- `redis_sre_agent/evaluation/test_cases.py` provides static diagnostic scenarios
- `redis_sre_agent/tools/fake/provider.py` and `redis_sre_agent/targets/fake_integration.py`
  prove that fake target integrations can be attached

These are useful foundations, but they do not provide the eval system we need:

- they do not run the full agent loop against scenario-bound tool outputs
- they do not cover both instance-scoped and cluster-scoped Redis surfaces
- they do not emulate MCP-exposed observability tools as discoverable tool surfaces
- they do not let us ablate knowledge, pinned documents, runbooks, and skills independently
- they do not measure whether the agent followed instructions from pinned or retrieved sources
- they do not provide retrieval-only evals over the same source fixtures and parameters

As a result, we cannot answer high-value questions such as:

- Did a prompt change alter tool-use behavior or only final wording?
- Would the chat agent choose the right tools for a Redis Enterprise node-maintenance incident?
- Does the agent behave differently when pinned policy docs are present?
- Did a runbook or skill retrieval improve or degrade the answer?
- How much of a regression is caused by retrieval quality versus prompt behavior?

## Goals

- Evaluate `chat`, `redis_triage`, and routing behavior without live infrastructure.
- Mock all Redis-facing and external tool outputs while preserving real tool schemas and the real
  agent control loop.
- Support instance, cluster, and Redis Enterprise cluster scenarios with no live Redis or admin
  API required.
- Support fake MCP-exposed tools for metrics, logs, traces, tickets, repos, and utilities so the
  eval can exercise MCP discovery and tool selection behavior.
- Evaluate startup-context behavior with:
  - knowledge disabled
  - pinned docs only
  - retrieval only
  - full knowledge access
- Evaluate whether the agent follows instructions from:
  - pinned documents
  - retrieved runbooks
  - retrieved skills
  - retrieved support tickets
- Provide pure retrieval evals that measure search quality without the LLM in the loop.
- Produce reproducible artifacts: prompts, tool traces, retrieved sources, scores, and pass/fail
  outcomes.
- Make the eval system suitable for CI and for local developer iteration.

## Non-goals

- Replacing the production `ToolManager` or production retrieval path for normal runtime use.
- Evaluating the temporary backward-compatibility `knowledge_only` / zero-scope entrypoint beyond
  confirming it remains out of scope for this eval system.
- Simulating every Redis command or every vendor API in v1.
- Building a full browser-first eval product before the core runtime exists.
- Solving synthetic data generation in this spec. The system must support curated fixtures first.

## Design Principles

1. Preserve production contracts whenever possible.
2. Mock behind boundaries, not by rewriting agent code for tests.
3. Make knowledge access independently switchable from tool access.
4. Treat pinned startup context, retrieved documents, and tool outputs as separate evidence layers.
5. Keep eval scenarios declarative so non-runtime contributors can author them.
6. Record enough evidence to explain regressions without rerunning live systems.
7. Intercept at the highest runtime seam needed for the eval goal.

## Current-State Constraints

### 1. `ToolManager` centralizes provider loading, but not the whole turn flow

`ToolManager` is the natural interception point for provider virtualization because it already:

- loads always-on knowledge and utility providers
- loads instance-scoped and cluster-scoped providers
- loads MCP providers
- supports attached target bindings and `TurnScope`

But the full production turn flow starts above it in the task/query orchestration layer, where the
runtime already handles:

- router selection
- thread and task state
- `TurnScope` construction
- target resolution and attached-target behavior
- temporary backward-compatibility entrypoints that should remain out of scope for eval coverage

That means full-loop evals should wrap the production turn entrypoint, not just agent
`process_query()` calls. `ToolManager` is still the right provider virtualization boundary inside
that higher-level harness.

### 2. Startup context is already a distinct layer, but not retrieval-free today

`build_startup_knowledge_context()` already composes:

- pinned documents
- skills TOC
- category-specific tool instructions

That means pinned-context evals should target this builder and the retrieval helpers behind it,
not reimplement startup injection elsewhere.

Important caveat: startup context currently performs query-dependent skill lookup. So a
`startup_only` eval mode cannot mean “no retrieval at all” unless the startup skill lookup path is
explicitly switchable or replaced with fixture-backed startup data.

### 3. The retrieval path already has semantic and exact-match behavior

`search_knowledge_base_helper()`, `skills_check_helper()`, and
`get_pinned_documents_helper()` already encode:

- version filtering
- doc-type filtering
- pinned-document behavior
- special handling for skills and support tickets
- exact and precise-search paths

The eval system should exercise these semantics, including ablation and parameter variation.

### 4. MCP loading is currently global-settings-driven

`ToolManager` loads MCP providers from configured `settings.mcp_servers`.

That means scenario-defined fake MCP servers need an explicit per-run config injection path. The
spec cannot assume that fake MCP surfaces simply appear without either:

- a scenario-scoped `ToolManager` configuration override, or
- a first-class eval-only provider injection API

### 5. Tool identities are runtime-generated, not stable logical strings

The runtime does not expose tools to the model or traces as stable dotted identifiers like
`redis_enterprise_admin.get_cluster_info`.

Actual tool names are generated from provider identity plus a per-instance hash. MCP tool names are
also derived from configured server names, not from capability labels such as `metrics`.

That means eval scenarios and assertions need a normalized logical identity layer that maps onto
concrete runtime tool names.

## Proposed Architecture

## 1. Introduce an `EvalRuntime`

Add a dedicated runtime layer that wraps agent execution for evals.

Primary responsibilities:

- load an eval scenario
- configure target scope and tool visibility
- replace live tool execution with scenario-driven responders
- optionally replace knowledge retrieval with fixture-backed retrieval
- run the selected production turn path or a narrower agent-only path
- capture prompts, tool calls, retrieved sources, and final outputs
- score the run and persist a report

Suggested module layout:

- `redis_sre_agent/evaluation/runtime.py`
- `redis_sre_agent/evaluation/scenarios.py`
- `redis_sre_agent/evaluation/tool_mocks.py`
- `redis_sre_agent/evaluation/knowledge_backend.py`
- `redis_sre_agent/evaluation/runner.py`
- `redis_sre_agent/evaluation/reporting.py`

The existing `redis_sre_agent/evaluation/` package should be extended rather than creating a second
top-level eval namespace.

The runtime must support two execution lanes:

- `full_turn`
  - wraps the production turn/task entrypoint
  - preserves router selection, `TurnScope`, target binding, and compatibility entrypoints
  - used for “real loop” evals and routing evals
- `agent_only`
  - calls a specific agent runtime directly with prebuilt context
  - used for narrower prompt/tool-behavior tests where routing/turn orchestration is not under test

Scenarios must declare which lane they require.

## 2. Virtualize tools at the provider boundary

The eval runtime should preserve production tool names and descriptions while replacing execution.

Required behavior:

- the agent sees the same tool schemas it would see in production
- tool invocation still flows through the normal tool-call path
- returned payloads come from scenario fixtures instead of live systems
- each tool can be stateful across turns and across repeated calls

Two virtualization modes are required.

### Mode A: in-process provider virtualization

Use this for fast unit/integration evals.

Mechanism:

- load a real provider class when possible
- keep its tool schemas
- replace tool execution with a scenario responder before tool objects are finalized, or replace the
  constructed `Tool.invoke` wrappers directly

This is the default for:

- Redis diagnostics tools
- Redis Enterprise admin tools
- host telemetry tools
- knowledge tools when running retrieval in mocked mode

### Mode B: fake MCP server virtualization

Use this when we need to exercise MCP discovery and tool-call integration end to end.

Mechanism:

- start an in-process or subprocess fake MCP server from the scenario
- advertise configured tools over MCP
- return scenario-bound outputs when the agent calls them

This is required for:

- metrics
- logs
- traces
- tickets
- repos
- utilities exposed via MCP

The eval system must support both modes because they answer different questions:

- Mode A isolates agent behavior cheaply
- Mode B verifies MCP discovery, naming, schema translation, and call plumbing

Mode B must be scenario-scoped. The eval runtime must not rely on mutating global
`settings.mcp_servers` for the whole process without an isolation story.

## 3. Normalize tool identities for scenarios and scoring

Scenarios must refer to tools through a stable logical identity, not the concrete runtime tool name.

Required fields:

- `provider_family`
- `operation`
- optional `target_handle`
- optional `server_name` for MCP tools

The eval runtime must map this logical identity onto:

- the concrete tool name shown to the model
- the concrete tool name recorded in traces
- the provider metadata needed for routing and scoring

This normalization layer is required for:

- fixture routing
- `required_tool_calls`
- `forbidden_tool_calls`
- reporting
- comparisons across runs with different target hashes or MCP server names

## 4. Add a declarative `EvalScenario` format

Each scenario should be a portable file set, preferably YAML plus supporting JSON/Markdown
fixtures.

Suggested top-level shape:

```yaml
id: enterprise-node-maintenance
name: Redis Enterprise node maintenance incident
description: Agent should discover maintenance-mode nodes and avoid OSS advice.

provenance:
  source_kind: redis_docs
  source_pack: redis-docs-curated
  source_pack_version: 2026-04-01
  derived_from: []
  synthetic:
    is_synthetic: false
  golden:
    expectation_basis: human_from_docs
    exemplar_sources: []
    review_status: approved

execution:
  lane: full_turn
  agent: redis_triage
  query: Investigate failovers on the prod enterprise cluster.
  route_via_router: true
  max_tool_steps: 8
  llm_mode: replay

scope:
  turn_scope:
    resolution_policy: require_target
    automation_mode: interactive
  target_catalog:
    - handle: tgt_cluster_prod_east
      kind: cluster
      resource_id: cluster-prod-east
      display_name: prod-east cluster
      cluster_type: redis_enterprise
      capabilities: [admin, diagnostics, metrics, logs]
  bound_targets:
    - tgt_cluster_prod_east

knowledge:
  mode: full
  version: latest
  pinned_documents:
    - fixtures/policies/sev1-escalation.md
  corpus:
    - fixtures/runbooks/re-node-maintenance.md
    - fixtures/skills/failover-investigation.md
    - fixtures/tickets/ret-4421.md

tools:
  redis_enterprise_admin:
    get_cluster_info:
      result: fixtures/tools/get_cluster_info.json
    list_nodes:
      result: fixtures/tools/list_nodes.json
    get_database:
      result: fixtures/tools/get_database.json
  mcp_servers:
    metrics_eval:
      capability: metrics
      tools:
        query_metrics:
          responders:
            - when:
                args_contains:
                  query: maintenance
              result: fixtures/tools/metrics-maintenance.json

expectations:
  required_tool_calls:
    - provider_family: redis_enterprise_admin
      operation: get_cluster_info
      target_handle: tgt_cluster_prod_east
    - provider_family: redis_enterprise_admin
      operation: list_nodes
      target_handle: tgt_cluster_prod_east
  forbidden_tool_calls:
    - provider_family: redis_command
      operation: config_set
  required_findings:
    - node maintenance mode is the likely cause of redistribution or failover
  forbidden_claims:
    - recommend CONFIG SET
    - claim INFO proves enterprise persistence configuration
  required_sources:
    - sev1-escalation
    - failover-investigation
```

Scenario files must support:

- inline fixture bodies for small cases
- referenced fixture files for large tool outputs and documents
- reusable shared fixtures
- per-scenario parameter overrides
- explicit logical tool identities instead of concrete runtime tool names
- target catalogs that compile into runtime `TurnScope` bindings
- provenance metadata for source pack, source version, derivation lineage, and golden lineage

Recommended provenance fields:

- `source_kind`: `redis_docs`, `support_ticket_export`, `synthetic`, or `mixed`
- `source_pack`: stable identifier for the scenario pack or export batch
- `source_pack_version`: version string, export date, or immutable snapshot identifier
- `derived_from`: source document ids, ticket ids, or prior scenario ids
- `synthetic.is_synthetic`: whether the scenario was generated or transformed
- `synthetic.method`: optional generator or distillation method identifier
- `synthetic.model`: optional model or pipeline version used to create synthetic content
- `golden.expectation_basis`: `human_from_docs`, `human_from_ticket`, `distilled_from_agent_trace`,
  `model_drafted_human_reviewed`, or similar
- `golden.exemplar_sources`: provenance for any exemplar answers or traces
- `golden.review_status`: `draft`, `reviewed`, or `approved`
- `golden.reviewed_by`: optional reviewer or owning team identifier

Target fixtures must compile into the existing target-binding system:

- public target match data for prompt/discovery context
- bound target handles and `TargetBinding` payloads
- provider load requests or synthetic instance/cluster objects as needed

That keeps attached-target behavior testable without inventing a second scope model.

## 5. Model three evidence planes independently

The eval system must separate three kinds of evidence because the product already uses them
differently.

### A. Tool evidence

Examples:

- Redis `INFO`, `SLOWLOG`, `CLIENT LIST`
- Redis Enterprise admin responses
- cluster-node listings
- Prometheus/Loki/MCP tool outputs

### B. Startup evidence

Examples:

- pinned policies
- pinned runbooks
- pinned skills
- startup tool instructions

This evidence is injected before the first model turn and should be tested independently from
retrieval.

### C. Retrieval evidence

Examples:

- `knowledge.search`
- `skills_check`
- `get_skill`
- support-ticket search and fetch

This evidence is discoverable by the agent and should be measured both as retrieval quality and
as downstream instruction-following quality.

## 6. Define explicit knowledge-access modes

The eval runner must support the following modes for every scenario:

- `disabled`
  - no pinned startup context
  - no knowledge tools
  - no retrieval-backed support-ticket tools
- `startup_only`
  - pinned context available
  - no retrieval tools after startup
- `retrieval_only`
  - no pinned startup context
  - retrieval tools enabled
- `full`
  - pinned startup context enabled
  - retrieval tools enabled
- `custom`
  - explicit per-surface enablement for advanced ablations

This is the minimum needed to answer “did the agent improve because of retrieval, because of
pinned context, or because of neither?”

Knowledge modes control only knowledge-backed surfaces:

- pinned startup documents and startup skill content
- knowledge provider tools
- retrieval-backed support-ticket tools exposed through the knowledge path

They do not automatically disable external MCP `tickets` tools. Those remain controlled by the
scenario’s tool-visibility configuration.

## 7. Provide a fixture-backed knowledge backend

We need a retrieval backend that requires no live Redis but still exercises the current semantics.

Required behavior:

- load documents, skills, runbooks, and support tickets from fixture files
- preserve document metadata:
  - `doc_type`
  - `category`
  - `priority`
  - `pinned`
  - `version`
  - `product_labels`
  - `name`
  - `summary`
- support the current helper behaviors:
  - pinned document loading
  - skill TOC generation
  - `get_skill`
  - support-ticket exact lookup
  - version filtering
  - doc-type filtering
  - precise-search behavior for quoted or exact-looking queries

Implementation choices:

- v1 may use a simple in-memory retrieval adapter backed by precomputed embeddings and metadata
- the adapter should expose the same response shapes as current helper functions
- it must accept the same user-visible parameters where practical
- startup-context code and helper functions must read through an injectable backend interface rather
  than calling live indices directly in eval mode

This backend is what powers both agent evals and retrieval-only evals.

Required implementation seam:

- production code keeps a default live backend
- eval runtime installs a scenario-scoped backend adapter for:
  - pinned document loading
  - startup skill lookup / TOC generation
  - knowledge search
  - skill fetch
  - support-ticket search and fetch

This should be done through a narrow adapter layer, not ad hoc conditional branches throughout the
agent code.

## 8. Add target fixture types for Redis instance and cluster scope

The eval system must support fixture-backed targets for:

- OSS single-instance Redis
- OSS cluster-linked database scenarios
- Redis Enterprise database scenarios
- Redis Enterprise cluster-only scenarios
- Redis Cloud database scenarios where relevant

Each target fixture should define:

- public metadata used for discovery and prompt context
- which provider families are exposed
- optional bound credentials or auth descriptors for fake authenticated providers
- scenario-specific tool payloads

This should reuse the existing target-binding system where possible so attached-target behavior is
also testable.

## 9. Add a fake observability catalog for MCP

We need a standard fake MCP suite that exposes representative observability tools without any real
backends.

Initial capability set:

- `metrics`
- `logs`
- `traces`
- `tickets`
- `repos`
- `utilities`

Each fake MCP tool must support:

- schema advertisement
- deterministic result payloads
- conditional responders based on args
- error and timeout injection
- optional latency simulation

This lets us test whether the agent:

- notices the right external tools are available
- chooses them when appropriate
- avoids them when knowledge or Redis-native tools are enough

The fake MCP catalog must be injectable per scenario run through the eval runtime, not just through
process-global settings.

## 10. Add stateful mock responders

Static one-shot outputs are not enough. Many useful scenarios require discovery across turns.

Examples:

- first `INFO memory` call shows high fragmentation, second call after a follow-up shows stable
  memory pressure
- first ticket search returns multiple candidates, then the agent fetches the correct ticket
- `list_nodes` exposes a maintenance-mode node only after cluster scope is resolved

Responders must support:

- exact tool operation matches
- argument-based branching
- call-count branching
- shared scenario state mutation
- injected failures:
  - timeout
  - auth error
  - rate limit
  - partial data
  - empty result

## Eval Suite Types

## 1. Prompt and policy evals

Purpose:

- validate system-prompt and startup-context behavior independent of live dependencies

Example questions:

- does `chat` stay iterative and avoid over-calling tools?
- does `redis_triage` batch tools and produce action-oriented output?
- does `chat` avoid pretending it has live access when only knowledge-backed sources are enabled?
- does the model obey pinned escalation policy text?

Primary metrics:

- instruction adherence
- prohibited-action avoidance
- prompt-specific behavioral checks
- tone/format requirements where they matter

## 2. Redis incident scenario evals

Purpose:

- validate behavior on realistic Redis states using mocked diagnostics

Coverage should include:

- memory pressure
- fragmentation
- hot keys
- slowlog anti-patterns
- client blocking
- persistence misconfiguration
- replication lag
- failover symptoms
- Redis Enterprise maintenance mode
- shard imbalance
- cluster admin/API vs OSS advice separation

Primary metrics:

- correct tool selection
- correct diagnosis
- correct prioritization
- safe recommendations

## 3. Source-following evals

Purpose:

- validate whether the agent follows pinned or retrieved operational guidance

Required scenario patterns:

- pinned policy overrides generic knowledge
- skill must be retrieved and then followed
- runbook must be retrieved and cited
- conflicting documents must be handled in deterministic precedence order

Expected precedence for eval scoring:

1. system prompt and hard safety constraints
2. pinned documents
3. retrieved skills and runbooks
4. general knowledge documents
5. model priors not grounded in scenario evidence

## 4. Knowledge ablation evals

Purpose:

- isolate what changes when knowledge surfaces are removed or added

For the same scenario, run at least:

- `disabled`
- `startup_only`
- `retrieval_only`
- `full`

Compare:

- answer quality
- tool behavior
- source usage
- citations
- final recommendations

## 5. Retrieval-only evals

Purpose:

- measure the retrieval layer without agent reasoning

Required coverage:

- general knowledge retrieval
- skill matching
- pinned-document loading
- support-ticket exact and semantic lookup
- version-filter behavior
- source-pack / dataset-version behavior
- doc-type filter behavior
- distance-threshold behavior
- exact / precise-query upgrade behavior
- helper-default semantic behavior

Primary metrics:

- Precision@K
- Recall@K
- MRR
- NDCG@K
- MAP
- exact-match hit rate
- source-type hit rate

## Metrics and Scoring

Every full-agent scenario should produce both structured assertions and judged scoring.

### Structured assertions

Use for hard requirements:

- required tool calls
- forbidden tool calls
- required sources
- forbidden claims
- required factual findings
- expected routing decision

### Rubric scoring

Use for softer judgment:

- technical correctness
- completeness
- actionability
- evidence use
- instruction-following quality
- citation quality

The existing `evaluation/judge.py` can be extended for this, but the judge must receive richer
context:

- startup context that was injected
- tool call trace
- retrieved source list
- final answer
- expectation set

## Reporting and Artifacts

Every eval run should emit a durable artifact bundle.

Minimum contents:

- scenario id and git SHA
- scenario provenance block
- agent type and model
- system prompt digest
- knowledge mode
- corpus or source-pack version
- tool trace
- retrieved source trace
- startup-context snapshot
- final answer
- structured assertion results
- judge scores
- overall pass/fail
- execution lane
- logical-to-concrete tool identity map
- LLM mode and baseline policy
- golden provenance and review status

Suggested output formats:

- JSON for machine consumption
- Markdown summary for local review

## CLI and Developer Workflow

Add a dedicated CLI entry group:

- `uv run redis-sre-agent eval run <scenario_or_suite>`
- `uv run redis-sre-agent eval compare <baseline> <candidate>`
- `uv run redis-sre-agent eval list`
- `uv run redis-sre-agent eval retrieval <suite>`

This should be integrated into the existing Click CLI registration flow rather than introduced as an
isolated secondary CLI surface.

Useful flags:

- `--agent`
- `--knowledge-mode`
- `--model`
- `--scenario-dir`
- `--report-dir`
- `--fail-fast`
- `--update-baseline`
- `--filter`

## Initial Suite Inventory

The first committed suite should include at least:

1. `prompt/chat-iterative-tool-use`
2. `prompt/knowledge-agent-no-live-access`
3. `redis/memory-pressure-oss`
4. `redis/slowlog-anti-pattern`
5. `redis/enterprise-maintenance-mode`
6. `redis/enterprise-cluster-health-vs-info-misread`
7. `sources/pinned-sev1-escalation-policy`
8. `sources/retrieve-failover-skill-and-follow-it`
9. `sources/runbook-overrides-generic-advice`
10. `retrieval/general-knowledge-core`
11. `retrieval/skills-core`
12. `retrieval/support-ticket-exact-match`

## Phased Implementation Plan

## Phase 0: Contract alignment

- define the scenario schema
- define the report schema
- decide the authoritative fixture directory layout
- define logical tool identity normalization
- define the execution lanes (`full_turn` vs `agent_only`)

## Phase 1: Full-turn harness and runtime seams

- add `EvalRuntime`
- add a `full_turn` harness around the production turn entrypoint
- add an `agent_only` harness for narrower tests
- add scenario-scoped backend/config injection hooks for knowledge and MCP

## Phase 2: Knowledge backend virtualization

- add fixture-backed document and skill corpus loading
- add `disabled`, `startup_only`, `retrieval_only`, `full` knowledge modes
- ensure startup-context and retrieval helpers use the eval backend in eval mode

## Phase 3: Tool virtualization

- add `EvalRuntime`
- add in-process mock responders for Redis and admin providers
- make it possible to run existing agents with mocked tool execution

## Phase 4: Fake MCP integration

- add a fake MCP server/runtime
- support scenario-defined MCP tools and outputs
- add MCP-focused evals

## Phase 5: Scoring and reporting

- integrate structured assertions
- extend the judge context
- emit JSON and Markdown reports

## Phase 6: Initial scenario corpus

- land the initial suites listed above
- add golden expectations and comparison workflow

## Phase 7: CI integration

- run a deterministic subset in PR CI
- reserve live-model evals for scheduled or manually triggered runs
- document baseline update rules and acceptable variance bands

## Risks and Open Questions

### 1. Fidelity versus speed

If mocks are too shallow, evals become misleading. If they are too faithful, authoring becomes
slow and brittle. v1 should prefer realistic payloads for high-value scenarios rather than broad
but shallow coverage.

### 2. Retrieval fidelity

An in-memory retrieval backend may not perfectly match RedisVL behavior. That is acceptable for
unit-speed evals, but we should reserve the option to add a second mode that runs against an
ephemeral local Redis 8 container for retrieval parity checks.

### 3. Prompt drift

Because prompts are loaded from code, prompt changes may invalidate older baselines. Reports must
include prompt digests so regressions can be attributed cleanly.

### 4. Judge dependence

LLM-as-judge is useful but not sufficient. Hard assertions must remain the primary signal for
safety and instruction-following regressions.

### 5. Determinism

PR-facing evals should not depend on live, drifting model behavior. The runtime must support:

- `replay` mode for deterministic model outputs
- `stub` mode for narrow harness tests
- `live` mode only for manual or scheduled suites unless explicitly waived

Reports must record the exact model configuration or replay artifact used.

## Acceptance Criteria

This spec is satisfied when the repository can:

- run agent evals with no live Redis, no live Redis Enterprise cluster, and no live MCP servers
- expose scenario-controlled Redis, cluster, and MCP tool outputs to the LLM
- run the same scenario under multiple knowledge modes
- verify pinned-doc, skill, and runbook following behavior
- run retrieval-only evals on the same source fixtures
- emit reproducible reports that explain regressions with prompt, tool, and source traces

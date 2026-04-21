# Formal Skills Protocol Support Spec

Status: Proposed

Related:
- `docs/how-to/source-document-features.md`
- `specs/eval-fixture-layout-spec.md`

## Summary

Add first-class support for directory-backed skills that follow the formal skill protocol:

```text
skill-name/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
├── references/
└── assets/
```

Today `redis-sre-agent` only supports "skills" as indexed markdown documents. That works for
short procedural text, but it cannot model packaged resources, deterministic scripts, or
progressive disclosure via `references/`.

This spec proposes a Redis-first model:

- keep existing document-backed skills for backward compatibility
- add package discovery and parsing for formal skill directories during ingestion
- ingest the full text portion of each skill package into `sre_skills` so skills remain searchable
  and distributable through Redis
- extend the knowledge tool surface so the agent can inspect packaged references and execute
  packaged scripts without relying on persistent filesystem access at runtime
- teach eval corpora to load directory-backed skills in addition to legacy `skills/*.md`

## Problem

The current repo treats a skill as a single markdown document with front matter. The relevant
implementation seams are:

- startup context only renders a skill TOC from `skills_check` results and has no notion of
  references or scripts: `redis_sre_agent/agent/knowledge_context.py:49-59`,
  `redis_sre_agent/agent/knowledge_context.py:251-272`
- `skills_check_helper()` and `get_skill_helper()` read only from the indexed `skills` corpus:
  `redis_sre_agent/core/knowledge_helpers.py:662-819`,
  `redis_sre_agent/core/knowledge_helpers.py:822-940`
- the knowledge tool provider exposes only `skills_check` and `get_skill`; there is no tool for
  packaged references or packaged scripts:
  `redis_sre_agent/tools/knowledge/knowledge_base.py:216-275`
- source ingestion only turns standalone markdown files into `ScrapedDocument` objects:
  `redis_sre_agent/pipelines/ingestion/processor_source_helpers.py:179-240`
- eval corpus loading assumes `skills/` contains files, not packages with resources:
  `redis_sre_agent/evaluation/knowledge_backend.py`

That means the repo cannot support a skill like:

- `SKILL.md` with concise workflow instructions
- `references/redis-cloud.md` for details loaded only when needed
- `scripts/capture_diagnostics.py` for deterministic execution
- `agents/openai.yaml` for UI metadata

## Goals

- Support discovery of directory-backed skill packages from one or more configured ingestion roots.
- Keep formal skills searchable in Redis.
- Keep current document-backed skill retrieval working without migration pressure.
- Make the full text portion of a skill package available through Redis-backed retrieval and
  tool calls, not persistent local filesystem reads.
- Let the agent read `references/` and script sources on demand from Redis instead of inlining
  everything into `SKILL.md`.
- Let the agent execute packaged `scripts/` safely and deterministically after reconstructing
  an ephemeral runtime bundle from Redis.
- Support the same package format inside `evals/corpora/.../skills/`.
- Keep binary assets out of the vector index.
- Reuse the existing source-document deduplication and tracked-source cleanup procedures instead of
  introducing skill-specific duplicate handling.

## Non-goals

- Replacing general knowledge search or support-ticket retrieval.
- Indexing binaries or arbitrary asset content into Redis.
- Allowing arbitrary shell execution outside packaged skill scripts.
- Designing a remote skill marketplace or installer flow.
- Forcing all legacy skill markdown files to convert immediately.

## Current-State Observations

### 1. Skills are retrieval documents, not packages

The repo's current skill flow is optimized for semantic retrieval:

- `skills_check` returns `name`, `summary`, and a few metadata fields from the skills index.
- `get_skill` reconstructs the full markdown content from indexed fragments.
- startup prompt injection only adds a TOC, not a package manifest.

This is the right shape for corpus documents, but not for a protocol whose core value is:

- resource directories
- scripts
- optional UI metadata
- progressive disclosure via `references/`

### 2. Ingestion and eval layout are file-oriented

Production source parsing and eval fixture loading both assume a skill is a single file. That is
why package-local `references/*.md` or `scripts/*.py` would either be ignored or accidentally
treated as ordinary documents unless the loader becomes skill-package-aware.

### 3. The agent has no script execution primitive for skills

Even if we could discover a `scripts/` directory, the current tool surface gives the model no
safe way to invoke a packaged script. Supporting the formal protocol requires more than parsing
`SKILL.md`; it requires a runtime contract for package resources.

## Proposed Design

## 1. Treat the directory protocol as an ingestion format, not a runtime dependency

Add a new package:

```text
redis_sre_agent/skills/
├── __init__.py
├── models.py
├── discovery.py
├── catalog.py
├── bundle_runtime.py
└── runner.py
```

Core models:

- `SkillPackage`
- `SkillMetadata`
- `SkillReference`
- `SkillScript`
- `SkillAsset`
- `SkillProtocol = "formal_v1" | "legacy_markdown"`
- `SkillResourceKind = "entrypoint" | "reference" | "script" | "asset"`

Discovery rules for a package skill:

- a directory qualifies as a skill package if it contains `SKILL.md`
- `SKILL.md` must contain front matter with `name` and `description`
- `agents/openai.yaml` is optional and parsed only when present
- `references/`, `scripts/`, and `assets/` are optional
- all resource paths are stored relative to the skill root

Recommended roots:

- production/dev: new configurable `skills/` root at repo top level
- evals: existing `evals/corpora/<pack>/<version>/skills/`

At runtime, the agent should not depend on these roots being mounted. They are ingestion inputs
only. The canonical runtime source of truth remains Redis, matching the rest of the repo's
knowledge distribution model.

## 2. Ingest the full skill package into `sre_skills`

Formal skill packages should be expanded into Redis documents during ingestion.

Model each package as a grouped set of skill resources:

- one entrypoint resource for `SKILL.md`
- zero or more reference resources for text files under `references/`
- zero or more script resources for text files under `scripts/`
- zero or more text asset resources when assets are plain text and below size limits
- metadata-only asset records for binary or non-indexable assets

All text resources should be searchable through Redis so a query can match:

- the main `SKILL.md`
- a detail that only appears in a reference
- a helper name or usage note that only appears in a script
- a text asset when that asset is ingestible

Search results should still collapse to one skill row per `skill_name`, but ranking may use the
best matching resource within the package.

### Schema extensions

Extend `SRE_SKILLS_SCHEMA` in `redis_sre_agent/core/redis.py` with skill-package metadata fields:

- `skill_protocol`: `legacy_markdown | formal_v1`
- `resource_kind`: `entrypoint | reference | script | asset`
- `resource_path`
- `mime_type`
- `encoding`
- `package_hash`
- `entrypoint`: `true | false`
- `has_references`
- `has_scripts`
- `has_assets`

All resources stay in `sre_skills`; do not create a second skill-resource index in v1.

### Ingestion behavior

Update the ingestion pipeline so a discovered skill package produces multiple `ScrapedDocument`
records with shared package metadata.

Deduplication and source tracking must follow the same path already used for other knowledge
documents:

- each package resource gets a stable `source_document_path`, for example:
  - `skills/<skill-name>/SKILL.md`
  - `skills/<skill-name>/references/<file>`
  - `skills/<skill-name>/scripts/<file>`
- each resource is indexed through the existing `skill` deduplicator and
  `replace_source_document_chunks()` flow, using the same `content_hash` and tracked-source
  semantics as current knowledge documents
- repeated ingests of an unchanged package must be no-ops at the resource level
- removed resources must be deleted through the existing tracked-source cleanup path
- no separate package-registry dedup state should be introduced

Search-time ranking should then collapse the resource-level matches back to a single skill:

- exact name match first
- then best-match resource score within the package
- then stable alphabetical tie-break

This keeps formal skills fully searchable in Redis and aligned with the repo's existing
"ingest once, retrieve anywhere" model.

## 3. Add a Redis-backed skill catalog abstraction

Today the code reaches directly into Redis-backed helpers for skill lookup. Keep Redis as the
runtime backing store, but introduce a catalog layer so the logic becomes package-aware without
spreading resource-aggregation code across the repo.

Suggested interface:

```python
class SkillCatalog(Protocol):
    async def list_skills(self, *, query: str | None, limit: int, offset: int, version: str | None) -> dict: ...
    async def get_skill(self, *, skill_name: str, version: str | None) -> dict: ...
    async def get_skill_resource(self, *, skill_name: str, resource_path: str, version: str | None) -> dict: ...
    async def run_script(self, *, skill_name: str, script_path: str, args: list[str], stdin: str | None) -> dict: ...
```

Implementation plan:

- `RedisSkillCatalog` becomes the default production path
- eval backends implement the same logical contract without requiring live Redis
- package parsing remains an ingestion concern, not a runtime concern

## 4. Extend the skill tool surface

Keep the existing tool names for compatibility, but change their backing implementation to use the
new Redis-backed catalog.

### `skills_check`

Extend the result shape with package metadata:

- `source_kind`: `redis`
- `protocol`: `formal_v1 | legacy_markdown`
- `has_references`
- `has_scripts`
- `has_assets`
- `matched_resource_kind`
- `matched_resource_path`

The startup TOC in `build_startup_knowledge_context()` should continue to stay compact, but it
should source data from the package-aware Redis catalog instead of the current document-only helper.

### `get_skill`

Preserve the existing `full_content` field, but make package skills aggregate all Redis-backed
resources belonging to the package. Return a compact manifest plus optional inline previews:

```json
{
  "skill_name": "iterative-redis-triage",
  "source_kind": "redis",
  "protocol": "formal_v1",
  "full_content": "...SKILL.md body...",
  "description": "Use a diagnostic sequence that narrows the problem before changing configuration.",
  "references": [
    {"path": "references/memory.md", "title": "Memory triage", "summary": "When to read this file"}
  ],
  "scripts": [
    {"path": "scripts/capture_diagnostics.py", "description": "Collect read-only diagnostics"}
  ],
  "assets": [
    {"path": "assets/checklist.md"}
  ],
  "ui_metadata": {
    "display_name": "Iterative Redis Triage"
  }
}
```

For legacy markdown skills, return the same payload shape but with empty `references`, `scripts`,
and `assets`.

Important: formal package resources should be retrievable from Redis even if the original
filesystem package is no longer mounted.

### Add `get_skill_resource`

New knowledge tool:

- input: `skill_name`, `resource_path`
- output: `skill_name`, `resource_path`, `resource_kind`, `content`, `truncated`, `mime_type`

Rules:

- supports references, scripts, and text assets
- resource lookup is served from Redis metadata, not direct disk access
- text-only in v1
- apply a content budget similar to pinned-doc startup budgets

### Add `run_skill_script`

New knowledge or utilities tool:

- input: `skill_name`, `script_path`, `args`, optional `stdin`, optional `timeout_seconds`
- output: `exit_code`, `stdout`, `stderr`, `truncated`, `duration_ms`

Rules:

- `script_path` must resolve to a Redis-backed script resource in the skill package
- runtime reconstructs an ephemeral temp directory from the skill bundle stored in Redis
- the temp directory includes at minimum the requested script and any sibling script files
  required for relative imports
- default timeout comes from config
- stdout/stderr are size-limited and marked when truncated
- return structured errors for missing script, timeout, non-zero exit, and invalid interpreter

This is the critical addition that makes formal skills materially more useful than the current
retrieval-only markdown documents.

## 5. Add runtime configuration and safety controls

Add settings in `redis_sre_agent/core/config.py`:

- `skill_roots: list[str]`
- `skill_reference_char_budget: int = 12000`
- `enable_skill_scripts: bool = False`
- `skill_script_timeout_seconds: int = 30`
- `skill_script_max_output_bytes: int = 32768`

Behavior:

- package discovery is enabled during ingestion when one or more `skill_roots` exist
- packaged script execution is separately gated by `enable_skill_scripts`
- when script execution is disabled, `run_skill_script` returns a structured blocked result

If the approval/resume work lands first, classify `run_skill_script` as `unknown` or `write`
until per-script safety policy exists. The safe default is to require explicit enablement.

## 6. Make startup context package-aware

Update `redis_sre_agent/agent/knowledge_context.py` so startup grounding uses the package-aware
Redis catalog.

Behavior changes:

- the skill TOC can include both package skills and legacy indexed skills
- package skills should use `description` when `summary` is absent
- no package reference content is injected at startup
- no script content is injected at startup

This preserves the current compact startup prompt shape while making package skills discoverable.

## 7. Teach eval corpora to load package skills

Extend `evals/corpora/<pack>/<version>/skills/` to support both:

- legacy: `skills/<name>.md`
- formal: `skills/<skill-name>/SKILL.md`

Eval loader changes:

- update `redis_sre_agent/evaluation/knowledge_backend.py` to treat a directory with `SKILL.md`
  as one skill package with multiple Redis-like resources
- expose eval-only implementations for `get_skill_resource` and `run_skill_script`
- allow scripted eval fixtures to return deterministic output without needing live shell access

This keeps mocked evals deterministic while still exercising the same agent-facing protocol.

## 8. Keep backward compatibility for existing skill documents

Legacy `doc_type: skill` markdown documents should continue to work unchanged.

Compatibility rules:

- `skills_check` returns both protocols from the same Redis index
- exact package skill name wins over legacy document on `get_skill`
- callers can distinguish protocols via `protocol`
- a future migration can convert selected legacy skills into packages incrementally

This is important because the repo already contains:

- `source_documents/...` skill markdown
- `evals/corpora/.../skills/*.md`
- tests that assume indexed markdown skills

## File and Module Changes

Expected code touch points:

- new: `redis_sre_agent/skills/models.py`
- new: `redis_sre_agent/skills/discovery.py`
- new: `redis_sre_agent/skills/catalog.py`
- new: `redis_sre_agent/skills/bundle_runtime.py`
- new: `redis_sre_agent/skills/runner.py`
- update: `redis_sre_agent/core/config.py`
- update: `redis_sre_agent/core/redis.py`
- update: `redis_sre_agent/core/runtime_overrides.py`
- update: `redis_sre_agent/core/knowledge_helpers.py`
- update: `redis_sre_agent/pipelines/ingestion/processor_source_helpers.py`
- update: `redis_sre_agent/pipelines/ingestion/document_processor.py`
- update: `redis_sre_agent/tools/knowledge/knowledge_base.py`
- update: `redis_sre_agent/agent/knowledge_context.py`
- update: `redis_sre_agent/evaluation/knowledge_backend.py`
- update: docs under `docs/how-to/`

## Suggested API Shapes

### Package skill list item

```json
{
  "name": "iterative-redis-triage",
  "title": "Iterative Redis Triage",
  "summary": "Use a diagnostic sequence that narrows the problem before changing configuration.",
  "source_kind": "redis",
  "protocol": "formal_v1",
  "has_references": true,
  "has_scripts": true,
  "has_assets": false,
  "matched_resource_kind": "script",
  "matched_resource_path": "scripts/capture_diagnostics.py"
}
```

### Resource read result

```json
{
  "skill_name": "iterative-redis-triage",
  "resource_path": "references/memory.md",
  "resource_kind": "reference",
  "content": "...",
  "truncated": false,
  "mime_type": "text/markdown"
}
```

### Script run result

```json
{
  "skill_name": "iterative-redis-triage",
  "script_path": "scripts/capture_diagnostics.py",
  "exit_code": 0,
  "stdout": "...",
  "stderr": "",
  "duration_ms": 842,
  "truncated": false
}
```

## Rollout Plan

### Phase 1: Read-only package support

- add package discovery and package-to-Redis ingestion
- extend `sre_skills` schema
- add Redis-backed catalog aggregation
- route `skills_check` and `get_skill` through the catalog
- add `get_skill_resource`
- update startup context
- update eval fixture loading

This phase delivers searchable, Redis-distributed formal skills except for execution.

### Phase 2: Script execution

- add `run_skill_script`
- add config gate and limits
- add eval/runtime overrides
- add approval classification once tool action policy is in place

### Phase 3: Tooling and migration helpers

- add CLI commands such as `redis-sre-agent skills list`, `show`, `read-reference`, `run-script`
- add a repo-local example package under a new top-level `skills/`
- optionally add a helper script to convert a legacy markdown skill into a package skeleton

## Testing

Add or update tests in these areas:

- discovery of package skills from configured roots
- ingestion of multi-resource skill packages into `sre_skills`
- repeated-ingest no-op behavior for unchanged skill resources
- tracked-source cleanup when a package resource is removed or renamed
- collapse and ranking when a query matches a reference or script resource
- `get_skill` manifest shape for both protocols
- `get_skill_resource` retrieval and truncation handling
- `run_skill_script` happy path, timeout, missing file, and non-zero exit
- startup context still stays compact and includes package skill summaries
- eval corpus loading for `skills/<name>/SKILL.md`
- backward compatibility for existing `skills/*.md` fixtures

## Open Questions

- Should text assets be indexed by default, or only when explicitly marked ingestible?
- Should `run_skill_script` live under the knowledge provider or a separate local-exec provider?
- Do we want per-script metadata in `SKILL.md` or `agents/openai.yaml`, or is directory discovery
  enough for v1?
- Should package skill assets ever be exposed to the model directly, or only to downstream UI/CLI
  consumers?

## Recommendation

Implement Phase 1 first. It is the smallest change that actually supports the formal protocol:

- package directory discovery
- package-to-Redis ingestion
- searchable `SKILL.md`, `references/`, and script sources
- package-aware `skills_check` / `get_skill`
- eval fixture support

Then add `run_skill_script` behind an explicit config gate. That sequencing preserves the current
retrieval model, keeps Redis as the distribution plane for the entire skill, and adds execution
only after the search and retrieval story is coherent.

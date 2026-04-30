# Eval Fixture Layout

Status: Proposed

## Purpose

This document defines the authoritative on-disk layout for mocked eval fixtures.
It is intentionally limited to directory structure, reserved filenames, and
relative-reference conventions. It does not redefine the scenario schema or the
execution-lane contract.

## Root

Committed eval fixtures live under:

```text
evals/fixtures/
```

The top-level tree is:

```text
evals/fixtures/
  scenarios/
  shared/
  corpora/
  goldens/
```

## Scenario Bundles

Each scenario owns a bundle directory:

```text
evals/fixtures/scenarios/<suite>/<scenario_id>/
  scenario.yaml
  fixtures/
    tools/
    startup/
    retrieval/
```

Rules:

- `scenario.yaml` is the canonical scenario manifest filename.
- Scenario-local payloads stay under the sibling `fixtures/` tree.
- Existing relative refs such as `fixtures/tools/get_cluster_info.json` remain valid.
- Bundle directories are suite-scoped, so scenario ids only need to be unique inside a suite.

Example:

```text
evals/fixtures/scenarios/redis/enterprise-maintenance-mode/
  scenario.yaml
  fixtures/
    tools/get_cluster_info.json
    tools/list_nodes.json
```

## Shared Fixtures

Reusable assets that should not be copied into every scenario live under:

```text
evals/fixtures/shared/
  policies/
  runbooks/
  skills/
  tools/
  startup/
```

Because the current scenario loader resolves relative paths from the scenario file directory,
shared references from a scenario bundle use the prefix:

```text
../../../shared/
```

Example:

```yaml
pinned_documents:
  - ../../../shared/policies/sev1-escalation.md
```

## Corpora

Fixture-backed corpora are versioned by source pack and source-pack version:

```text
evals/fixtures/corpora/<source_pack>/<source_pack_version>/
  metadata.yaml
  documents/
  skills/
  tickets/
```

Rules:

- `metadata.yaml` stores pack-level provenance and ingestion metadata.
- `documents/`, `skills/`, and `tickets/` are the reserved first-level corpus categories.
- Scenario refs into a corpus use the relative prefix:

```text
../../../corpora/
```

Example:

```yaml
knowledge:
  corpus:
    - ../../../corpora/redis-docs-curated/2026-04-01/documents/re-node-maintenance.md
    - ../../../corpora/redis-docs-curated/2026-04-01/skills/failover-investigation.md
```

## Golden Data

Golden artifacts are stored separately from scenario manifests so exemplar answers and traces can
evolve without rewriting scenario-local tool fixtures:

```text
evals/fixtures/goldens/<suite>/<scenario_id>/
  answer.md
  trace.json
  notes.md
```

Reserved filenames:

- `answer.md`: human-authored or reviewed exemplar answer text
- `trace.json`: optional exemplar trace, cited evidence, or structured baseline
- `notes.md`: reviewer notes or change history

The scenario provenance block remains the source of truth for golden review status and lineage.
This layout only defines where supplemental golden files live.

## Contract Summary

- Authoritative root: `evals/fixtures/`
- Scenario manifest: `evals/fixtures/scenarios/<suite>/<scenario_id>/scenario.yaml`
- Scenario-local payloads: `.../fixtures/...`
- Shared fixture prefix from scenario bundles: `../../../shared/`
- Corpus prefix from scenario bundles: `../../../corpora/`
- Golden artifact directory: `evals/fixtures/goldens/<suite>/<scenario_id>/`

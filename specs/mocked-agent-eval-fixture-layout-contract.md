# Mocked Agent Eval Fixture Layout Contract

Status: Proposed

This document defines the authoritative on-disk layout for mocked eval inputs and generated
artifacts. It is intentionally limited to path layout and placement rules. It does not redefine
the scenario YAML schema, execution lanes, or report payload schema.

## Goals

- Keep committed eval inputs in one stable repo root.
- Separate reusable shared fixtures from scenario-local one-offs.
- Keep committed golden baselines separate from generated run artifacts.
- Make scenario ids map mechanically onto fixture, golden, and artifact paths.

## Authoritative Roots

Committed eval inputs and committed baselines live under:

```text
eval_fixtures/
```

Generated run outputs live under:

```text
.artifacts/evals/
```

Generated artifacts must never be written back into `eval_fixtures/`.

## Scenario Layout

Every scenario id maps to a directory under:

```text
eval_fixtures/scenarios/<suite>/<scenario_slug>/
```

Each scenario directory contains exactly one canonical scenario file:

```text
eval_fixtures/scenarios/<suite>/<scenario_slug>/scenario.yaml
```

Scenario-local binary or large supporting files live under:

```text
eval_fixtures/scenarios/<suite>/<scenario_slug>/fixtures/
```

Use scenario-local fixtures only when the file is specific to that scenario and is not intended
for reuse.

## Shared Fixture Layout

Reusable committed fixtures live under:

```text
eval_fixtures/shared/documents/
eval_fixtures/shared/skills/
eval_fixtures/shared/runbooks/
eval_fixtures/shared/tickets/
eval_fixtures/shared/tool_payloads/
eval_fixtures/shared/corpora/
```

Use these directories as follows:

- `documents/`: pinned policies, general docs, and reusable narrative source material
- `skills/`: startup or retrieved skill content
- `runbooks/`: reusable runbook documents
- `tickets/`: support-ticket fixture content
- `tool_payloads/`: JSON or text payloads returned by mocked tools
- `corpora/`: higher-level corpora or source-pack directories referenced by multiple scenarios

## Golden Baselines

Committed goldens live under:

```text
eval_fixtures/goldens/<suite>/<scenario_slug>/
```

This directory is for committed expectations and baselines only. The exact file schema for golden
JSON or Markdown is defined separately by the report-schema slice.

## Generated Artifact Placement

Generated run artifacts live under:

```text
.artifacts/evals/<run_id>/<suite>/<scenario_slug>/
```

This directory is where the eval runner writes per-run report bundles, traces, and any expanded
materialized outputs. The exact JSON and Markdown payload shapes are defined separately by the
report-schema slice.

## Path Rules

- Scenario ids are relative slash-delimited ids such as `prompt/chat-iterative-tool-use`.
- Scenario ids must not be absolute and must not contain `.` or `..` path segments.
- `run_id` values are also relative path-safe ids.
- Scenario YAML should reference committed fixtures relative to the repo and should prefer files
  under `eval_fixtures/`.

## Code Contract

The corresponding path helpers live in:

```text
redis_sre_agent/evaluation/fixture_layout.py
```

That module is the authoritative code contract for turning scenario ids and run ids into fixture,
golden, and artifact directories.

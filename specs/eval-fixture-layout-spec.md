# Eval Fixture Layout

Status: Proposed

## Goal

Define one authoritative on-disk layout for mocked eval inputs and goldens without changing the
scenario schema or execution-lane contract.

This slice owns only filesystem organization:

- scenario YAML manifests
- scenario-local fixtures
- shared fixtures
- versioned corpora
- golden expectations

It does not redefine `EvalScenario`, execution lanes, or report payload schemas.

## Root Layout

All mocked eval assets live under `evals/`:

```text
evals/
  scenarios/
    _shared/
      startup/
      tools/
    <suite>/
      <scenario_id>/
        scenario.yaml
        fixtures/
          startup/
          tools/
  corpora/
    <source_pack>/
      <version>/
        manifest.yaml
        documents/
        skills/
        tickets/
  goldens/
    <suite>/
      <scenario_id>/
        metadata.yaml
        expected.md
        assertions.json
```

## Contract

### 1. Scenario manifests

Canonical path:

```text
evals/scenarios/<suite>/<scenario_id>/scenario.yaml
```

Rules:

- each scenario owns a dedicated directory
- scenario-local relative references remain stable because the manifest and its local fixtures live
  together
- suite and scenario ids are path segments only; no empty values or `..` traversal

### 2. Scenario-local fixtures

Canonical path:

```text
evals/scenarios/<suite>/<scenario_id>/fixtures/
```

Subdirectories reserved in v1:

- `fixtures/tools/` for scenario-specific tool payloads and responder outputs
- `fixtures/startup/` for scenario-specific pinned docs or startup-only assets

Scenario YAML should prefer local references for data unique to one scenario:

- `fixtures/tools/get_cluster_info.json`
- `fixtures/startup/sev1-escalation.md`

### 3. Shared fixtures

Canonical path:

```text
evals/scenarios/_shared/
```

Subdirectories reserved in v1:

- `_shared/tools/`
- `_shared/startup/`

Shared fixtures stay under `scenarios/` on purpose so every scenario can reach them with the same
relative prefix from its manifest:

```text
../../_shared/<category>/...
```

Examples:

- `../../_shared/tools/metrics/maintenance.json`
- `../../_shared/startup/policies/sev1.md`

This avoids introducing a second path-resolution rule beyond plain relative filesystem paths.

### 4. Versioned corpora

Canonical path:

```text
evals/corpora/<source_pack>/<version>/
```

Required contents:

- `manifest.yaml`
- `documents/`
- `skills/`
- `tickets/`

Rules:

- corpora are versioned by `source_pack` and `version`, not by suite
- corpora are not mixed into per-scenario fixture directories
- scenario provenance should point to the pack/version; retrieval fixtures then resolve into this
  corpus tree

### 5. Goldens

Canonical path:

```text
evals/goldens/<suite>/<scenario_id>/
```

Required files in v1:

- `metadata.yaml`
- `expected.md`
- `assertions.json`

Rules:

- goldens live outside scenario input directories so inputs and expected outputs stay separate
- `metadata.yaml` carries review and provenance details for the golden bundle
- report-schema work may extend the golden payload, but should not move the directory contract

## Naming Guidance

- use kebab-case for `suite`, `scenario_id`, `source_pack`, and versioned fixture filenames
- keep suite names semantic (`prompt`, `redis`, `sources`, `retrieval`)
- reserve `_shared/` as the only leading-underscore directory in `evals/scenarios/`

## Implementation Hook

The path contract is implemented in:

- `redis_sre_agent.evaluation.fixture_layout`

That module should remain the authoritative source for canonical fixture locations and any future
loader code should route through it rather than hardcoding path strings.

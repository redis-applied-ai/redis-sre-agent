# Eval Fixture Layout Contract

Status: Proposed

This document defines the authoritative on-disk layout for eval scenario files and reusable
fixtures. It is intentionally limited to directory structure and fixture resolution rules.
It does not define the scenario schema, execution lanes, or report file schema.

## Root

All eval fixtures live under:

```text
tests/fixtures/evals/
```

This keeps scenario inputs, shared corpora, and goldens in a test-owned tree and separates them
from runtime reports under `tests/eval_reports/`.

## Layout

```text
tests/fixtures/evals/
  scenarios/
    <suite>/
      <scenario_id>/
        scenario.yaml
        fixtures/
          ...
  shared/
    corpora/
      <source_pack>/
        <version>/
          docs/
          runbooks/
          skills/
          tickets/
    tools/
      <provider_family>/
        <operation>/
          ...
  goldens/
    <suite>/
      <scenario_id>/
        ...
```

## Contract

- `scenarios/<suite>/<scenario_id>/scenario.yaml` is the only authoritative scenario entrypoint.
- `scenarios/<suite>/<scenario_id>/fixtures/` holds scenario-local assets referenced by that
  scenario only.
- `shared/corpora/<source_pack>/<version>/...` holds reusable knowledge fixtures. The layout
  reserves stable versioned directories for docs, runbooks, skills, and tickets.
- `shared/tools/<provider_family>/<operation>/...` holds reusable mocked tool payloads shared by
  multiple scenarios.
- `goldens/<suite>/<scenario_id>/` is the reserved root for curated golden data and baselines for
  that scenario.

## Fixture References

Scenario YAML files may reference fixtures in two ways:

- `fixtures/...`
  Resolves relative to the owning scenario directory.
- `shared/...`
  Resolves from the shared fixture root under `tests/fixtures/evals/shared/`.

Other relative paths are resolved from the scenario directory, but all resolved paths must stay
within `tests/fixtures/evals/`.

## Non-goals

- Defining the shape of `scenario.yaml`
- Defining golden file names or report JSON schemas
- Defining runtime artifact output locations

Those belong to the scenario-schema and report-schema slices.

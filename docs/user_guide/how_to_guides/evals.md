---
description: Run the eval harness against the agent.
---

# Evals

Run the eval harness when you change a prompt, swap a model, or add a tool
and need to know whether the agent's behavior actually improved. Two
entry points are available: deterministic mocked scenarios for
regression testing, and live-model suite runs for periodic baseline
checks. Mocked scenarios run in pytest and are safe for CI; live runs hit
real LLM endpoints and cost money, so reach for them when you need a
real-world signal.

**Related:** [Triage loop (concept)](../../concepts/triage_loop.md) ·
[CLI reference](../../api/cli_ref.md)

Redis SRE Agent includes a scenario-driven eval system under `evals/` and `redis_sre_agent/evaluation/`.
The CLI exposes scenario listing, one-off mocked-scenario execution, live-suite execution, and
baseline comparison. For deterministic regression coverage, prefer the pytest-backed mocked eval
suite; `eval run` is best for interactive debugging and ad hoc inspection.

## Terms Used In This Guide

This page uses `policy` in two different ways:

- A `policy document` is just a written rule or instruction that the agent can read during a scenario, such as "do not run destructive commands" or "escalate Sev 1 incidents immediately."
- The `baseline policy` in `evals/baseline_policy.yaml` is configuration for live eval suites. It says when a suite is allowed to run, when it is allowed to update a stored baseline, and how much score drift is acceptable when comparing a new run against that baseline.

When this guide says `policy file`, it means the live-suite baseline policy. When it says a scenario includes a `policy`, it means a document in the scenario's knowledge inputs.

## What Lives Where

- `evals/scenarios/`: scenario manifests grouped by lane or topic.
- `evals/corpora/`: versioned docs, skills, and ticket packs used by scenarios.
- `evals/goldens/`: expected answers and assertion metadata.
- `evals/suites/`: repo-local live-suite manifests.
- `evals/baseline_policy.yaml`: live-suite baseline rules such as allowed triggers, baseline updates, and acceptable score drift.
- `redis_sre_agent/evaluation/`: loaders, mocked runtimes, scoring, and report writers.

Example scenario files:

- `evals/scenarios/prompt/chat-iterative-tool-use/scenario.yaml`
- `evals/scenarios/redis/memory-pressure-oss/scenario.yaml`
- `evals/scenarios/retrieval/skills-core/scenario.yaml`

## Quick Start

List the known scenarios:

```bash
uv run redis-sre-agent eval list
uv run redis-sre-agent eval list --json
```

Limit the scan to part of the tree:

```bash
uv run redis-sre-agent eval list --root evals/scenarios/prompt
```

## Mocked Evals During Development

The fast path for the mocked harness is the evaluation test suite. This uses the scenario fixtures under `evals/` instead of live Redis, live MCP servers, or live retrieval systems.

Useful commands:

```bash
make test-eval-pr
uv run pytest tests/unit/evaluation
uv run pytest tests/unit/cli/test_cli_eval.py
uv run pytest tests/unit/evaluation/test_prompt_scenarios.py -k iterative
uv run pytest tests/unit/evaluation/test_live_suite.py
```

When you are editing one scenario family, run the narrow test module that covers it instead of the whole tree.

`make test-eval-pr` is the supported mocked-eval gate for this repository. It runs the deterministic subset used in pull-request CI.

Do not treat `evals/scenarios/` as a single live-model suite. Most of those scenario files are validated through the deterministic pytest modules above, while live-model execution is reserved for the curated manifests under `evals/suites/`.

## Running One Mocked Scenario

Use the CLI when you want to execute a single mocked scenario directly.

For the most self-contained CLI path, start with an `agent_only` scenario. It still uses your
configured model credentials, but it avoids the local Redis/task-system dependency that
`full_turn` scenarios need.

```bash
uv run redis-sre-agent eval run \
  evals/scenarios/prompt/knowledge-agent-no-live-access/scenario.yaml
```

For machine-readable output:

```bash
uv run redis-sre-agent eval run \
  evals/scenarios/prompt/knowledge-agent-no-live-access/scenario.yaml \
  --json
```

Requirements and caveats:

- `agent_only` scenarios avoid local Redis/task orchestration, but they still execute the configured
  model. Set `OPENAI_API_KEY` or the equivalent compatible-endpoint settings before using `eval run`.
- `full_turn` scenarios exercise the real thread/task orchestration path and therefore also need the
  local Redis-backed runtime available.
- Scenarios marked `llm_mode: live` require explicit live opt-in with `--allow-live-llm`.

Useful options:

- `--session-id`: supply your own eval session id instead of using the default derived from the scenario id.
- `--user-id`: associate the run with a specific user id.
- `--allow-live-llm`: explicitly opt into scenarios configured with `llm_mode: live`.

## Running from Python

The Python API remains useful for custom harnesses and debugging.

Run a full-turn scenario:

```bash
uv run python - <<'PY'
import asyncio

from redis_sre_agent.evaluation import load_eval_scenario, run_full_turn_scenario

scenario = load_eval_scenario("evals/scenarios/prompt/chat-iterative-tool-use/scenario.yaml")
result = asyncio.run(
    run_full_turn_scenario(
        scenario,
        user_id="local-eval",
        session_id="local-eval::chat-iterative-tool-use",
    )
)
print(result.model_dump_json(indent=2))
PY
```

Run an `agent_only` scenario:

```bash
uv run python - <<'PY'
import asyncio

from redis_sre_agent.evaluation import load_eval_scenario
from redis_sre_agent.evaluation.agent_only import run_agent_only_scenario

scenario = load_eval_scenario("evals/scenarios/prompt/knowledge-agent-no-live-access/scenario.yaml")
result = asyncio.run(
    run_agent_only_scenario(
        scenario,
        session_id="local-eval::knowledge-agent-no-live-access",
        user_id="local-eval",
    )
)
print(result.model_dump_json(indent=2))
PY
```

Notes:

- `full_turn` scenarios exercise the real thread/task orchestration path with eval-time overrides.
- `agent_only` scenarios call the selected agent directly with a prebuilt eval context.
- Scenarios marked `llm_mode: live` require explicit live opt-in in the Python API.

## Scenario Anatomy

Most scenarios are built from the same parts:

- `execution`: lane, agent, prompt, and tool-step limits.
- `scope`: target catalog and bound targets for target-aware runs.
- `knowledge`: pinned startup docs plus one or more corpora.
- `tools`: mocked responder payloads for Redis, admin, and MCP tools.
- `expectations`: required and forbidden tool calls, findings, claims, and sources.

The `prompt/chat-iterative-tool-use` scenario is a good compact example because it includes:

- a real target binding handle,
- a pinned startup policy document,
- fixture-backed Redis tool payloads,
- structured assertions in the same manifest.

## Live Suites

Use live suites when you want the current model to run against the scenario corpus and emit comparable artifact bundles.

This repository includes a live-suite manifest:

- manifest: `evals/suites/live-agent-only-smoke.yaml`
- suite name: `live-agent-only-smoke`

Run it locally:

```bash
uv run redis-sre-agent eval live-suite \
  live-agent-only-smoke \
  --config evals/suites/live-agent-only-smoke.yaml \
  --output-dir .artifacts/evals \
  --trigger workflow_dispatch
```

Important: the baseline policy in `evals/baseline_policy.yaml` does not allow the CLI default `--trigger manual` for the `scheduled_live` profile. For the example suite above, use `--trigger workflow_dispatch` for manual runs.
To request a reviewed baseline refresh:

```bash
uv run redis-sre-agent eval live-suite \
  live-agent-only-smoke \
  --config evals/suites/live-agent-only-smoke.yaml \
  --output-dir .artifacts/evals \
  --trigger workflow_dispatch \
  --update-baseline
```

That switches the suite run onto the `manual_update` baseline-policy profile in the CLI wrapper.

## GitHub Actions Suite Config

CI also carries a separate suite manifest:

- manifest: `.github/evals/live-model-suites.yaml`
- suite name: `weekly-live-smoke`

If you want to reproduce the GitHub Actions suite locally with the helper script:

```bash
uv run python scripts/run_live_eval_suite.py \
  --suite .github/evals/live-model-suites.yaml \
  --suite-name weekly-live-smoke \
  --report-dir artifacts/live-evals \
  --trigger workflow_dispatch
```

## Comparing Candidate Results Against a Baseline

Each live run writes one suite directory. Compare two suite outputs with the same baseline-policy file used by the suite:

```bash
uv run redis-sre-agent eval compare \
  artifacts/live-evals/live-agent-only-smoke-baseline \
  .artifacts/evals/live-agent-only-smoke \
  --policy-file evals/baseline_policy.yaml \
  --profile scheduled_live
```

The compare command exits non-zero when the candidate breaches the configured variance band or is missing a scenario report.

## Output Layout

A live suite writes:

- `summary.json` at the suite root.
- one subdirectory per `scenario_id`.

Each scenario directory contains:

- `report.json`
- `report.md`
- `tool_trace.json`
- `retrieved_sources.json`
- `startup_context.json`

For the default local command above, the suite lands under:

```text
.artifacts/evals/live-agent-only-smoke/
```

## Reading the Results

Use the artifacts for different questions:

- `summary.json`: suite-level pass/fail and scenario paths.
- `report.json`: structured assertions, judge scores, provenance, and overall outcome.
- `report.md`: quick human review.
- `tool_trace.json`: which mocked or live-resolved tools were called.
- `retrieved_sources.json`: which pinned or retrieved sources were actually used.
- `startup_context.json`: startup knowledge and bound-context snapshot seen by the run.

## Choosing the Right Workflow

Use mocked evals when:

- you are editing prompts, routing, retrieval wiring, or tool virtualization,
- you want deterministic failures,
- you are iterating on a new scenario or corpus pack.

Use live suites when:

- you need to measure current model behavior,
- you want a regression signal against a reviewed baseline,
- you are preparing a scheduled or manual live-model check.

## Current Behavior

- The scenario corpus mixes `full_turn`, `agent_only`, `prompt`, `redis`, `knowledge`, `retrieval`, and `sources` lanes under one tree.
- Live suites coerce loaded scenarios to live LLM mode before execution, even when the source manifest is authored for replay mode.
- The CLI now exposes `eval run` for one-off debugging, but the supported deterministic regression gate remains the pytest workflow documented above.

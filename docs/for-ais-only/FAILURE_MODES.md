---
description: Intentional behaviors in the Redis SRE Agent that look like bugs but are not.
---

# Failure Modes

Things that look like bugs but are intentional. Read this before "fixing"
any of them.

## CLI commands and MCP tools must mirror each other

`tests/test_lint_parity.py` fails any PR that adds a CLI subcommand without
a corresponding MCP tool (or vice versa). The parity table is the contract
the agent uses to plan tool calls; deleting the test or relaxing the check
silently breaks tool selection inside the agent. If you must add an
asymmetric command, add an explicit allow-list entry in
`core/cli_mcp_parity.py` with a comment explaining why.

## Tool providers must go through `targets/redis_binding.py`

Direct `redis.Redis(...)` calls inside `tools/` look like obvious
simplifications, but they bypass target resolution, credential decryption,
and the per-target connection cache. The agent assumes that "the active
target" is the only Redis it talks to; ad-hoc clients break multi-target
deployments and Redis Enterprise admin flows.

## `core/config.py` is the only place that reads `os.environ`

Reading env vars from inside agent or tool modules looks harmless but
breaks settings overrides in tests and in the eval harness, both of which
patch the `Settings` instance rather than the environment. New
configuration goes into `Settings` with a default and an env-var name; tests
get the value from the injected settings object.

## The triage loop calls knowledge before tools, by design

It looks wasteful for the agent to retrieve runbooks before calling a
diagnostic tool, but the prompt assumes that retrieved context is what
narrows the tool choice. Reordering, or skipping retrieval when "the
question is simple," regresses the live-suite eval scores even when unit
tests still pass.

## "Pipeline ingest" is intentionally separate from "pipeline scrape"

A single `pipeline run` command would be ergonomic, but scraping is slow
and the artifacts are reused across many `ingest` runs (different chunking
strategies, different embedding models). Merging them would make iteration
on chunk size or embeddings 10-100x slower.

## Eval suite uses `FakeMCP`, not the real MCP server

`evaluation/fake_mcp.py` is *not* dead code waiting to be replaced by the
real server. It pins the tool surface the eval harness is graded against
so that adding a new tool does not silently change historical eval scores.
Switching the eval harness to the live MCP server defeats this guarantee.

## `make docs-gen-check` failures are not flakes

The REST and CLI reference pages under `docs/api/` are generated from code.
If `docs-gen-check` fails, regenerate (`make docs-gen`) and commit; do not
hand-edit the generated files.

## Strict-mode docs build warnings are errors

CI runs `mkdocs build --strict`, which promotes every warning to an
error. Silencing a warning in `mkdocs.yml` (for example by removing a
page from `nav` or relaxing a plugin's strictness) to "make CI green"
hides broken cross-references that later become 404s on the published
docs site. Fix the underlying link or page instead.

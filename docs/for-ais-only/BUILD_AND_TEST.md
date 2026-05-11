---
description: Exact commands CI runs and their local equivalents for the Redis SRE Agent.
---

# Build and Test

## Prerequisites

- Python 3.12 or newer (`requires-python = ">=3.12"` in `pyproject.toml`).
- `uv` (https://docs.astral.sh/uv/).
- Docker (for the local services stack and integration tests that spin up
  Redis via testcontainers).
- `OPENAI_API_KEY` set in the environment for live-LLM evals; unit tests do
  not need it.

## Make targets

```
make sync                 uv sync (dev deps + project)
make lint                 ruff format + ruff check + mypy
make test                 pytest excluding integration tests
make test-integration     integration tests only (requires Redis + Docker)
make test-all             unit + integration
make test-eval-pr         deterministic eval subset used in PR CI
make test-eval-live       scheduled live-model eval suite
make local-services       docker compose up -d (full local stack)
make local-services-down  stop the stack
make quick-demo           seeded demo stack with a registered Redis target
make docs-build           build Sphinx HTML to docs/_build/html
make docs-serve           serve docs/_build/html on http://127.0.0.1:8000
make docs-gen             regenerate REST/CLI reference pages from code
make docs-gen-check       fail if `docs-gen` would change tracked files
```

## Coverage policy

This project does not enforce a global coverage gate. New code that touches
the agent loop, tool providers, or `core/config.py` should ship with unit
tests; new integration paths should ship with at least one
`tests/integration/` test.

## Running a single test

```
uv run pytest tests/integration/test_agent_behavior.py::test_<name> -vv
uv run pytest tests/test_lint_parity.py -vv
```

## Building the docs

```
uv sync --group docs       # if a docs group is defined; otherwise just sync
make docs-build            # writes docs/_build/html
make docs-serve            # http://127.0.0.1:8000
```

The Sphinx build should complete with zero warnings. Treat any warning as a
breaking change. Run with `-W` in CI:

```
uv run sphinx-build -W -b html docs docs/_build/html
```

The Python package reference under `docs/api/python/` uses
`sphinx.ext.autosummary` with `:recursive:`; if you add a top-level
sub-package under `redis_sre_agent/`, list it in
`docs/api/python/index.rst`.

## CI gates (target state)

- `make lint` and `make test` on every PR.
- `make docs-gen-check` on every PR (REST/CLI reference must stay in sync).
- `make docs-build` with `-W` on every PR.
- `make test-eval-pr` on every PR; `test-eval-live` on schedule.

## Fast iteration loops

When changing the LangGraph agent or prompts:

```
uv run pytest tests/integration/test_agent_behavior.py -x -vv
uv run pytest tests/integration/test_multi_turn_simple.py -x -vv
```

When changing tool providers:

```
uv run pytest tests/tools/ -x -vv
uv run pytest tests/integration/test_instance_tool_routing.py -x -vv
```

When changing the knowledge pipeline:

```
uv run pytest tests/integration/test_cli_knowledge_commands.py -x -vv
uv run pytest tests/integration/test_knowledge_search_helper_integration.py -x -vv
```

When changing the CLI ↔ MCP surface:

```
uv run pytest tests/test_lint_parity.py -vv
```

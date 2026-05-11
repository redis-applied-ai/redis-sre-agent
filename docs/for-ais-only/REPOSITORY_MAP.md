---
description: Module-by-module guide to the Redis SRE Agent source tree, written for an AI agent making changes.
---

# Repository Map

A module-by-module guide to the Redis SRE Agent source tree, written for an
agent that needs to change something and wants to know where to look.

## Source layout

```
redis_sre_agent/
  __init__.py             Package version only; no public re-exports.
  agent/                  LangGraph triage agent, prompts, checkpointing.
    chat_agent.py         The conversational agent loop.
    knowledge_agent.py    Retrieval-augmented knowledge agent.
    langgraph_agent.py    Top-level LangGraph state machine.
    cluster_diagnostics.py  Redis cluster diagnostic flow.
    helpers.py            Shared agent helpers.
    prompts.py            Prompt templates.
  api/                    FastAPI HTTP surface.
    app.py                FastAPI app factory + route registration.
    health.py, instances.py, clusters.py, knowledge.py,
    metrics.py, schedules.py, schemas.py, middleware.py
  cli/                    Click CLI entry points.
    main.py               Top-level command group (`redis-sre-agent`).
    cluster.py, instance.py, knowledge.py, mcp.py, eval/
  core/                   Configuration, helpers, target plumbing.
    config.py             Pydantic settings; the source of truth.
    agent_memory.py       Agent-Memory-Server integration helpers.
    cluster_admin_defaults.py, cluster_helpers.py,
    clusters.py, citation_message.py, approvals.py
  evaluation/             Eval scenarios + judges (PR + live suites).
    agent_only.py, fake_mcp.py, judge.py, live_policy.py,
    live_suite/, knowledge_backend.py
  mcp_server/             MCP server exposing the agent's tools.
    server.py
  observability/          LLM metrics, OpenTelemetry tracing.
    llm_metrics.py, tracing.py
  pipelines/              Knowledge ingestion pipeline.
    orchestrator.py       SCRAPE → PARSE → CHUNK → EMBED → INDEX coordinator.
    scraper/, ingestion/, enrichment/
  skills/                 Skill discovery + scaffolding for source docs.
    backend.py, discovery.py, scaffold.py, models.py
  targets/                Redis target binding (OSS / cluster / Enterprise / Cloud).
    contracts.py, registry.py, redis_binding.py,
    redis_catalog.py, handle_store.py, services.py
  tools/                  Tool providers callable by the agent.
    admin/, cloud/, diagnostics/, host_telemetry/,
    knowledge/, logs/, cache.py, decorators.py, fake/
```

## Test layout

```
tests/
  conftest.py             Shared fixtures (Redis testcontainers, FakeMCP).
  test_lint_parity.py     Guards CLI <-> MCP parity.
  test_docs_snippets.py   Validates code snippets in docs/.
  unit/                   Pure-Python unit tests.
  tools/                  Tool-provider unit tests.
  integration/            Requires Redis + sometimes API keys; covers
                          agent behaviour, evals, knowledge, conversation
                          flow, target discovery, Prometheus E2E, etc.
```

## Where features live

| Feature | Module(s) |
|---|---|
| LangGraph triage loop | `agent/langgraph_agent.py`, `agent/chat_agent.py` |
| Knowledge retrieval | `agent/knowledge_agent.py`, `tools/knowledge/`, `pipelines/` |
| Tool registration | `tools/decorators.py`, `tools/__init__.py` |
| Redis target catalog | `targets/registry.py`, `targets/redis_catalog.py` |
| REST endpoints | `api/app.py` + sibling routers |
| MCP tool surface | `mcp_server/server.py` |
| Recurring schedules | `api/schedules.py` + Docket workers |
| Eval suites | `evaluation/` + `evals/` (project root) |
| Configuration | `core/config.py`, `.env.example` |

## What to read before changing X

- **The triage loop.** Start in `agent/langgraph_agent.py`. The state graph
  there decides what tool to call; tool definitions live in `tools/` and are
  collected by `tools/__init__.py`. Read `agent/prompts.py` for the system
  prompt that drives tool selection.
- **A tool provider.** Each provider exposes one or more functions decorated
  via `tools/decorators.py`. Side effects on Redis go through
  `targets/redis_binding.py`, not raw `redis` clients.
- **Knowledge ingestion.** The pipeline is `pipelines/orchestrator.py`.
  Don't add scrape/parse logic anywhere else - it must thread through the
  orchestrator so retries and resumability still work.
- **CLI ↔ MCP parity.** `tests/test_lint_parity.py` enforces that every
  CLI command is mirrored as an MCP tool. If you add a CLI command, add the
  MCP tool too.
- **Configuration.** `core/config.py` is a `pydantic_settings.BaseSettings`.
  All new config must go there with a default and an env-var name; nothing
  reads `os.environ` directly outside `config.py`.

## What is intentionally not exported

- `tools/fake/` and `evaluation/fake_mcp.py` are test doubles. They are
  imported by tests but are not part of the public agent contract.
- `cli/logging_utils.py` is internal CLI-only; do not import from
  application code.
- `core/cli_mcp_parity.py` exists to satisfy the CLI/MCP parity test and is
  not a runtime dependency of the agent.

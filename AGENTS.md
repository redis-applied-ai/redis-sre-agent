# Redis SRE Agent - Agents File

## Project Overview
A production-ready Redis Site Reliability Engineering (SRE) agent built with LangGraph, FastAPI, and comprehensive monitoring tools. Provides automated Redis health monitoring, issue detection, and conversational troubleshooting.

## Architecture Components
- **LangGraph Agent**: Multi-turn conversation with specialized SRE tools
- **FastAPI API**: Production endpoints for agent interaction
- **Background Worker**: Docket-based async task execution
- **Redis Monitoring**: Multi-category diagnostic analysis system
- **Prometheus/Loki Integration**: Metrics and log aggregation
- **Vector Knowledge Base**: SRE runbook search and retrieval
- **Docker Stack**: Complete monitoring environment with Grafana dashboards

## Quick Reference

### Environment Setup
```bash
uv sync --dev
uv run redis-sre-agent --help
```

### Testing
```bash
make test                # Unit tests only
make test-integration    # Integration tests only
make test-all           # Full suite
uv run pytest --cov=redis_sre_agent --cov-report=html  # With coverage
```

### Docker Stack
```bash
make local-services      # Start full stack
make local-services-down # Stop stack
make local-services-logs # Tail logs
```

### Access Points (Docker)
| Service | URL |
|---------|-----|
| SRE Agent API | http://localhost:8080 |
| SRE Agent UI | http://localhost:3002 |
| Grafana | http://localhost:3001 (admin/admin) |
| Prometheus | http://localhost:9090 |
| Redis (agent) | redis://localhost:7843 |
| Redis (demo) | redis://localhost:7844 |

## Key File Locations
- Agent core: `redis_sre_agent/agent/`
- Redis tools: `redis_sre_agent/tools/`
- API endpoints: `redis_sre_agent/api/app.py`
- CLI: `redis_sre_agent/cli/`
- Configuration: `redis_sre_agent/core/config.py`
- Docker config: `docker-compose.yml`
- Source documents: `source_documents/`

## Environment Variables
See `.env.example` for full configuration. Key variables:
- `OPENAI_API_KEY`: Required for LLM functionality
- `REDIS_URL`: Redis connection string (default: redis://localhost:7843/0)
- `LITELLM_MASTER_KEY`: Auth key for LiteLLM proxy (Docker only)

## Knowledge Base
- **Data sources**: redis.io/kb articles, local redis-docs clone, `source_documents/`
- **Pipeline**: `pipeline scrape` creates artifacts, `pipeline ingest` indexes into Redis
- **Sync docs**: `make redis-docs-sync` to clone/update redis/docs

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **redis-sre-agent** (32287 symbols, 45155 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/redis-sre-agent/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/redis-sre-agent/context` | Codebase overview, check index freshness |
| `gitnexus://repo/redis-sre-agent/clusters` | All functional areas |
| `gitnexus://repo/redis-sre-agent/processes` | All execution flows |
| `gitnexus://repo/redis-sre-agent/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

- Re-index: `npx gitnexus analyze`
- Check freshness: `npx gitnexus status`
- Generate docs: `npx gitnexus wiki`

<!-- gitnexus:end -->

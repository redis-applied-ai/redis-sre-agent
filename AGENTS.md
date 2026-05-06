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
- Written specs: `specs/`
- Source documents: `source_documents/`

## Specs
- Put newly written design specs and implementation specs in `specs/`.
- Prefer `specs/` over `docs/` for work-in-progress or review-oriented specification documents.

## Environment Variables
See `.env.example` for full configuration. Key variables:
- `OPENAI_API_KEY`: Required for LLM functionality
- `OPENAI_BASE_URL`: Optional OpenAI-compatible endpoint override
- `REDIS_URL`: Redis connection string (default: redis://localhost:7843/0)

## Knowledge Base
- **Data sources**: redis.io/kb articles, local redis-docs clone, `source_documents/`
- **Pipeline**: `pipeline scrape` creates artifacts, `pipeline ingest` indexes into Redis
- **Sync docs**: `make redis-docs-sync` to clone/update redis/docs

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **redis-sre-agent** (31399 symbols, 54431 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/redis-sre-agent/context` | Codebase overview, check index freshness |
| `gitnexus://repo/redis-sre-agent/clusters` | All functional areas |
| `gitnexus://repo/redis-sre-agent/processes` | All execution flows |
| `gitnexus://repo/redis-sre-agent/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

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

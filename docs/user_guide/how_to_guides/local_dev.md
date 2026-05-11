---
description: Run the agent against a local Redis without the full stack.
---

# Local development

Use this guide when you are working on the agent itself rather than
operating a deployed instance. It walks through booting the agent
without Docker, swapping in the Docker stack for full-environment
testing, and running the unit and integration test suites. If you only
want to *use* a local stack to chat with the agent, the [Local quick
start](../01_local_quickstart.md) is shorter.

**Related:** [Docker deployment](operations/docker_deployment.md) · [Evals](evals.md)

## Prerequisites
- Python 3.12
- uv (https://github.com/astral-sh/uv)
- Docker + Docker Compose v2 (for stack testing)

## 1) Setup the dev environment
```bash
# Install dependencies (dev extras included)
uv sync --dev

# Basic sanity check
uv run redis-sre-agent --help
```

Environment variables (create .env for local dev)
```bash
cp .env.example .env
# Set at minimum
# OPENAI_API_KEY=your_key
# REDIS_URL=redis://localhost:7843/0
```

## 2) Run the API locally
```bash
# Start FastAPI with reload
uv run uvicorn redis_sre_agent.api.app:app --host 0.0.0.0 --port 8000 --reload
# OpenAPI: http://localhost:8000/openapi.json
# Docs:    http://localhost:8000/docs
```

## 3) Run the background worker locally
```bash
uv run redis-sre-agent worker
```

Tip: Run API and worker in two shells. The API serves endpoints and websockets; the worker executes long-running jobs.

## 4) Full stack (Docker Compose)
Use this to bring up Prometheus, Grafana, Loki, and the agent services.
```bash
# Minimal dev stack (omit demo services)
docker compose up -d \
  redis \
  sre-agent sre-worker \
  prometheus grafana \
  loki promtail

# Logs
docker compose logs -f sre-agent
```
**Note**: Docker Compose exposes the API on port **8080** (http://localhost:8080), while local uvicorn uses port 8000.

## 5) Create a demo instance (optional)
```bash
# Inside the API container (uses internal addresses)
docker compose exec -T sre-agent uv run redis-sre-agent instance create \
  --name demo \
  --connection-url redis://redis-demo:6379/0 \
  --environment development \
  --usage cache \
  --description "Demo Redis"
```

## 6) Testing
Smallest-to-largest scope:
```bash
# Single test function
uv run pytest tests/unit/api/test_api.py::test_root

# Single file
uv run pytest tests/unit/api/test_api.py

# Unit tests only (skip integration)
uv run pytest -m "not integration"

# Integration tests only
uv run pytest -m integration

# Coverage HTML report
uv run pytest --cov=redis_sre_agent --cov-report=html
```

## 7) Useful commands
```bash
# Install repo pre-commit hook (root config)
make hooks-install

# Run exact CI lint checks locally
make lint

# Run all local pre-commit hooks
uv run pre-commit run -a

# Build docs
uv run mkdocs build

# Live docs server
uv run mkdocs serve -a 127.0.0.1:8001
```

## Troubleshooting
- OPENAI_API_KEY missing: set it in .env or your shell
- Redis not reachable: verify `REDIS_URL` and that compose `redis` is running (port 7843)
- Worker not processing: ensure `uv run redis-sre-agent worker start` is running and `/api/v1/health` shows worker available
- Prometheus/Grafana: check `docker compose logs -f prometheus grafana`

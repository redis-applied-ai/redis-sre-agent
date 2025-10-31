## Using the API: Core Workflows

This guide shows how to use the HTTP API end-to-end: check health, add an instance, triage using tasks/threads, ingest and search knowledge, schedule recurring checks, and view status. It focuses on concrete workflows rather than a full reference.

Prerequisites
- Services running (Docker Compose or local uvicorn + worker)
- If you enabled auth in your environment, include your API key header as needed

### 1) Start services (choose one)
- Docker Compose
```bash
docker compose up -d \
  redis \
  sre-agent sre-worker \
  prometheus grafana \
  loki promtail
```
- Local processes
```bash
# API
uv run uvicorn redis_sre_agent.api.app:app --host 0.0.0.0 --port 8000 --reload
# Worker (separate terminal)
uv run redis-sre-agent worker --concurrency 4
```

### 2) Health and readiness
```bash
# Root health (fast)
curl -fsS http://localhost:8000/

# Detailed health (Redis, vector index, workers)
curl -fsS http://localhost:8000/api/v1/health | jq

# Prometheus metrics (scrape this)
curl -fsS http://localhost:8000/api/v1/metrics | head -n 20
```

### 3) Manage Redis instances
Create the instance the agent will triage, then verify a connection.
```bash
# Create instance
curl -fsS -X POST http://localhost:8000/api/v1/instances \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "prod-cache",
    "connection_url": "redis://your-redis-host:6379/0",
    "environment": "production",
    "usage": "cache",
    "description": "Primary Redis"
  }' | jq

# List & inspect
curl -fsS http://localhost:8000/api/v1/instances | jq
curl -fsS http://localhost:8000/api/v1/instances/<id> | jq

# Test connection (by ID)
curl -fsS -X POST http://localhost:8000/api/v1/instances/<id>/test-connection | jq

# Test a raw URL (without saving)
curl -fsS -X POST http://localhost:8000/api/v1/instances/test-connection-url \
  -H 'Content-Type: application/json' \
  -d '{"connection_url": "redis://host:6379/0"}' | jq
```

Notes
- The API masks credentials in returned `connection_url`
- Use `PUT /api/v1/instances/{id}` to update fields (masked secrets are preserved)
- Use `DELETE /api/v1/instances/{id}` to remove

### 4) Triage with tasks and threads
Simplest: create a task with your question. The API will create a thread if you omit `thread_id`.
```bash
# Create a task (no instance)
curl -fsS -X POST http://localhost:8000/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"message": "Explain high memory usage signals in Redis"}' | jq

# Create a task (target a specific instance)
curl -fsS -X POST http://localhost:8000/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "Check memory pressure and slow ops",
    "context": {"instance_id": "<instance_id>"}
  }' | jq
```
Poll task or inspect the thread:
```bash
# Poll task status
curl -fsS http://localhost:8000/api/v1/tasks/<task_id> | jq

# Get the thread state (messages, updates, result)
curl -fsS http://localhost:8000/api/v1/threads/<thread_id> | jq
```
Real-time updates via WebSocket:
```bash
# Requires a thread_id; use any ws client (wscat, websocat)
wscat -c ws://localhost:8000/api/v1/ws/tasks/<thread_id>
# You will receive an initial_state event and subsequent progress updates
```
Alternative flow: create a thread first, then submit a task on that thread.
```bash
# Create thread
curl -fsS -X POST http://localhost:8000/api/v1/threads \
  -H 'Content-Type: application/json' \
  -d '{"user_id": "u1", "subject": "Prod triage"}' | jq

# Submit a task to that thread
curl -fsS -X POST http://localhost:8000/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "thread_id": "<thread_id>",
    "message": "Check for memory fragmentation",
    "context": {"instance_id": "<instance_id>"}
  }' | jq
```

### 5) Prepare knowledge and validate what the agent knows
Run an ingestion job, then search to confirm content is available.
```bash
# Start pipeline job (ingest existing artifacts or run full if configured)
curl -fsS -X POST http://localhost:8000/api/v1/knowledge/ingest/pipeline \
  -H 'Content-Type: application/json' \
  -d '{"operation": "ingest", "artifacts_path": "./artifacts"}' | jq

# List jobs & check individual job status
curl -fsS http://localhost:8000/api/v1/knowledge/jobs | jq
curl -fsS http://localhost:8000/api/v1/knowledge/jobs/<job_id> | jq

# Search knowledge
curl -fsS 'http://localhost:8000/api/v1/knowledge/search?query=redis%20eviction%20policy' | jq
```
Optional single-document ingestion:
```bash
curl -fsS -X POST http://localhost:8000/api/v1/knowledge/ingest/document \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Redis memory troubleshooting",
    "content": "Steps to investigate RSS and used_memory...",
    "source": "internal-docs",
    "category": "runbooks"
  }' | jq
```

### 6) Schedule recurring checks
Create a schedule to run instructions periodically, optionally bound to an instance.
```bash
# Create schedule (daily)
curl -fsS -X POST http://localhost:8000/api/v1/schedules/ \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "daily-triage",
    "description": "Daily Redis health check",
    "interval_type": "days",
    "interval_value": 1,
    "instructions": "Daily Redis health check",
    "redis_instance_id": "<instance_id>",
    "enabled": true
  }' | jq

# List/get
curl -fsS http://localhost:8000/api/v1/schedules/ | jq
curl -fsS http://localhost:8000/api/v1/schedules/<schedule_id> | jq

# Trigger now (manual run)
curl -fsS -X POST http://localhost:8000/api/v1/schedules/<schedule_id>/trigger | jq

# View runs for a schedule
curl -fsS http://localhost:8000/api/v1/schedules/<schedule_id>/runs | jq
```

### 7) Tasks, threads, and streaming
- Tasks: `GET /api/v1/tasks/{task_id}`
- Threads: `GET /api/v1/threads`, `GET /api/v1/threads/{thread_id}`
- WebSocket: `ws://localhost:8000/api/v1/ws/tasks/{thread_id}`

### 8) Observability
- Prometheus scrape: `GET /api/v1/metrics`
- Health: `GET /api/v1/health` (checks Redis, vector index, workers); status may be degraded when workers aren’t running
- Grafana: http://localhost:3001 (default admin/admin)

Tips
- Set TOOLS_PROMETHEUS_URL and TOOLS_LOKI_URL to enable metrics/logs tools during triage
- For Docker, prefer in-cluster addresses from within the sre-agent container when invoking the CLI
- See How-to: Using the CLI & API for a CLI-first walkthrough of the same flows

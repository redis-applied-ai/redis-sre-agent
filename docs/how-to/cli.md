## Using the CLI: Core Workflows

This guide shows how to use the agent end-to-end: start services, add an instance, triage with queries, ingest knowledge, search what the agent knows, schedule recurring checks, and view task/thread status.

Prerequisites
- OPENAI_API_KEY set (see How-to: Configuration)
- Services running (Docker Compose or local API + worker)

### 1) Start services (choose one)
- Docker Compose (recommended for full stack)
  ```bash
docker compose up -d \
  redis \
  sre-agent sre-worker \
  prometheus grafana \
  loki promtail
  ```
  - API: http://localhost:8000
- Local processes (no Docker)
  ```bash
  # API
  uv run uvicorn redis_sre_agent.api.app:app --host 0.0.0.0 --port 8000 --reload
  # Worker (separate terminal)
  uv run redis-sre-agent worker --concurrency 4
  ```

### 2) Add a Redis instance and verify
Tell the agent about the Redis you want to triage.
```bash
# Create (adjust URL/env/usage/description)
uv run redis-sre-agent instance create \
  --name prod-cache \
  --connection-url redis://your-redis-host:6379/0 \
  --environment production \
  --usage cache \
  --description "Primary Redis"

# List / view / test
uv run redis-sre-agent instance list
uv run redis-sre-agent instance get <id>
uv run redis-sre-agent instance test --id <id>
```

### 3) Triage with queries
- Without an instance: quick questions (general guidance)
  ```bash
  uv run redis-sre-agent query "Explain high memory usage signals in Redis"
  ```
- With an instance: targeted triage (the agent will fetch metrics/logs if configured)
  ```bash
  uv run redis-sre-agent query "Check memory pressure and slow ops" -r <id>
  ```

### 4) Prepare knowledge for better answers (ingest a batch)
Load docs so the agent can cite internal knowledge.
```bash
# Option A: Prepare built-in sources then ingest
uv run redis-sre-agent pipeline prepare-sources
uv run redis-sre-agent pipeline ingest

# Option B: One-shot full pipeline (prepare + scrape + ingest)
uv run redis-sre-agent pipeline full

# Inspect batches and status
uv run redis-sre-agent pipeline status
uv run redis-sre-agent pipeline show-batch --batch <name>
```
Runbooks (subtopic)
```bash
# Generate standardized runbooks for a topic
uv run redis-sre-agent runbook generate --topic "Redis memory troubleshooting"
# Evaluate runbooks you generated or imported
uv run redis-sre-agent runbook evaluate
```

### 5) Search what the agent knows (and verify context)
Use this to confirm the agent’s view of your knowledge base.
```bash
uv run redis-sre-agent knowledge search --query "redis eviction policy"
uv run redis-sre-agent knowledge fragments --doc-hash <hash>
uv run redis-sre-agent knowledge related --doc-hash <hash> --chunk-index 0
```

### 6) Schedule recurring checks
Create a schedule that enqueues a triage with optional instance context.
```bash
# Create: run every 24 hours
uv run redis-sre-agent schedule create \
  --name daily-triage \
  --interval-type days \
  --interval-value 1 \
  --instructions "Daily Redis health check" \
  --redis-instance-id <id> \
  --enabled

# Trigger immediately (out-of-band)
uv run redis-sre-agent schedule run-now <schedule_id>

# Manage
uv run redis-sre-agent schedule list
uv run redis-sre-agent schedule get <schedule_id>
uv run redis-sre-agent schedule enable <schedule_id>
uv run redis-sre-agent schedule disable <schedule_id>
uv run redis-sre-agent schedule update <schedule_id> --name "new-name"
uv run redis-sre-agent schedule delete <schedule_id> -y
```

### 7) See task status and thread contents
Tasks track execution; threads hold the conversation + context.
```bash
# Tasks
uv run redis-sre-agent task list                # in-progress/queued by default
uv run redis-sre-agent task list --all          # include done/failed/cancelled
uv run redis-sre-agent task get <task_id>

# Threads
uv run redis-sre-agent thread list
uv run redis-sre-agent thread get <thread_id>
uv run redis-sre-agent thread sources <thread_id>
```

Tips
- Use the Docker stack to get Prometheus/Loki; set TOOLS_PROMETHEUS_URL and TOOLS_LOKI_URL so the agent can fetch metrics/logs.
- Prefer `docker compose exec -T sre-agent uv run ...` inside containers when running in Docker (uses in-cluster addresses).
- Health endpoints: `curl http://localhost:8000/` and `/api/v1/health` to verify API and worker availability.

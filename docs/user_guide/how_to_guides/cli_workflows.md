---
description: End-to-end workflows for driving the Redis SRE Agent from the command line.
---

# CLI workflows

This page shows you how to drive the agent end-to-end from the CLI: start
services, register a Redis instance, triage with queries, ingest knowledge,
search what the agent knows, schedule recurring checks, and inspect task
or thread state. It is workflow-oriented; for command-level detail see the
[CLI reference](../../api/cli_ref.md).

**Related:** [API workflows](api_workflows.md) ·
[Source documents](source_documents.md) · [Pipelines](pipelines.md)

!!! info "Prerequisites"
    `OPENAI_API_KEY` set (see [Configuration](configuration.md)) and
    services running (Docker Compose or local API + worker).


## 1) Start services (choose one)
- Docker Compose (recommended for full stack)
  ```bash
docker compose up -d \
  redis \
  sre-agent sre-worker \
  prometheus grafana \
  loki promtail
  ```
  - API: http://localhost:8080 (Docker Compose exposes port 8080)
- Local processes (no Docker)
  ```bash
  # API
  uv run uvicorn redis_sre_agent.api.app:app --host 0.0.0.0 --port 8000 --reload
  # Worker (separate terminal)
  uv run redis-sre-agent worker start
  ```

## 2) Add a Redis instance and verify
Tell the agent about the Redis you want to triage.
```bash
# Create (adjust URL/env/usage/description)
uv run redis-sre-agent instance create \
  --name prod-cache \
  --connection-url redis://localhost:6379/0 \
  --environment production \
  --usage cache \
  --description "Primary Redis"

# List / view / test
uv run redis-sre-agent instance list
uv run redis-sre-agent instance get <id>
uv run redis-sre-agent instance test <id>
```

## 3) Triage with queries
- Without an instance: quick questions (general guidance)
  ```bash
  uv run redis-sre-agent query "Explain high memory usage signals in Redis"
  ```
- With an instance: targeted triage (the agent will fetch metrics/logs if configured)
  ```bash
  uv run redis-sre-agent query "Check memory pressure and slow ops" -r <id>
  ```
- With a cluster: cluster-scoped diagnostics fan out across linked instances
  ```bash
  uv run redis-sre-agent query "Check this cluster for connectivity and memory pressure" -c <cluster_id>
  ```
  - For diagnostic prompts, cluster-scoped queries are auto-upgraded to triage.

### Natural-language target discovery
When target-discovery integrations are configured, you can ask for a target in natural language
instead of supplying `-r` or `-c` up front.

```bash
uv run redis-sre-agent query \
  "Check whether the production checkout cache is under memory pressure"
```

If the reference is ambiguous, the agent should ask for clarification instead of making live
claims. Continue the same thread with the narrower identifier:

```bash
uv run redis-sre-agent query -t <thread_id> \
  "Use the prod checkout cache in us-east-1"
```

### Multi-target comparison
When the prompt clearly asks for a comparison, the agent can keep more than one discovered target
in scope and compare them in one conversation.

```bash
uv run redis-sre-agent query \
  "Compare checkout cache and session cache for memory pressure and evictions"
```

You can continue the thread to narrow or reshape the comparison set:

```bash
uv run redis-sre-agent query -t <thread_id> \
  "Keep only the production caches and summarize which one needs attention first"
```

These discovery-first flows depend on your configured target catalog and bindings. If discovery is
not configured, use explicit `-r <instance_id>` or `-c <cluster_id>` flags instead.

## 4) Prepare knowledge for better answers (ingest a batch)
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
### Runbooks
```bash
# Generate standardized runbooks for a topic
uv run redis-sre-agent runbook generate --topic "Redis memory troubleshooting"
# Evaluate runbooks you generated or imported
uv run redis-sre-agent runbook evaluate
```

## 5) Search what the agent knows (and verify context)
Use this to confirm the agent’s view of your knowledge base.
```bash
uv run redis-sre-agent knowledge search "redis eviction policy"
uv run redis-sre-agent knowledge fragments --doc-hash <hash>
uv run redis-sre-agent knowledge related --doc-hash <hash> --chunk-index 0
```

### Exact-match search notes
- Wrap a query in quotes to force the precise-search path for exact names, document hashes, source filenames, or literal phrases.
- Unquoted single-token identifiers that contain digits or punctuation also trigger exact matching automatically.
- Exact-looking queries first check identifier-style fields such as `name` and `source`, then run a literal phrase search across `title`, `summary`, and `content` before semantic results are merged in.
- General knowledge search excludes pinned docs, skills, and support tickets. Use the support-ticket tools for historical ticket lookups.

Examples:
```bash
# Exact source filename match
uv run redis-sre-agent knowledge search '"redis-enterprise-rladmin-cli.md"'

# Exact document hash or other identifier-like value
uv run redis-sre-agent knowledge search '"<document_hash>"'
```

For support-ticket IDs such as `RET-4421`, use the ticket workflow instead of general knowledge search:
```bash
uv run redis-sre-agent query --agent chat "Find support tickets for RET-4421"
```

## 6) Inspect Agent Skills packages
Use the top-level `skills` commands to inspect Agent Skills packages without running a full agent turn.

```bash
uv run redis-sre-agent skills list --query "maintenance"
uv run redis-sre-agent skills show redis-maintenance-triage
uv run redis-sre-agent skills read-resource \
  redis-maintenance-triage references/maintenance-checklist.md
```

To scaffold a package from an existing markdown skill:

```bash
uv run redis-sre-agent skills scaffold legacy-skill.md skills/legacy-skill
```

## 7) Schedule recurring checks
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

## 8) Analyze support packages
Upload and analyze Redis Enterprise support packages (debuginfo archives).

```bash
# Upload a support package
uv run redis-sre-agent support-package upload /path/to/debuginfo.tar.gz

# List uploaded packages
uv run redis-sre-agent support-package list

# Get package info
uv run redis-sre-agent support-package info <package_id>

# Query with a support package (agent gets access to INFO, SLOWLOG, CLIENT LIST, logs)
uv run redis-sre-agent query -p <package_id> "What databases are in this package?"

# Combine instance + support package (compare live vs snapshot)
uv run redis-sre-agent query -r <instance_id> -p <package_id> "Compare current memory with the snapshot"
```

### Docker Compose usage
When running in Docker, use `docker compose exec` to access the CLI. For file uploads,
you need to copy the file into the container first or mount a volume.

```bash
# Option 1: Copy file into container, then upload
docker compose cp /local/path/debuginfo.tar.gz sre-agent:/tmp/debuginfo.tar.gz
docker compose exec -T sre-agent uv run redis-sre-agent support-package upload /tmp/debuginfo.tar.gz

# Option 2: Mount a volume in docker-compose.yml and upload from there
# Add to sre-agent service volumes: - ./packages:/packages
docker compose exec -T sre-agent uv run redis-sre-agent support-package upload /packages/debuginfo.tar.gz

# List/query from Docker
docker compose exec -T sre-agent uv run redis-sre-agent support-package list
docker compose exec -T sre-agent uv run redis-sre-agent query -p <package_id> "Show database memory usage"
```

## 9) See task status and thread contents
Tasks track execution; threads hold the conversation + context.
```bash
# Tasks
uv run redis-sre-agent task list                # in-progress/queued by default
uv run redis-sre-agent task list --all          # include done/failed/cancelled
uv run redis-sre-agent task get <task_id>

# Threads
uv run redis-sre-agent thread list
uv run redis-sre-agent thread get <thread_id>
uv run redis-sre-agent thread trace <message_id_or_decision_trace_id>
uv run redis-sre-agent thread sources <thread_id>
```

### Approval-driven tasks
Some write actions can pause a task in `awaiting_approval`. The current CLI lets you inspect the
task or thread state, but approval history and resume actions are not exposed as CLI commands.

- `task get <task_id>` shows the latest status and can include `pending_approval`.
- `thread get <thread_id>` can also surface `task_id`, `pending_approval`, and `resume_supported`.
- Use the HTTP API or the web UI triage page to list approval records and submit `approved` or
  `rejected` decisions.

### Citations in thread history
Use these commands together when you want citation-level provenance for an answer:

1. Run `thread get <thread_id>` to list messages in the thread and find assistant `message_id` values.
2. Run `task get <task_id>` (or `GET /api/v1/tasks/<task_id>`) after completion to view `tool_calls` directly on the task payload.
3. Run `thread trace <id>` with either an assistant `message_id` (from `thread get`) or a `Decision trace: <id>` printed by `query`.
4. Run `thread sources <thread_id>` to list retrieved knowledge fragments by thread or turn.

When a response uses knowledge search, citations are also added to the chat history as a follow-up system message (`**Sources for previous response**`) in the same thread.
For support-ticket workflows, provenance appears in `thread trace` and thread system messages; `thread sources` focuses on fragment retrieval from knowledge indexes.
If a response used no tools, `thread trace` can return `No decision trace found for message ...`.

## Tips
- Use the Docker stack to get Prometheus/Loki; set TOOLS_PROMETHEUS_URL and TOOLS_LOKI_URL so the agent can fetch metrics/logs.
- Prefer `docker compose exec -T sre-agent uv run ...` inside containers when running in Docker (uses in-cluster addresses).
- Health endpoints: `curl http://localhost:8080/` (Docker Compose) or `http://localhost:8000/` (local uvicorn) and `/api/v1/health` to verify API and worker availability.

## Related

- [CLI reference](../../api/cli_ref.md) — full command reference.
- [API workflows](api_workflows.md) — same flows over HTTP.
- [Scheduling](scheduling.md) — recurring health checks in depth.
- [Configuration](configuration.md) — what to set on each process.

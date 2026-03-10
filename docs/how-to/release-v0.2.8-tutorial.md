# v0.2.8 Release Tutorial

This walkthrough validates each user-facing feature from the
[`v0.2.8` release](https://github.com/redis-applied-ai/redis-sre-agent/releases/tag/v0.2.8)
with runnable examples.

## Release Items Covered

- `fix: Force tool call on first turn in knowledge agent`
- `docs: citation tracing via thread get/trace`
- `docs: Redis connection setup guidance`
- `feat: Split RedisCluster from RedisInstance`
- `feat: pinned docs, skills, and support tickets`
- `feat: Allow Redis Enterprise cluster creation to use env admin defaults`
- `feat: Cluster-scoped diagnostics across CLI/API/UI/MCP`

## Prerequisites

```bash
# Fresh Redis databases: initialize all required indexes once
uv run redis-sre-agent index recreate --yes --json

# API
uv run uvicorn redis_sre_agent.api.app:app --host 0.0.0.0 --port 8000 --reload

# Worker (separate terminal)
uv run redis-sre-agent worker start
```

## 1) Knowledge Agent First-Turn Tool Calls + Citation Tracing

Release items:
- `fix: Force tool call on first turn in knowledge agent`
- `docs: citation tracing via thread get/trace`

### Try it

```bash
uv run redis-sre-agent query --agent knowledge \
  "What is the default Redis eviction behavior when maxmemory is not set?"
```

You should see a thread ID in CLI output.

### Inspect provenance

```bash
# 1) Get thread messages
uv run redis-sre-agent thread get <thread_id> --json

# 2) Trace by assistant message_id or decision trace ID printed by query
uv run redis-sre-agent thread trace <message_id_or_decision_trace_id> --json

# 3) Show source fragments gathered for the thread
uv run redis-sre-agent thread sources <thread_id> --json
```

What to look for:
- `thread trace` includes `tool_envelopes` entries for knowledge-search calls.
- If sources were retrieved, the thread also includes a system message titled
  `**Sources for previous response**`.
- `thread sources` returns fragment results from knowledge indexes.
- For support-ticket retrieval flows, use `thread trace` + `thread get` for provenance.

## 2) RedisCluster / RedisInstance Split

Release item:
- `feat: Split RedisCluster from RedisInstance`

### CLI flow

```bash
# Create cluster
uv run redis-sre-agent cluster create \
  --name "oss-cluster-a" \
  --cluster-type oss_cluster \
  --environment production \
  --description "OSS cluster for testing" \
  --json

# Create instance linked to the cluster
uv run redis-sre-agent instance create \
  --name "oss-inst-a" \
  --connection-url "redis://localhost:6379/0" \
  --environment production \
  --usage cache \
  --description "Linked OSS instance" \
  --instance-type oss_cluster \
  --cluster-id <cluster_id> \
  --json

# Verify
uv run redis-sre-agent cluster get <cluster_id> --json
uv run redis-sre-agent instance get <instance_id> --json
```

Note: `cluster create --json` returns `{id, status}`. Use `cluster get <cluster_id> --json` for full cluster fields.

### API flow

```bash
# Create cluster
curl -fsS -X POST http://localhost:8080/api/v1/clusters \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "cloud-cluster-a",
    "cluster_type": "redis_cloud",
    "environment": "production",
    "description": "Cloud control plane"
  }' | jq

# Create linked instance
curl -fsS -X POST http://localhost:8080/api/v1/instances \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "cloud-inst-a",
    "connection_url": "redis://localhost:6379/0",
    "environment": "production",
    "usage": "cache",
    "description": "Cloud-linked instance",
    "instance_type": "redis_cloud",
    "cluster_id": "<cluster_id>"
  }' | jq
```

## 3) Pinned Docs, Skills, and Support Tickets

Release item:
- `feat: pinned docs, skills, and support tickets`

### Prepare source docs with front matter

```bash
uv run redis-sre-agent pipeline prepare-sources \
  --source-dir /path/to/source_documents \
  --batch-date 2099-01-04

uv run redis-sre-agent pipeline ingest --batch-date 2099-01-04
```

### Pinned doc behavior

```bash
uv run redis-sre-agent query --agent chat \
  "For sev-1 Redis incidents, what escalation code must we post?"
```

Expected: response reflects pinned policy content from startup context.

### Skill retrieval behavior

```bash
uv run redis-sre-agent query --agent chat \
  "Do we have a skill named failover-investigation? If so, summarize it in one sentence."
```

Expected: response summarizes the skill and `thread trace` shows a `get_skill` tool call.

### Support-ticket workflow (two turns)

```bash
# Turn 1
uv run redis-sre-agent query --agent chat \
  "Can you find relevant support tickets for failover resets?"

# Turn 2 (same thread)
uv run redis-sre-agent query --agent chat --thread-id <thread_id> \
  "Host is cache-prod-1.redis.company.net and errors are ECONNRESET during failover."
```

Expected:
- Support-ticket search narrows with identifier + symptom.
- `thread trace` shows both `search_support_tickets` and `get_support_ticket`.

## 4) Redis Enterprise Cluster Creation Defaults

Release item:
- `feat: Allow Redis Enterprise cluster creation to use env admin defaults`

### CLI fallback + override

```bash
export REDIS_ENTERPRISE_ADMIN_URL='https://re-admin.example.com:9443'
export REDIS_ENTERPRISE_ADMIN_USERNAME='admin@example.com'
export REDIS_ENTERPRISE_ADMIN_PASSWORD='super-secret'

# Uses env defaults
uv run redis-sre-agent cluster create \
  --name "re-cluster-env" \
  --cluster-type redis_enterprise \
  --environment production \
  --description "Should use env defaults" \
  --json

# Explicit args override env values
uv run redis-sre-agent cluster create \
  --name "re-cluster-override" \
  --cluster-type redis_enterprise \
  --environment production \
  --description "Should use explicit values" \
  --admin-url 'https://override.example.com:9443' \
  --admin-username 'override-user' \
  --admin-password 'override-pass' \
  --json

# Verify resolved admin fields on the created cluster
uv run redis-sre-agent cluster get <cluster_id> --json
```

### API fallback

```bash
curl -fsS -X POST http://localhost:8080/api/v1/clusters \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "re-cluster-api-default",
    "cluster_type": "redis_enterprise",
    "environment": "production",
    "description": "API should use env defaults"
  }' | jq
```

## 5) Cluster-Scoped Diagnostics (CLI/API/MCP)

Release item:
- `feat: Cluster-scoped diagnostics across CLI/API/UI/MCP`

### CLI path (fan-out verified)

```bash
uv run redis-sre-agent query \
  -c <cluster_id> \
  "Check this cluster for connectivity and memory pressure"
```

Expected:
- CLI output shows `Agent: Triage (selected)` for diagnostic prompts.
- Cluster-scoped diagnostic prompts are upgraded to triage.
- Linked instances are inspected in fan-out mode.
- Unhealthy linked instances are called out in the response.

### API path

```bash
curl -fsS -X POST http://localhost:8080/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "Check this cluster for connectivity and memory pressure",
    "context": {"cluster_id": "<cluster_id>"}
  }' | jq
```

Then poll task status:

```bash
curl -fsS http://localhost:8080/api/v1/tasks/<task_id> | jq
```

### MCP path

Create a task with `redis_sre_deep_triage` and poll to completion:

1. `redis_sre_deep_triage(query="Check this cluster for connectivity and memory pressure", cluster_id="<cluster_id>")`
2. `redis_sre_get_task_status(task_id="<task_id>")` until status is `done`
3. Optional: `redis_sre_get_thread(thread_id="<thread_id>")` for full transcript

## 6) Redis Connection Documentation Updates

Release item:
- `docs: ... establishing Redis connections`

Use the updated connection guide for:
- Cluster-first Redis Enterprise flow (`cluster create` first, then `instance create --cluster-id`)
- Env-default credential fallback for enterprise cluster creation in CLI and API

Reference:
- [How to connect to Redis](./connect-to-redis.md)

## Known Caveats from Real Validation

- CLI/API outputs use different JSON envelope keys by command path.
- On fresh Redis databases, run `index recreate --yes` before ingestion/query flows to avoid `No such index` errors.
- `thread trace` is available only when a response has a stored decision trace (typically responses involving tool calls).
- The docs examples here use command forms that are valid in `v0.2.8` CLI help output.

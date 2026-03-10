# Redis SRE Agent v0.2.8 Release Notes Tutorial

## Scope
- Release tested: https://github.com/redis-applied-ai/redis-sre-agent/releases/tag/v0.2.8
- Docs tested: https://redis-applied-ai.github.io/redis-sre-agent/
- Test date: 2026-03-09 (America/Los_Angeles)

## Environment I Used
- OS: macOS 15.7.1 (arm64)
- Python: 3.12.9
- `uv`: 0.9.15
- Redis: `redis:8` on `localhost:7853`
- API: `uv run uvicorn redis_sre_agent.api.app:app --port 8090`
- Worker: `uv run redis-sre-agent worker start`
- Repo/tag tested: `v0.2.8` (commit `4a95198`)
- Version command output at this tag: `redis-sre-agent 0.2.7`

## 1) Knowledge Agent First-Turn Tool Call + Citation Tracing
### Release items
- fix: Force tool call on first turn in knowledge agent
- docs: citation tracing via thread get/trace

### Docs used
- https://redis-applied-ai.github.io/redis-sre-agent/how-to/cli/#citations-in-thread-history

### What I tried
1. Knowledge query on a fresh thread, then trace the decision ID.
2. Chat query with support-ticket retrieval, then inspect `thread get`, `thread trace`, `thread sources`.

### Result
- First-turn knowledge query did execute tool calls (`knowledge_*_search`) immediately.
- `thread trace <message_id>` showed tool envelopes and arguments/results.
- `thread get <thread_id>` contained follow-up system source messages (`Sources for previous response`).
- `thread sources <thread_id>` returned `0` for my support-ticket thread despite source system messages.

### User-facing tutorial steps
```bash
# Run a knowledge query
uv run redis-sre-agent query --agent knowledge \
  "What is the default Redis eviction behavior when maxmemory is not set?"

# Use the printed thread ID + decision trace ID
uv run redis-sre-agent thread get <thread_id> --json
uv run redis-sre-agent thread trace <decision_trace_or_message_id> --json
uv run redis-sre-agent thread sources <thread_id> --json
```

## 2) RedisCluster / RedisInstance Split
### Release item
- feat: Split RedisCluster from RedisInstance

### Docs used
- https://redis-applied-ai.github.io/redis-sre-agent/how-to/api/#3-manage-redis-instances-with-optional-cluster-links
- https://redis-applied-ai.github.io/redis-sre-agent/how-to/connect-to-redis/

### What I tried
1. CLI path: created cluster, created instance linked via `--cluster-id`, listed/get both.
2. API path: created cluster and linked instances through `/api/v1/clusters` and `/api/v1/instances`.
3. Migration path: created legacy enterprise instance with deprecated `admin_*`, then ran backfill.

### Result
- Split model works: clusters and instances are separate records, with `cluster_id` linkage.
- Backfill works with `--force`; it created a cluster and linked legacy enterprise instance.
- Observed caveats while testing:
  - API allowed mismatched link (`instance_type=oss_single` linked to `cluster_type=redis_cloud`).
  - Rapid creates in same second can collide IDs (timestamp-based IDs).

### User-facing tutorial steps
```bash
# Create cluster
uv run redis-sre-agent cluster create \
  --name "oss-cluster-a" \
  --cluster-type oss_cluster \
  --environment production \
  --description "OSS cluster for v0.2.8 test" \
  --json

# Create linked instance
uv run redis-sre-agent instance create \
  --name "oss-inst-a" \
  --connection-url "redis://localhost:7853/0" \
  --environment production \
  --usage cache \
  --description "Linked OSS instance" \
  --instance-type oss_cluster \
  --cluster-id <cluster_id> \
  --json

# Verify
uv run redis-sre-agent cluster get <cluster_id> --json
uv run redis-sre-agent instance get <instance_id> --json

# Backfill legacy instance->cluster links (if needed)
uv run redis-sre-agent cluster backfill-instance-links --dry-run --json
uv run redis-sre-agent cluster backfill-instance-links --force --json
```

## 3) Pinned Docs, Skills, and Support Tickets
### Release item
- feat: pinned docs, skills, and support tickets

### Docs used
- https://redis-applied-ai.github.io/redis-sre-agent/how-to/source-document-features/

### What I tried
1. Created custom source files with front matter:
- one `pinned: true` runbook,
- one `doc_type: skill`,
- one `doc_type: support_ticket`.
2. Ran `pipeline prepare-sources` and `pipeline ingest`.
3. Queried pinned policy, skill lookup, and support-ticket retrieval (two-turn flow).

### Result
- Pinned content was injected and used in direct responses (`RDX-911` policy answer).
- Skill retrieval worked (`failover-investigation` loaded by name).
- Support-ticket tools worked (`search_support_tickets` and `get_support_ticket` showed in trace).

### User-facing tutorial steps
```bash
# Prepare + ingest your source docs with front matter
uv run redis-sre-agent pipeline prepare-sources \
  --source-dir /path/to/source-docs \
  --batch-date 2099-01-04 \
  --prepare-only

uv run redis-sre-agent pipeline ingest --batch-date 2099-01-04

# Pinned doc behavior
uv run redis-sre-agent query --agent chat \
  "For sev-1 Redis incidents, what escalation code must we post?"

# Skill behavior
uv run redis-sre-agent query --agent chat \
  "Do we have a skill named failover-investigation? Summarize it."

# Support-ticket behavior (2 turns)
uv run redis-sre-agent query --agent chat \
  "Can you find relevant support tickets for failover resets?"
uv run redis-sre-agent query --agent chat --thread-id <thread_id> \
  "Host is cache-prod-1.redis.company.net and errors are ECONNRESET during failover."
```

## 4) Redis Enterprise Cluster Creation Defaults
### Release item
- feat: Allow Redis Enterprise cluster creation to use env admin defaults

### Docs used
- https://redis-applied-ai.github.io/redis-sre-agent/how-to/connect-to-redis/#redis-enterprise-cluster-creation-defaults-apicli

### What I tried
1. CLI create enterprise cluster without env defaults.
2. CLI create with env defaults set.
3. CLI create with explicit args overriding env defaults.
4. API create with env defaults set on API process.
5. API create with explicit admin fields overriding env defaults.

### Result
- Env fallback works for both CLI and API.
- Explicit values override env defaults as documented.
- CLI no-env failure currently returns an error JSON but exit code `0`.

### User-facing tutorial steps
```bash
# Set defaults
export REDIS_ENTERPRISE_ADMIN_URL='https://re-admin.example.com:9443'
export REDIS_ENTERPRISE_ADMIN_USERNAME='admin@example.com'
export REDIS_ENTERPRISE_ADMIN_PASSWORD='super-secret'

# CLI (no admin args)
uv run redis-sre-agent cluster create \
  --name re-cluster-env \
  --cluster-type redis_enterprise \
  --environment production \
  --description "Uses env defaults" \
  --json

# API (no admin fields)
curl -fsS -X POST http://localhost:8090/api/v1/clusters \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "re-cluster-api-default",
    "cluster_type": "redis_enterprise",
    "environment": "production",
    "description": "Uses env defaults"
  }' | jq
```

## 5) Cluster-Scoped Diagnostics (CLI/API/MCP)
### Release item
- feat: Cluster-scoped diagnostics: route to triage, fan out linked-instance checks, and add CLI/API/UI/MCP support

### Docs used
- https://redis-applied-ai.github.io/redis-sre-agent/how-to/cli/
- https://redis-applied-ai.github.io/redis-sre-agent/how-to/api/

### What I tried
1. CLI auto route with `-c <cluster_id>`.
2. CLI explicit `--agent triage -c <cluster_id>`.
3. API task with `context.cluster_id`.
4. MCP deep triage call with `cluster_id`.

### Result
- CLI auto route upgraded cluster diagnostic query to Triage and performed fan-out across linked instances.
- Fan-out captured partial failure on unreachable linked instance and still returned useful cluster summary.
- API task with `context.cluster_id` worked and included `cluster_context` update.
- Explicit `--agent chat -c <cluster_id>` did not fan-out (asked for identifiers); triage behavior is reliable with auto/triage.
- MCP tool accepts `cluster_id`; end-to-end depends on having discoverable/valid cluster IDs in MCP-managed data.

### User-facing tutorial steps
```bash
# CLI: auto route (recommended)
uv run redis-sre-agent query -c <cluster_id> \
  "Check this cluster for connectivity and memory pressure"

# CLI: force triage
uv run redis-sre-agent query --agent triage -c <cluster_id> \
  "Check connectivity only"

# API: cluster-scoped task
curl -fsS -X POST http://localhost:8090/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "Check this cluster for connectivity and memory pressure",
    "context": {"cluster_id": "<cluster_id>"}
  }' | jq
```

## Practical Recommendations
- Prefer `query -c <cluster_id>` with auto/triage when you want fan-out diagnostics.
- Use `thread get` + `thread trace` for provenance; rely on `thread sources` only after verifying it returns expected data in your setup.
- If you create entities in scripts, add short sleeps or uniqueness in names/IDs to avoid timestamp-collision edge cases.

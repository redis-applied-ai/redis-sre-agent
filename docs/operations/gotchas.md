## Gotchas and Rough Spots

Known issues, limitations, and things that might trip you up. This is an early release - some rough edges are still being smoothed out.

---

## Architecture and Design Limitations

### Tool provider configuration per instance is clunky
Each Redis instance may need specific configuration for tool providers (e.g., different Prometheus label selectors, different Loki tenant IDs). Currently:
- Store these in the instance's `extension_data` (tool provider config)
- Store secrets in `extension_secrets` (tool provider secrets)
- Access via instance API or CLI

**Note**: The preferred approach for tool provider secrets is environment variables, but there may be cases where you need to store instance-specific secrets for a tool provider.

**The problem**: This works but isn't elegant. You're managing per-instance config in JSON blobs rather than a structured interface.

**Future direction**: We're exploring better patterns for per-instance tool configuration, possibly with provider-specific schemas and validation.

### Envelope encryption uses environment variable for master key
The agent uses envelope encryption to protect secrets (connection URLs, passwords, API keys) stored in Redis. The encryption works like this:
1. Master key (32-byte secret) is stored in `REDIS_SRE_MASTER_KEY` environment variable
2. Data encryption keys (DEKs) are generated per secret
3. DEKs are encrypted with the master key and stored alongside encrypted data

**The problem**: The master key is an environment variable, not integrated with a secrets store (Vault, AWS Secrets Manager, etc.). For some users, this is a non-starter.

**Workarounds**:
- Use your orchestration system's secrets management (Kubernetes Secrets, systemd credentials, etc.) to inject the env var
- Rotate the master key periodically (requires re-encrypting all secrets)

**Future direction**: Direct integration with secrets stores is on the roadmap.

### AI agent connecting to production databases requires storing connection secrets
The Redis Command diagnostics provider is useful (especially if you're not already scraping `INFO` metrics), but it requires storing the target database's connection URL.

**Important**: The agent can never run commands directly on the target instance. It can only use the tool provider interface, which exposes read-only commands indirectly (via redis-py, not CLI access).

**The risks**:
- Connection URLs must be stored in the agent's operational Redis (encrypted, but still stored)
- Misconfigured agent could connect to the wrong instance
- Compromised agent deployment could leak connection credentials
- Audit trail for agent actions may not meet compliance requirements

**Mitigations**:
- **Disable the Redis Command provider entirely**: Remove `redis_sre_agent.tools.diagnostics.redis_command.provider.RedisCommandToolProvider` from `TOOL_PROVIDERS` env var. The agent will rely on Prometheus/Loki instead.
- Use read-only Redis users for the agent (ACLs with `+@read -@write -@dangerous`)
- Deploy agent as a sidecar to the database and inject connection URL at runtime (requires custom scripting currently)
- Monitor agent actions via OpenTelemetry traces and logs
- Use network policies to restrict agent connectivity

**Future direction**: Better patterns for sidecar deployment and runtime credential injection are being explored. The correct design is still simmering.

### Triage sessions can be slow (7-10 minutes)
The agent's deep-research approach is thorough but slow. A single triage session can take 7-10 minutes due to:
- **Deep research**: Parallel research tracks with multiple tool-calling loops
- **GPT-4o**: Default model choice (high quality, but slower than GPT-3.5)
- **Large context**: Metrics and log data can be substantial (thousands of lines)
- **Multiple LLM calls**: Each research track makes 1-2 generation calls, often 1-2 minutes each

**The tradeoff**: Slow but valuable. The agent produces thorough analysis with actionable recommendations.

**Workarounds**:
- Use a faster model: Set `OPENAI_MODEL=gpt-3.5-turbo` (lower quality, faster)
- Reduce max iterations: Set `MAX_ITERATIONS=15` (less thorough, faster)
- Limit tool timeouts: Set `TOOL_TIMEOUT=30` (less data gathering, faster)
- Use schedules for non-urgent checks (run overnight, review results in the morning)

**Future direction**: We're exploring ways to make "intensity" configurable (think harder vs. don't think too much). Options under consideration:
- Query-time intensity parameter (quick scan vs. deep dive)
- Streaming partial results (show findings as they arrive)
- Smarter context pruning (send less data to LLM without losing signal)

---

## General

### Docker-compose is not for production
The `docker-compose.yml` setup is for local development and testing only. It includes:
- Demo Redis instances
- Full observability stack (Prometheus, Grafana, Loki, Tempo)
- Redis Enterprise test cluster

For production, deploy the agent on VMs or in a container orchestration system and connect to your existing observability infrastructure.

### Redis Enterprise vs Redis OSS
The agent requires Redis with the RediSearch module for vector search. Options:
- **Redis Enterprise**: RediSearch included, recommended for production
- **Redis Stack**: RediSearch included, good for development
- **Redis OSS**: Requires manual RediSearch module installation

Redis 8.x is recommended. Redis 7.x works but may have different module versions.

---

## Configuration

### Master key is required for production
The `REDIS_SRE_MASTER_KEY` is used for envelope encryption of secrets (connection URLs, passwords, API keys). Without it:
- Secrets are stored in plaintext in Redis
- You'll see warnings in logs
- Not suitable for production

Generate a 32-byte base64 key:
```bash
python3 -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())'
```

### Environment variables vs .env file
- `.env` file is loaded automatically in development
- In production, use environment variables directly (systemd, Kubernetes, etc.)
- Don't commit `.env` to version control
- Docker-compose mounts `.env` as a volume (dev convenience only)

### REDIS_URL port confusion
The agent's operational Redis (where it stores state) defaults to port 7843 in docker-compose to avoid conflicts with target Redis instances on 6379. In production:
- Use whatever port your Redis Enterprise database is on
- Don't confuse the agent's operational Redis with target instances you're monitoring

---

## Knowledge Base

### Ingestion is slow on first run
The first ingestion run:
- Downloads and processes all source documents
- Generates embeddings for thousands of chunks
- Can take 10-30 minutes depending on document count and OpenAI rate limits

Subsequent runs are faster (incremental updates only).

### Artifacts directory is large
The `./artifacts` directory contains:
- Scraped documents (JSON)
- Processed chunks
- Batch manifests

Expect 500MB-2GB depending on how many docs you ingest. This is normal.

### "Latest only" flag is important
When ingesting Redis docs, use `--latest-only` to skip versioned docs (7.4, 7.2, etc.) and only index the latest version. Without this flag:
- You'll index duplicate content across versions
- Knowledge base will be 3-5x larger
- Retrieval quality may suffer from version confusion

### Vector index requires memory
RediSearch vector indexes are memory-resident. For ~12,000 chunks with 1536-dimensional embeddings:
- Expect ~500MB-1GB of Redis memory usage
- Plan Redis memory accordingly
- Monitor with `FT.INFO` command

---

## Agent Behavior

### "Without Redis instance details" vs "With Redis instance details"
This is the key distinction:
- **Without instance details**: Agent uses knowledge base only (docs, runbooks)
- **With instance details**: Agent uses tools (Prometheus, Loki, Redis CLI) for live triage

Don't expect live diagnostics without providing an instance_id.

### Parallel research can be expensive
The triage agent uses parallel research tracks, which means:
- Multiple LLM calls in parallel
- Higher token usage than simple Q&A
- Faster results but higher cost

Monitor LLM token usage via Prometheus metrics at `/api/v1/metrics`.

### Tool timeouts
Default tool timeout is 60 seconds (`TOOL_TIMEOUT=60`). If Prometheus/Loki queries are slow:
- Increase timeout in `.env`
- Check network latency to observability systems
- Review Prometheus/Loki query performance

### Max iterations limit
The agent has a max iterations limit (`MAX_ITERATIONS=25`) to prevent runaway loops. If you see "max iterations reached":
- The query was too complex or ambiguous
- Try breaking it into smaller, more specific queries
- Increase `MAX_ITERATIONS` if needed (but monitor costs)

---

## Worker and Tasks

### Worker must be running
Tasks are queued but won't execute without a worker. Symptoms:
- Tasks stuck in "queued" status
- No progress updates
- Health check shows 0 workers

Solution: Start the worker with `uv run redis-sre-agent worker`

### Worker concurrency affects memory
Default concurrency is 4 (`--concurrency 4`). Each concurrent task:
- Loads LangGraph state
- May hold LLM context in memory
- Runs tool calls

If you see high memory usage, reduce concurrency to 2 or 1.

### Task redelivery timeout
Tasks have a redelivery timeout (default: 300 seconds from `TASK_TIMEOUT`). If a worker crashes:
- Task will be redelivered to another worker after timeout
- May result in duplicate work if the first worker recovers
- Monitor worker health to avoid this

---

## Tool Providers

### Prometheus queries need labels
When using the Prometheus provider, queries need proper label selectors. Bad query:
```
redis_memory_used_bytes
```

Good query:
```
redis_memory_used_bytes{instance="redis-prod-cache:6379"}
```

The agent will try to add instance labels automatically, but explicit labels are more reliable.

### Loki requires LogQL syntax
Loki queries use LogQL, not PromQL. The agent knows this, but if you're debugging:
- Use `{service="redis"}` for stream selectors
- Use `|= "error"` for line filters
- Use `| json` for JSON parsing

### Redis Command provider needs network access
The Redis Command provider connects to target instances via redis-py. Ensure:
- Network connectivity from agent to target Redis
- Correct connection URL (including auth)
- Firewall rules allow access

---

## Performance

### First query is slow
The first query after startup:
- Loads embedding model into memory
- Initializes LangGraph checkpointer
- May download model weights

Expect 10-30 seconds for first query, then <5 seconds for subsequent queries.

### Embedding model memory usage
The default embedding model (`text-embedding-3-small`) uses ~500MB RAM when loaded. This is per-process:
- API process: 500MB
- Worker process: 500MB (per worker if using multiple workers)

Plan memory accordingly.

---

## Observability

### Metrics endpoint is not scraped by default
The agent exposes Prometheus metrics at `/api/v1/metrics`, but you need to configure Prometheus to scrape it. It won't auto-register.

### Worker metrics on different port
Worker metrics are on port 9101, not 8000. Configure Prometheus to scrape both:
- API: `http://agent:8000/api/v1/metrics`
- Worker: `http://agent:9101/`

**Note**: It's awkward that these aren't both on `/api/v1/metrics`, but the worker is a separate process without the FastAPI app.

### OpenTelemetry is opt-in
OTel tracing is disabled by default. Enable with `OTEL_EXPORTER_OTLP_ENDPOINT`. Without it:
- No distributed traces
- No LangGraph node visibility in trace tools (other than LangSmith, if you've enabled that)
- Debugging complex workflows is harder

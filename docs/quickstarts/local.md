## Local Quickstart (Docker Compose)

Use this path when you want the fastest local demo with a seeded Redis target, API, worker, dashboards, and UI.

### Prerequisites

- Docker with Compose v2
- OpenAI API key or compatible endpoint
- Optional: `curl` for quick health checks

### 1) Configure environment

```bash
cp .env.example .env
# Set OPENAI_API_KEY
# Generate REDIS_SRE_MASTER_KEY with:
# python3 -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())'
```

### 2) Run the seeded demo

```bash
make quick-demo
```

The helper does four things:

- Starts the local evaluation stack with Docker Compose
- Seeds `redis-demo` with sample keys
- Registers a demo Redis target with the agent
- Prints next-step commands for knowledge mode and live triage

### 3) Ask your first question

Start with a knowledge-only question that needs no target setup:

```bash
docker compose exec -T sre-agent uv run redis-sre-agent \
  query "What are Redis eviction policies?"
```

Then inspect the seeded demo target and run live triage:

```bash
docker compose exec -T sre-agent uv run redis-sre-agent instance list

docker compose exec -T sre-agent uv run redis-sre-agent \
  query "Check memory pressure and slow ops" -r <instance_id>
```

### 4) Verify the stack

```bash
curl -fsS http://localhost:8080/
curl -fsS http://localhost:8080/api/v1/health | jq
curl -fsS http://localhost:9090/-/ready
```

### Access points

- API: <http://localhost:8080>
- UI: <http://localhost:3002>
- Grafana: <http://localhost:3001> (`admin` / `admin`)
- Prometheus: <http://localhost:9090>
- Agent Redis: `redis://localhost:7843/0`
- Demo Redis: `redis://localhost:7844/0`

### Run the CLI on your host instead of in the container

```bash
uv sync --dev

uv run redis-sre-agent instance create \
  --name demo \
  --connection-url redis://localhost:7844/0 \
  --environment development \
  --usage cache \
  --description "Demo Redis"
```

### Cleanup

```bash
docker compose down
```

### Next steps
- Full Docker walkthrough: [quickstarts/end-to-end-setup.md](end-to-end-setup.md)
- VM deployment: [quickstarts/vm-deployment.md](vm-deployment.md)
- Agent Memory Server integration: [how-to/agent-memory-server-integration.md](../how-to/agent-memory-server-integration.md)
- UI details: [ui/experimental.md](../ui/experimental.md)
- Knowledge ingestion: `uv run redis-sre-agent pipeline prepare-sources` then `uv run redis-sre-agent pipeline ingest`

### See also

- Configuration: [how-to/configuration.md](../how-to/configuration.md)
- Tool Providers: [how-to/tool-providers.md](../how-to/tool-providers.md)
- Encryption: [how-to/configuration/encryption.md](../how-to/configuration/encryption.md)

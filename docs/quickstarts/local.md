## Local Quickstart (Docker Compose)

This gets the API, Worker, monitoring stack, and optional Experimental UI running locally.

### Prerequisites
- Docker and Docker Compose (v2)
- OpenAI API key
- Optional: curl for simple checks

### 1) Configure environment
```bash
cp .env.example .env
# Edit .env and set at least:
# OPENAI_API_KEY=your_key
```

### 2) Start core services (no Redis Enterprise)
Recommended minimal stack:
```bash
docker compose up -d \
  redis redis-demo redis-exporter redis-exporter-agent pushgateway \
  prometheus grafana loki promtail \
  sre-agent sre-worker sre-ui
```
Notes:
- API: http://localhost:8080
- Grafana: http://localhost:3001 (admin/admin)
- Experimental UI: http://localhost:3002 (proxied to API)

### 3) Check status
```bash
# API root health
curl http://localhost:8080/
# Detailed health (Redis, Docket/worker availability, etc.)
curl http://localhost:8080/api/v1/health
# Prometheus
curl http://localhost:9090/-/ready
```

### 4) Create a demo Redis instance (inside container)
The demo Redis runs as `redis-demo` in Compose.
```bash
# Create instance
docker compose exec -T sre-agent uv run redis-sre-agent instance create \
  --name demo \
  --connection-url redis://redis-demo:6379/0 \
  --environment development \
  --usage cache \
  --description "Demo Redis"

# List instances to copy the ID
docker compose exec -T sre-agent uv run redis-sre-agent instance list
```

Optional: Run the CLI on your host instead of in the container (requires uv):
```bash
uv sync --dev
# Use localhost port mapping for the demo Redis
uv run redis-sre-agent instance create \
  --name demo \
  --connection-url redis://localhost:7844/0 \
  --environment development \
  --usage cache \
  --description "Demo Redis"
```

### 5) Run your first triage (CLI)
```bash
# Replace <instance_id> with the ID from the list command
docker compose exec -T sre-agent uv run redis-sre-agent \
  query "Check memory pressure and slow ops" -r <instance_id>
```

### 6) Explore dashboards (optional)
- Grafana: http://localhost:3001 (admin/admin)
- Prometheus: http://localhost:9090
- Experimental UI: http://localhost:3002

### Cleanup
```bash
docker compose down
```

### Next steps
- Production Quickstart: docs/quickstarts/production.md
- Experimental UI details: docs/ui/experimental.md
- Knowledge ingestion (optional): `uv run redis-sre-agent pipeline prepare_sources` then `uv run redis-sre-agent pipeline ingest`

### See also
- Configuration: how-to/configuration.md
- Tool Providers: how-to/tool-providers.md
- Advanced Encryption: how-to/configuration/encryption.md

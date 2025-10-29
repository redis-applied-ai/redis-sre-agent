## Minimal Production Quickstart (Docker Compose)

A small, production‑oriented deployment using only the core services: API, Worker, Redis (for the agent itself), and monitoring. This excludes demo services (redis-demo, redis-enterprise, exporters not required by you).

### Prerequisites
- Docker and Docker Compose v2
- OpenAI API key
- A 32‑byte master key for secret encryption (recommended)

### 1) Set secrets and environment
Provide secrets via environment (recommended). Example:
```bash
# Required for LLM
export OPENAI_API_KEY=...

# Recommended: 32‑byte base64 master key for envelope encryption
# Generate: python -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())'
export REDIS_SRE_MASTER_KEY=...

# Optional: Tool endpoints (Prometheus/Grafana)
export TOOLS_PROMETHEUS_URL=http://prometheus:9090
export TOOLS_LOKI_URL=http://loki:3100
```

Notes
- Avoid baking .env into images. Use environment variables or Compose env files in production.
- If fronting the API with a reverse proxy, set CORS/ALLOWED_HOSTS accordingly.

### 2) Build images
```bash
docker compose build sre-agent sre-worker
```

### 3) Start minimal services
```bash
# Minimal core stack (omit demo/enterprise services)
docker compose up -d \
  redis \
  sre-agent sre-worker \
  prometheus grafana \
  loki promtail
```

Ports
- API: http://localhost:8000
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (admin/admin)
- Loki: http://localhost:3100

### 4) Health checks
```bash
# API root
curl -fsS http://localhost:8000/ | sed -n '1p'
# Detailed health (Redis connectivity, worker availability, providers)
curl -fsS http://localhost:8000/api/v1/health | jq '.status,.components'
# Prometheus readiness
curl -fsS http://localhost:9090/-/ready
```

### 5) (Optional) Create a Redis instance for triage
Use your production Redis URL. Example:
```bash
# Create an instance record (inside API container)
docker compose exec -T sre-agent uv run redis-sre-agent instance create \
  --name prod-cache \
  --connection-url redis://your-redis-host:6379/0 \
  --environment production \
  --usage cache \
  --description "Primary Redis"

# Verify
docker compose exec -T sre-agent uv run redis-sre-agent instance list
```

### 6) Smoke test triage and metrics
```bash
# Ask a quick question with instance context (replace <id>)
docker compose exec -T sre-agent uv run redis-sre-agent \
  query "Check for memory pressure" -r <id>

# Confirm metrics are exposed by the API for Prometheus
curl -fsS http://localhost:8000/api/v1/metrics | head -n 20
```

### 7) Rollback and maintenance
- Rollback: `docker compose down` (adds `-v` to remove volumes if needed)
- Logs: `docker compose logs -f sre-agent` and `docker compose logs -f sre-worker`
- Upgrades: rebuild and `docker compose up -d` to roll forward
- Secrets rotation: see Advanced Encryption for rotating `REDIS_SRE_MASTER_KEY`

### Hardening checklist
- Put the API behind TLS and an auth layer (API_KEY if needed)
- Restrict CORS/ALLOWED_HOSTS to trusted origins
- Limit exposed ports publicly (Grafana/Prometheus often internal-only)
- Store secrets in your preferred secrets manager

### See also
- Configuration: how-to/configuration.md
- Tool Providers: how-to/tool-providers.md
- Advanced Encryption: how-to/configuration/encryption.md

---
description: Run the full stack with Compose, including monitoring sidecars.
---

# Docker deployment

Use Docker Compose when you want a reference deployment that mirrors
production layout — agent, worker, Redis, monitoring sidecars — without
provisioning bare metal. This is the same stack the [Local quick
start](../../01_local_quickstart.md) boots, just configured for a
shared host instead of a developer laptop. For air-gapped environments,
see [Airgap deployment](airgap.md); for VM installs, see [VM
deployment](../../03_vm_deployment.md).

**Related:** [Observability](observability.md) ·
[Configuration](../configuration.md)

## Overview

The standard Docker deployment includes:

- **Redis** - Agent state, task queue, and vector storage
- **Direct LLM access** - OpenAI by default, or any OpenAI-compatible endpoint via `OPENAI_BASE_URL`
- **Prometheus/Grafana** - Metrics and dashboards
- **Loki** - Log aggregation
- **Tempo** - Distributed tracing

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/redis-applied-ai/redis-sre-agent.git
cd redis-sre-agent

# Copy example environment
cp .env.example .env
```

### 2. Set Required Environment Variables

Edit `.env`:

```bash
# Required: OpenAI API key
OPENAI_API_KEY=sk-your-openai-key

# Optional: route through a compatible gateway instead of api.openai.com
# OPENAI_BASE_URL=https://your-llm-endpoint.example.com/v1

# API authentication
REDIS_SRE_MASTER_KEY=your-secret-key
```

### 3. Start Services

```bash
# Start core services
docker compose up -d

# View logs
docker compose logs -f sre-agent sre-worker
```

### 4. Access Services

| Service | URL | Credentials |
|---------|-----|-------------|
| SRE Agent API | http://localhost:8080 | `REDIS_SRE_MASTER_KEY` header |
| SRE Agent UI | http://localhost:3002 | - |
| Grafana | http://localhost:3001 | admin / admin |
| Prometheus | http://localhost:9090 | - |

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  SRE Agent  │────▶│   OpenAI    │
│     API     │     │ or gateway  │
└─────────────┘     └─────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│    Redis    │◀────│ SRE Worker  │
│  (state +   │     │ (background │
│   vectors)  │     │   tasks)    │
└─────────────┘     └─────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Prometheus  │────▶│   Grafana   │◀────│    Loki     │
└─────────────┘     └─────────────┘     └─────────────┘
```

## Services

### Core Services

| Service | Purpose | Port |
|---------|---------|------|
| `sre-agent` | API server | 8080 |
| `sre-worker` | Background task processor | - |
| `redis` | Agent state and vectors | 7843 |

### Monitoring Stack

| Service | Purpose | Port |
|---------|---------|------|
| `prometheus` | Metrics collection | 9090 |
| `grafana` | Dashboards | 3001 |
| `loki` | Log aggregation | 3100 |
| `tempo` | Distributed tracing | 3200 |

### Demo/Testing

| Service | Purpose | Port |
|---------|---------|------|
| `redis-demo` | Target Redis for testing | 7844 |
| `redis-demo-replica` | Replica for replication tests | 7845 |
| `redis-exporter` | Redis metrics exporter | 9121 |

## Configuration

### Embedding Models

By default, the standard deployment uses OpenAI embeddings:

```bash
# Default (OpenAI API)
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
VECTOR_DIM=1536
```

For local embeddings (no OpenAI API needed for embeddings):

```bash
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
VECTOR_DIM=384
```

### LLM Configuration

By default, the standard deployment calls OpenAI directly:

```bash
OPENAI_API_KEY=sk-your-openai-key
OPENAI_MODEL=gpt-5
OPENAI_MODEL_MINI=gpt-5-mini
OPENAI_MODEL_NANO=gpt-5-nano
```

To route requests through an OpenAI-compatible gateway instead, set:

```bash
OPENAI_BASE_URL=https://your-llm-endpoint.example.com/v1
OPENAI_API_KEY=your-gateway-api-key
```

### MCP Servers (Optional)

Enable MCP integrations with the `mcp` profile:

```bash
# Start with GitHub MCP server
docker compose --profile mcp up -d
```

For HTTPS MCP (required for Claude Desktop):

```bash
# Generate self-signed certs
./scripts/generate-mcp-certs.sh

# Start with SSL
docker compose --profile ssl up -d
```

## Development Mode

The default compose mounts source code for hot-reload:

```yaml
volumes:
 - ./redis_sre_agent:/app/redis_sre_agent  # Source code
 - ./tests:/app/tests                       # Tests
```

Changes to Python files trigger automatic reload.

## Production Considerations

For production deployments:

1. **Use pre-built images** instead of building from source
2. **Remove volume mounts** for source code
3. **Configure proper secrets management**
4. **Set up persistent storage** for Redis, Prometheus, Grafana
5. **Configure TLS** for all external endpoints
6. **Set resource limits** on containers

### Docker Hub Images

Pre-built images are available on Docker Hub:

| Image | Description |
|-----|-------------|
| `redislabs/redis-sre-agent:latest` | Latest standard API/worker image |
| `redislabs/redis-sre-agent:airgap` | Air-gap API/worker image with bundled models |
| `redislabs/redis-sre-agent:v1.0.0` | Versioned API/worker release (example) |
| `redislabs/redis-sre-agent:v1.0.0-airgap` | Versioned air-gap API/worker release |
| `redislabs/redis-sre-agent-ui:latest` | Latest production UI image |
| `redislabs/redis-sre-agent-ui:airgap` | Air-gap-compatible production UI image |
| `redislabs/redis-sre-agent-ui:v1.0.0` | Versioned UI release (example) |
| `redislabs/redis-sre-agent-ui:v1.0.0-airgap` | Versioned air-gap UI release |

Example production overrides:

```yaml
# compose.prod.yml
services:
  sre-agent:
    image: redislabs/redis-sre-agent:latest
    volumes: []  # Remove dev mounts
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

## Comparison: Standard vs Air-Gapped

| Feature | Standard | Air-Gapped |
|---------|----------|------------|
| Internet required | Yes | No |
| Embedding models | OpenAI API | Bundled HuggingFace |
| LLM access | Direct or OpenAI-compatible endpoint | Customer's internal proxy |
| Redis | Included | Customer provides |
| Image size | ~1.5GB | ~4GB (includes models) |
| MCP servers | Full support | Limited (no npx) |

## Troubleshooting

### Services Won't Start

```bash
# Check logs
docker compose logs sre-agent

# Verify Redis is healthy
docker compose exec redis redis-cli ping
```

### LLM Errors

```bash
# Verify the configured model credentials work
docker compose exec sre-agent python - <<'PY'
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ.get("OPENAI_BASE_URL") or None)
print(client.models.list())
PY
```

### Worker Not Processing Tasks

```bash
# Check worker logs
docker compose logs sre-worker

# Verify worker is connected
curl http://localhost:8080/api/v1/health
```

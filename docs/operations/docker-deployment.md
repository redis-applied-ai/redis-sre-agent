# Docker Deployment Guide

This guide covers deploying Redis SRE Agent using Docker in environments with
internet access. For air-gapped environments, see [Air-Gapped Deployment](airgap-deployment.md).

## Overview

The standard Docker deployment includes:

- **Redis** - Agent state, task queue, and vector storage
- **LiteLLM Proxy** - LLM gateway supporting OpenAI, Anthropic, Azure, etc.
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
# Required: OpenAI API key (used by LiteLLM proxy)
OPENAI_API_KEY=sk-your-openai-key

# Optional: Anthropic for Claude models
ANTHROPIC_API_KEY=sk-ant-your-key

# LiteLLM proxy authentication (clients use this to auth to proxy)
LITELLM_MASTER_KEY=sk-1234

# API authentication
REDIS_SRE_MASTER_KEY=your-secret-key
```

### 3. Start Services

```bash
# Start core services
docker-compose up -d

# View logs
docker-compose logs -f sre-agent sre-worker
```

### 4. Access Services

| Service | URL | Credentials |
|---------|-----|-------------|
| SRE Agent API | http://localhost:8080 | `REDIS_SRE_MASTER_KEY` header |
| SRE Agent UI | http://localhost:3002 | - |
| Grafana | http://localhost:3001 | admin / admin |
| Prometheus | http://localhost:9090 | - |
| LiteLLM UI | http://localhost:4000/ui | admin / admin |

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  SRE Agent  │────▶│   LiteLLM   │────▶│   OpenAI    │
│     API     │     │    Proxy    │     │  Anthropic  │
└─────────────┘     └─────────────┘     └─────────────┘
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
| `litellm` | LLM proxy | 4000 |

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

LiteLLM supports multiple providers. Edit `monitoring/litellm/config.yaml`:

```yaml
model_list:
  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY

  - model_name: claude-3
    litellm_params:
      model: anthropic/claude-3-sonnet-20240229
      api_key: os.environ/ANTHROPIC_API_KEY
```

### MCP Servers (Optional)

Enable MCP integrations with the `mcp` profile:

```bash
# Start with GitHub MCP server
docker-compose --profile mcp up -d
```

For HTTPS MCP (required for Claude Desktop):

```bash
# Generate self-signed certs
./scripts/generate-mcp-certs.sh

# Start with SSL
docker-compose --profile ssl up -d
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

| Tag | Description |
|-----|-------------|
| `redislabs/redis-sre-agent:latest` | Latest standard image |
| `redislabs/redis-sre-agent:airgap` | Air-gap image with bundled models |
| `redislabs/redis-sre-agent:v1.0.0` | Versioned release (example) |
| `redislabs/redis-sre-agent:v1.0.0-airgap` | Versioned air-gap release |

Example production overrides:

```yaml
# docker-compose.prod.yml
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
| LLM access | Direct or LiteLLM | Customer's internal proxy |
| Redis | Included | Customer provides |
| Image size | ~1.5GB | ~4GB (includes models) |
| MCP servers | Full support | Limited (no npx) |

## Troubleshooting

### Services Won't Start

```bash
# Check logs
docker-compose logs sre-agent

# Verify Redis is healthy
docker-compose exec redis redis-cli ping
```

### LLM Errors

```bash
# Test LiteLLM
curl http://localhost:4000/health

# Check LiteLLM logs
docker-compose logs litellm
```

### Worker Not Processing Tasks

```bash
# Check worker logs
docker-compose logs sre-worker

# Verify worker is connected
curl http://localhost:8080/api/v1/health
```

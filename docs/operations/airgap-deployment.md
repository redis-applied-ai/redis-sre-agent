# Air-Gapped Deployment Guide

This guide covers deploying Redis SRE Agent in air-gapped environments where
no internet access is available at runtime. This is common in banks, government
agencies, and other high-security environments.

## Overview

The air-gapped deployment uses:

- **Pre-bundled embedding models** - HuggingFace sentence-transformers included in image
- **External Redis** - Customer provides Redis with RediSearch module
- **Internal LLM proxy** - Customer provides OpenAI-compatible API endpoint
- **No runtime downloads** - Everything needed is in the Docker image

## Prerequisites

### Required Infrastructure

| Component | Description | Notes |
|-----------|-------------|-------|
| Redis | Redis 7+ with RediSearch module | For agent state, task queue, vector storage |
| LLM Proxy | OpenAI-compatible API | Azure OpenAI, vLLM, Ollama, LiteLLM, etc. |

### Optional Infrastructure

| Component | Description | Notes |
|-----------|-------------|-------|
| Prometheus | Metrics server | For `prometheus_query_metrics` tool |
| Loki | Log aggregation | For `loki_query_logs` tool |

## Getting the Air-Gap Image

### Option 1: Mirror from Docker Hub (Recommended)

The air-gap image is published to Docker Hub. Mirror it to your internal
registry (Artifactory, Harbor, etc.):

```bash
# On a machine with internet access
docker pull redislabs/redis-sre-agent:airgap

# Tag for your internal registry
docker tag redislabs/redis-sre-agent:airgap your-artifactory.internal.com/redis-sre-agent:airgap

# Push to internal registry
docker push your-artifactory.internal.com/redis-sre-agent:airgap
```

Then in your air-gapped environment, pull from your internal registry:

```bash
docker pull your-artifactory.internal.com/redis-sre-agent:airgap
```

**Available tags:**

| Tag | Description |
|-----|-------------|
| `airgap` | Latest air-gap image with bundled HuggingFace models |
| `v1.0.0-airgap` | Versioned air-gap image (example) |
| `latest` | Standard image (requires internet for model downloads) |

### Option 2: Build from Source

If you cannot use the published image, build it yourself:

```bash
# Clone the repository
git clone https://github.com/redis-applied-ai/redis-sre-agent.git
cd redis-sre-agent

# Build the air-gap bundle (builds Docker image + creates bundle)
./scripts/build-airgap.sh --output ./airgap-bundle
```

The build script:

1. **Builds the Docker image** from `Dockerfile.airgap` with pre-bundled HuggingFace models
2. **Exports the image** to a portable tarball
3. **Creates a complete bundle** with configuration files

Bundle contents:

- `redis-sre-agent-airgap.tar.gz` (Docker image ~4GB with models)
- `docker-compose.airgap.yml`
- `.env.example`
- `config.yaml`
- `artifacts/` (pre-built knowledge base, if source_documents exist)
- `README.md` (quick start guide)

#### Build Options

```bash
# Custom image tag
./scripts/build-airgap.sh --tag myregistry/sre-agent:v1.0

# Skip knowledge base artifacts
./scripts/build-airgap.sh --skip-artifacts

# Push to internal registry
./scripts/build-airgap.sh --push myregistry.internal.com
```

## Deployment

### 1. Get the Image

**If using mirrored image (Option 1):**

```bash
# Pull from your internal registry
docker pull your-artifactory.internal.com/redis-sre-agent:airgap

# Or for Podman
podman pull your-artifactory.internal.com/redis-sre-agent:airgap
```

**If using build bundle (Option 2):**

```bash
# Transfer airgap-bundle/ to air-gapped environment, then:
docker load < redis-sre-agent-airgap.tar.gz

# Verify
docker images | grep redis-sre-agent
```

### 2. Get Configuration Files

If you mirrored the image, download the configuration files separately:

```bash
# From the repository (on internet-connected machine)
curl -O https://raw.githubusercontent.com/redis-applied-ai/redis-sre-agent/main/docker-compose.airgap.yml
curl -O https://raw.githubusercontent.com/redis-applied-ai/redis-sre-agent/main/.env.airgap.example
```

If you used the build script, these are already in your bundle.

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your internal URLs:

```bash
# Required: Redis connection
# Include credentials in URL if authentication is required:
#   redis://user:password@host:port/db
#   redis://:password@host:port/db  (no username)
#   rediss://user:password@host:port/db  (TLS)
# URL-encode special characters in password: @ -> %40, : -> %3A
REDIS_URL=redis://your-internal-redis:6379/0

# Required: LLM proxy
OPENAI_BASE_URL=https://your-llm-proxy.internal.com/v1
OPENAI_API_KEY=your-internal-key

# Embeddings: Use local model (default, recommended)
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
VECTOR_DIM=384

# Optional: Monitoring
TOOLS_PROMETHEUS_URL=http://your-prometheus:9090
TOOLS_LOKI_URL=http://your-loki:3100
```

### 4. Start Services

```bash
docker-compose -f docker-compose.airgap.yml up -d
```

For Podman:
```bash
podman-compose -f docker-compose.airgap.yml up -d
```

### 5. Initialize Knowledge Base

If you included pre-built artifacts:

```bash
docker-compose -f docker-compose.airgap.yml exec sre-agent \
  redis-sre-agent pipeline ingest --artifacts-path /app/artifacts
```

### 6. Verify Deployment

Test that the knowledge base and vector search are working:

```bash
# Check version
docker-compose -f docker-compose.airgap.yml exec sre-agent \
  redis-sre-agent version

# Test vector search (does not require LLM)
docker-compose -f docker-compose.airgap.yml exec sre-agent \
  redis-sre-agent knowledge search "redis memory management"
```

You should see search results from the knowledge base. This confirms:

- Redis connection is working
- Vector index was created
- Local embeddings are functioning
- Knowledge base was ingested successfully

## Configuration Reference

### Embedding Models

Two models are pre-bundled in the air-gap image:

| Model | Dimensions | Size | Quality |
|-------|------------|------|---------|
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | ~90MB | Good |
| `sentence-transformers/all-mpnet-base-v2` | 768 | ~420MB | Better |

To use the larger model:
```bash
EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
VECTOR_DIM=768
```

!!! warning "Vector Dimension Mismatch"
    If you change `EMBEDDING_MODEL`, you must also update `VECTOR_DIM` and
    re-index your knowledge base. The dimensions must match.

### MCP Servers

The air-gap image includes pre-installed MCP servers that work without internet:

| Server | Status | Notes |
|--------|--------|-------|
| `redis-memory-server` | ✅ Enabled | Pre-installed via `uv tool install`, uses Redis for storage |
| `github` | ✅ Enabled | Pre-installed via `npm install -g`, requires `GITHUB_PERSONAL_ACCESS_TOKEN` |

Both servers are pre-installed in the image so they don't need to download
anything at runtime. The GitHub MCP server uses `mcp-server-github` (the
globally installed binary) instead of `npx`.

!!! note "GitHub Token Required"
    The GitHub MCP server requires `GITHUB_PERSONAL_ACCESS_TOKEN` to be set.
    If you don't need GitHub integration, you can remove the `github` section
    from `config.yaml`.

**To add HTTP-based MCP servers** pointing to internal endpoints:

```yaml
# config.yaml
mcp_servers:
  # ... existing servers ...

  # Add your internal MCP servers here
  internal-tools:
    url: http://your-internal-mcp-server:8080
    transport: streamable_http
```

**To disable all MCP servers** (minimal deployment):

```yaml
# config.yaml
mcp_servers: {}
```

## Troubleshooting

### Image Won't Load

```bash
# Check image integrity
gzip -t redis-sre-agent-airgap.tar.gz

# Try loading with verbose output
docker load -i redis-sre-agent-airgap.tar.gz
```

### Embedding Model Errors

If you see "model not found" errors:
```bash
# Verify HF_HUB_OFFLINE is set
docker-compose exec sre-agent env | grep HF

# Should show:
# HF_HUB_OFFLINE=1
# TRANSFORMERS_OFFLINE=1
```

### Redis Connection Issues

```bash
# Test Redis connectivity
docker-compose exec sre-agent redis-cli -u $REDIS_URL ping
```

### LLM Proxy Issues

```bash
# Test LLM connectivity
docker-compose exec sre-agent curl -s $OPENAI_BASE_URL/models
```

## Security Considerations

1. **No outbound network** - The container makes no external network calls
2. **Secrets management** - Use your organization's secrets management for API keys
3. **Image signing** - Consider signing images before transfer
4. **Audit logging** - Enable audit logging in your Redis instance

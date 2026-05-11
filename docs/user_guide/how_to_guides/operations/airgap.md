---
description: Run the agent without internet access using a local model and pre-built indexes.
---

# Airgap deployment

Reach for this guide when the target environment has no internet access
at runtime — common for banks, government agencies, and other
high-security shops. The deployment uses bundled embedding models, a
local LLM endpoint, and pre-built knowledge indexes so the agent never
has to call out. If your environment can reach the public internet, the
[Docker deployment](docker_deployment.md) is simpler.

**Related:** [Observability](observability.md) ·
[Configuration](../configuration.md)

## Overview

The air-gapped deployment uses:

- **Pre-bundled embedding models** - HuggingFace sentence-transformers included in image
- **External Redis** - Customer provides Redis with RediSearch module
- **Internal LLM proxy** - Customer provides OpenAI-compatible API endpoint
- **No runtime downloads** - Everything needed is in the published Docker images

## Prerequisites

### Required Infrastructure

| Component | Description | Notes |
|-----------|-------------|-------|
| Redis | Redis 7+ with RediSearch module | For agent state, task queue, vector storage |
| LLM Proxy | OpenAI-compatible API | Azure OpenAI, vLLM, Ollama, custom gateway, etc. |

### Optional Infrastructure

| Component | Description | Notes |
|-----------|-------------|-------|
| Prometheus | Metrics server | For `prometheus_query_metrics` tool |
| Loki | Log aggregation | For `loki_query_logs` tool |

## Getting the Air-Gap Images

### Option 1: Mirror from Docker Hub (Recommended)

The air-gap images are published to Docker Hub. Mirror them to your internal
registry (Artifactory, Harbor, etc.):

```bash
# On a machine with internet access
docker pull redislabs/redis-sre-agent:airgap
docker pull redislabs/redis-sre-agent-ui:airgap

# Tag for your internal registry
docker tag redislabs/redis-sre-agent:airgap your-artifactory.internal.com/redis-sre-agent:airgap
docker tag redislabs/redis-sre-agent-ui:airgap your-artifactory.internal.com/redis-sre-agent-ui:airgap

# Push to internal registry
docker push your-artifactory.internal.com/redis-sre-agent:airgap
docker push your-artifactory.internal.com/redis-sre-agent-ui:airgap
```

Then in your air-gapped environment, pull from your internal registry:

```bash
docker pull your-artifactory.internal.com/redis-sre-agent:airgap
docker pull your-artifactory.internal.com/redis-sre-agent-ui:airgap
```

**Available agent tags:**

| Tag | Description |
|-----|-------------|
| `airgap` | Latest air-gap image with bundled HuggingFace models |
| `v1.0.0-airgap` | Versioned air-gap image (example) |
| `latest` | Standard image (requires internet for model downloads) |

**Available UI tags:**

| Tag | Description |
|-----|-------------|
| `airgap` | Latest UI image for no-internet deployments |
| `v1.0.0-airgap` | Versioned air-gap UI image (example) |
| `latest` | Latest standard UI image |

### Option 2: Build from Source

If you cannot use the published image, build it yourself:

```bash
# Clone the repository
git clone https://github.com/redis-applied-ai/redis-sre-agent.git
cd redis-sre-agent

# Build the air-gap bundle (builds Docker images + creates bundle)
./scripts/build-airgap.sh --output ./airgap-bundle
```

The build script:

1. **Builds the agent Docker image** from `Dockerfile.airgap` with pre-bundled HuggingFace models
2. **Builds the UI Docker image** from `ui/Dockerfile` using the production nginx target
3. **Exports the images** to portable tarballs
4. **Creates a complete bundle** with configuration files

Bundle contents:

- `redis-sre-agent-airgap.tar.gz` (Docker image ~4GB with models and KB artifacts)
- `redis-sre-agent-ui-airgap.tar.gz` (optional UI image served by nginx)
- `docker-compose.airgap.yml`
- `.env.example`
- `config.yaml`
- `README.md` (quick start guide)

!!! note "Pre-built Knowledge Base"
    The airgap image includes pre-scraped Redis documentation, Knowledge Base articles
    (from redis.io/kb), and SRE runbooks in `/app/artifacts`. You only need to run the
    **ingest** command after deployment to index them into Redis.

**Build options:**

```bash
# Custom image tag
./scripts/build-airgap.sh --tag myregistry/sre-agent:v1.0

# Custom UI image tag
./scripts/build-airgap.sh --ui-tag myregistry/sre-agent-ui:v1.0-airgap

# Skip knowledge base artifacts
./scripts/build-airgap.sh --skip-artifacts

# Skip building the UI image
./scripts/build-airgap.sh --skip-ui-image

# Push to internal registry
./scripts/build-airgap.sh --push myregistry.internal.com
```

## Deployment

### 1. Get the Images

**If using mirrored image (Option 1):**

```bash
# Pull from your internal registry
docker pull your-artifactory.internal.com/redis-sre-agent:airgap
docker pull your-artifactory.internal.com/redis-sre-agent-ui:airgap

# Or for Podman
podman pull your-artifactory.internal.com/redis-sre-agent:airgap
podman pull your-artifactory.internal.com/redis-sre-agent-ui:airgap
```

**If using build bundle (Option 2):**

```bash
# Transfer airgap-bundle/ to air-gapped environment, then:
docker load < redis-sre-agent-airgap.tar.gz
docker load < redis-sre-agent-ui-airgap.tar.gz

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

# Optional: Published UI image and backend upstream
SRE_UI_IMAGE=your-artifactory.internal.com/redis-sre-agent-ui:airgap
SRE_UI_API_UPSTREAM=http://sre-agent:8000
```

### 4. Start Services

Start the API and worker:

```bash
docker compose -f docker-compose.airgap.yml up -d
```

For Podman:
```bash
podman-compose -f docker-compose.airgap.yml up -d
```

To include the UI image, enable the `ui` profile:

```bash
docker compose --profile ui -f docker-compose.airgap.yml up -d
```

For Podman:
```bash
podman-compose --profile ui -f docker-compose.airgap.yml up -d
```

### 5. Initialize Knowledge Base

The airgap image includes pre-scraped artifacts in `/app/artifacts`. You only need to
**ingest** them into Redis:

```bash
docker compose -f docker-compose.airgap.yml exec sre-agent \
  redis-sre-agent pipeline ingest
```

This generates embeddings using the local model and indexes the content into Redis vector search.

!!! tip "Adding Custom Documents"
    To add your own documents, place markdown files in a mounted volume and run:
    ```bash
    # Prepare your custom docs
    docker compose -f docker-compose.airgap.yml exec sre-agent \
      redis-sre-agent pipeline prepare-sources --source-dir /your/docs

    # Re-ingest to include them
    docker compose -f docker-compose.airgap.yml exec sre-agent \
      redis-sre-agent pipeline ingest
    ```

### 6. Verify Deployment

Test that the knowledge base and vector search are working:

```bash
# Check version
docker compose -f docker-compose.airgap.yml exec sre-agent \
  redis-sre-agent version

# Test vector search (does not require LLM)
docker compose -f docker-compose.airgap.yml exec sre-agent \
  redis-sre-agent knowledge search "redis memory management"
```

You should see search results from the knowledge base. This confirms:

- Redis connection is working
- Vector index was created
- Local embeddings are functioning
- Knowledge base was ingested successfully

## Kubernetes Deployment

For Kubernetes deployments, you'll configure environment variables via ConfigMaps and Secrets
instead of a `.env` file.

!!! warning "Container User Permissions"
    The agent container must run as user `app:app` (UID 1000) to write to `/app/artifacts`
    and `/app/source_documents`. If you're using a restrictive `securityContext`, ensure
    the container runs as this user or mount writable volumes for these paths.

### Example Kubernetes Manifests

**ConfigMap for non-sensitive configuration:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sre-agent-config
data:
  EMBEDDING_PROVIDER: "local"
  EMBEDDING_MODEL: "sentence-transformers/all-MiniLM-L6-v2"
  VECTOR_DIM: "384"
  OPENAI_MODEL: "gpt-4"
  OPENAI_MODEL_MINI: "gpt-4"
  OPENAI_MODEL_NANO: "gpt-4"
```

**Secret for sensitive values:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: sre-agent-secrets
type: Opaque
stringData:
  REDIS_URL: "redis://user:password@redis-host:6379/0"
  OPENAI_BASE_URL: "https://your-llm-proxy.internal.com/v1"
  OPENAI_API_KEY: "your-internal-api-key"
  REDIS_SRE_MASTER_KEY: "your-master-key"
```

**Deployment:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sre-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: sre-agent
  template:
    metadata:
      labels:
        app: sre-agent
    spec:
      securityContext:
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
      containers:
       - name: sre-agent
          image: your-registry.internal.com/redis-sre-agent:airgap
          ports:
           - containerPort: 8000
          envFrom:
           - configMapRef:
                name: sre-agent-config
           - secretRef:
                name: sre-agent-secrets
          volumeMounts:
           - name: artifacts
              mountPath: /app/artifacts
           - name: config
              mountPath: /app/config.yaml
              subPath: config.yaml
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "2Gi"
              cpu: "1000m"
          livenessProbe:
            httpGet:
              path: /api/v1/health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /api/v1/health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
      volumes:
       - name: artifacts
          emptyDir: {}
       - name: config
          configMap:
            name: sre-agent-app-config
---
apiVersion: v1
kind: Service
metadata:
  name: sre-agent
spec:
  selector:
    app: sre-agent
  ports:
   - port: 8000
      targetPort: 8000
```

**Worker Deployment:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sre-agent-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: sre-agent-worker
  template:
    metadata:
      labels:
        app: sre-agent-worker
    spec:
      securityContext:
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
      containers:
       - name: worker
          image: your-registry.internal.com/redis-sre-agent:airgap
          command: ["redis-sre-agent", "worker", "start"]
          envFrom:
           - configMapRef:
                name: sre-agent-config
           - secretRef:
                name: sre-agent-secrets
          volumeMounts:
           - name: config
              mountPath: /app/config.yaml
              subPath: config.yaml
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "2Gi"
              cpu: "1000m"
      volumes:
       - name: config
          configMap:
            name: sre-agent-app-config
```

### Initializing Knowledge Base in Kubernetes

Run a one-time Job to ingest the pre-scraped artifacts into Redis:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: sre-agent-init-kb
spec:
  template:
    spec:
      securityContext:
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
      containers:
       - name: init
          image: your-registry.internal.com/redis-sre-agent:airgap
          command: ["redis-sre-agent", "pipeline", "ingest"]
          envFrom:
           - configMapRef:
                name: sre-agent-config
           - secretRef:
                name: sre-agent-secrets
      restartPolicy: Never
  backoffLimit: 2
```

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
| `github` | ✅ Enabled | Pre-installed via `npm install -g`, requires `GITHUB_PERSONAL_ACCESS_TOKEN` |

Configured MCP servers do not need to download anything at runtime. The GitHub
MCP server uses `mcp-server-github` (the globally installed binary) instead of
`npx`.

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
docker compose exec sre-agent env | grep HF

# Should show:
# HF_HUB_OFFLINE=1
# TRANSFORMERS_OFFLINE=1
```

### Redis Connection Issues

```bash
# Test Redis connectivity
docker compose exec sre-agent redis-cli -u $REDIS_URL ping
```

### LLM Proxy Issues

```bash
# Test LLM connectivity
docker compose exec sre-agent curl -s $OPENAI_BASE_URL/models
```

## Security Considerations

1. **No outbound network** - The container makes no external network calls
2. **Secrets management** - Use your organization's secrets management for API keys
3. **Image signing** - Consider signing images before transfer
4. **Audit logging** - Enable audit logging in your Redis instance

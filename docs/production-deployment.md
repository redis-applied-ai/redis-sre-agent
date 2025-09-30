# Production Deployment Guide

This guide covers deploying the Redis SRE Agent in production environments using Docker, Kubernetes, or infrastructure-as-code tools.

## Overview

The Redis SRE Agent Docker image includes:
- Pre-built knowledge base artifacts from `source_documents/`
- Automatic knowledge base initialization on first startup
- Health checks and graceful shutdown
- Non-root user for security

## Quick Start

### Docker

```bash
# Build the image
docker build -t redis-sre-agent:latest .

# Run with automatic knowledge base initialization
docker run -d \
  --name sre-agent \
  -e REDIS_URL=redis://your-redis:6379/0 \
  -e OPENAI_API_KEY=your-key \
  -p 8000:8000 \
  redis-sre-agent:latest
```

### Docker Compose

```yaml
version: '3.8'

services:
  redis:
    image: redis:8.2.1
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  sre-agent:
    image: redis-sre-agent:latest
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LOG_LEVEL=INFO
    depends_on:
      - redis
    restart: unless-stopped

volumes:
  redis_data:
```

## Kubernetes Deployment

### Basic Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis-sre-agent
spec:
  replicas: 2
  selector:
    matchLabels:
      app: redis-sre-agent
  template:
    metadata:
      labels:
        app: redis-sre-agent
    spec:
      containers:
      - name: sre-agent
        image: your-registry/redis-sre-agent:latest
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_URL
          value: "redis://redis-service:6379/0"
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: sre-agent-secrets
              key: openai-api-key
        - name: LOG_LEVEL
          value: "INFO"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 60
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
---
apiVersion: v1
kind: Service
metadata:
  name: redis-sre-agent
spec:
  selector:
    app: redis-sre-agent
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

### Knowledge Base Initialization Job

For initial setup or updates:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: sre-agent-knowledge-init
spec:
  template:
    spec:
      containers:
      - name: knowledge-init
        image: your-registry/redis-sre-agent:latest
        command:
        - uv
        - run
        - redis-sre-agent
        - pipeline
        - ingest
        - --artifacts-path
        - /app/artifacts
        env:
        - name: REDIS_URL
          value: "redis://redis-service:6379/0"
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: sre-agent-secrets
              key: openai-api-key
      restartPolicy: OnFailure
```

### Scheduled Knowledge Updates

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: sre-agent-knowledge-update
spec:
  schedule: "0 2 * * 0"  # Weekly at 2 AM Sunday
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: knowledge-update
            image: your-registry/redis-sre-agent:latest
            command:
            - uv
            - run
            - redis-sre-agent
            - knowledge
            - update
            - --scrapers
            - redis_kb,redis_docs
            env:
            - name: REDIS_URL
              value: "redis://redis-service:6379/0"
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: sre-agent-secrets
                  key: openai-api-key
          restartPolicy: OnFailure
```

## Terraform Example

```hcl
# main.tf
resource "docker_image" "sre_agent" {
  name = "redis-sre-agent:latest"
  build {
    context = "."
  }
}

resource "docker_container" "redis" {
  name  = "redis"
  image = "redis:8.2.1"

  volumes {
    volume_name    = docker_volume.redis_data.name
    container_path = "/data"
  }

  command = ["redis-server", "--appendonly", "yes"]
}

resource "docker_container" "sre_agent" {
  name  = "sre-agent"
  image = docker_image.sre_agent.image_id

  ports {
    internal = 8000
    external = 8000
  }

  env = [
    "REDIS_URL=redis://${docker_container.redis.name}:6379/0",
    "OPENAI_API_KEY=${var.openai_api_key}",
    "LOG_LEVEL=INFO"
  ]

  depends_on = [docker_container.redis]
}

resource "docker_volume" "redis_data" {
  name = "redis_data"
}

# Initialize knowledge base after deployment
resource "null_resource" "knowledge_init" {
  depends_on = [docker_container.sre_agent]

  provisioner "local-exec" {
    command = <<-EOT
      # Wait for service to be ready
      timeout 60 bash -c 'until curl -sf http://localhost:8000/health; do sleep 2; done'

      # Knowledge base is auto-initialized by entrypoint
      echo "Knowledge base initialization handled by container entrypoint"
    EOT
  }
}
```

## Environment Variables

### Required
- `REDIS_URL`: Redis connection string (e.g., `redis://host:6379/0`)
- `OPENAI_API_KEY`: OpenAI API key for embeddings and LLM

### Optional
- `SKIP_KNOWLEDGE_INIT`: Set to `true` to skip automatic knowledge base initialization (default: `false`)
- `WAIT_FOR_REDIS`: Set to `false` to skip waiting for Redis on startup (default: `true`)
- `LOG_LEVEL`: Logging level (default: `INFO`)
- `EMBEDDING_MODEL`: OpenAI embedding model (default: `text-embedding-3-small`)
- `ARTIFACTS_PATH`: Path to artifacts directory (default: `/app/artifacts`)

## Knowledge Base Management

### Check Status

```bash
curl http://localhost:8000/api/v1/knowledge/status
```

### Manual Initialization

If automatic initialization is skipped or fails:

```bash
# Using Docker
docker exec sre-agent uv run redis-sre-agent pipeline ingest

# Using Kubernetes
kubectl exec -it deployment/redis-sre-agent -- \
  uv run redis-sre-agent pipeline ingest
```

### Update Knowledge Base

```bash
# Scrape and ingest new content
docker exec sre-agent uv run redis-sre-agent knowledge update
```

## Monitoring

### Health Checks

```bash
# Basic health
curl http://localhost:8000/

# Detailed health with component status
curl http://localhost:8000/health
```

### Metrics

```bash
# Prometheus metrics
curl http://localhost:8000/metrics
```

## Troubleshooting

### Knowledge Base Not Initialized

Check logs:
```bash
docker logs sre-agent | grep ENTRYPOINT
```

Manually initialize:
```bash
docker exec sre-agent uv run redis-sre-agent pipeline ingest
```

### Redis Connection Issues

Verify Redis is accessible:
```bash
docker exec sre-agent redis-cli -u $REDIS_URL ping
```

### Out of Memory

Increase container memory limits or adjust Redis maxmemory:
```yaml
resources:
  limits:
    memory: "4Gi"  # Increase from 2Gi
```

## Security Best Practices

1. **Use secrets management** for API keys (Kubernetes Secrets, AWS Secrets Manager, etc.)
2. **Run as non-root user** (already configured in Dockerfile)
3. **Enable TLS** for Redis connections in production
4. **Use network policies** to restrict access
5. **Regularly update** base images and dependencies
6. **Enable audit logging** for compliance

## Performance Tuning

### Redis Configuration

```conf
# redis.conf
maxmemory 4gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
appendonly yes
```

### Agent Configuration

- Adjust `EMBEDDING_MODEL` for cost/performance tradeoff
- Use Redis connection pooling (configured by default)
- Scale horizontally with multiple replicas
- Use Redis Cluster for high availability

## Backup and Recovery

### Backup Knowledge Base

```bash
# Backup Redis data
redis-cli -u $REDIS_URL --rdb /backup/dump.rdb

# Backup artifacts
tar -czf artifacts-backup.tar.gz /app/artifacts
```

### Restore

```bash
# Restore Redis data
redis-cli -u $REDIS_URL --rdb /backup/dump.rdb

# Or re-ingest from artifacts
docker exec sre-agent uv run redis-sre-agent pipeline ingest
```

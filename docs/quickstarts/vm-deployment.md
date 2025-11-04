## VM Deployment with Redis Enterprise

Deploy the Redis SRE Agent on a Linux VM using Redis Enterprise as the application database (for agent state, vector search, and task queues).

This guide covers bare-metal deployment without containers.

---

## Prerequisites

### System Requirements
- **OS**: Linux (Ubuntu 22.04+, Debian 11+, RHEL 8+, or similar)
- **CPU**: 4+ cores recommended (2 minimum)
- **RAM**: 8GB+ recommended (4GB minimum)
- **Disk**: 20GB+ free space (for application, artifacts, and Redis data)
- **Network**: Outbound HTTPS access for OpenAI API and package downloads

### Software Requirements
- **Python**: 3.12 or 3.11 (3.12 recommended)
- **Redis Enterprise**: 7.4+ with RediSearch module enabled
- **uv**: Package manager (installed below)
- **Git**: For cloning the repository
- **curl**: For health checks and testing

### Access Requirements
- OpenAI API key (or OpenAI-compatible endpoint)
- Redis Enterprise connection URL with credentials
- Optional: Prometheus, Loki endpoints for tool providers

---

## 1. Install System Dependencies

### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install -y \
    git \
    curl \
    ca-certificates \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    build-essential \
    redis-tools
```

### RHEL/Rocky/AlmaLinux
```bash
sudo dnf install -y \
    git \
    curl \
    ca-certificates \
    python3.12 \
    python3.12-devel \
    gcc \
    gcc-c++ \
    make \
    redis
```

---

## 2. Install uv Package Manager

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env  # Add uv to PATH
```

Verify installation:
```bash
uv --version
```

---

## 3. Clone and Install the Agent

```bash
# Clone repository
git clone https://github.com/redis-applied-ai/redis-sre-agent.git
cd redis-sre-agent

# Install dependencies in a virtual environment
uv sync

# Verify installation
uv run redis-sre-agent --help
```

---

## 4. Configure Redis Enterprise

### Create a Database
In Redis Enterprise, create a database with:

- **Modules**: RediSearch enabled
- **Memory**: 2GB+ recommended
- **Eviction policy**: `noeviction` (recommended for operational data)
- **Persistence**: AOF or RDB (recommended)

### Get Connection Details
Note your Redis Enterprise connection URL:
```
redis://username:password@redis-enterprise-host:port/0
```

Or for TLS:
```
rediss://username:password@redis-enterprise-host:port/0
```

---

## 5. Configure Environment

Create `.env` file:
```bash
cp .env.example .env
```

Edit `.env` with your configuration:
```bash
# Required: Redis Enterprise connection
REDIS_URL=redis://username:password@your-redis-enterprise:12000/0

# Required: OpenAI API key
OPENAI_API_KEY=sk-your-openai-api-key

# Recommended: Master key for secret encryption (32-byte base64)
# Generate with: python3 -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())'
REDIS_SRE_MASTER_KEY=your-32-byte-base64-key

# Optional: Tool provider endpoints
TOOLS_PROMETHEUS_URL=http://your-prometheus:9090
TOOLS_LOKI_URL=http://your-loki:3100

# Optional: Observability
# OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4318/v1/traces
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=your-langsmith-key
```

---

## 6. Prepare Knowledge Base Artifacts

The agent needs runbooks and documentation ingested into the knowledge base.

### Option A: Use Pre-built Artifacts (Faster)
If you have pre-built artifacts from another environment:
```bash
# Copy artifacts to ./artifacts directory
scp -r user@build-server:/path/to/artifacts ./artifacts
```

### Option B: Build Artifacts Locally
```bash
# Prepare source documents (scrape docs, generate runbooks)
uv run redis-sre-agent pipeline prepare-sources \
    --source-dir ./source_documents \
    --artifacts-path ./artifacts \
    --prepare-only

# This creates a batch in ./artifacts/YYYY-MM-DD/
```

---

## 7. Ingest Knowledge Base

Ingest the prepared artifacts into Redis Enterprise:
```bash
# Find the latest batch
ls -lt ./artifacts/ | head -n 5

# Ingest the batch (replace with your batch date)
uv run redis-sre-agent pipeline ingest \
    --batch-date 2025-01-15 \
    --artifacts-path ./artifacts

# Expected output:
# ✅ Ingestion completed!
#    Batch date: 2025-01-15
#    Documents processed: 450
#    Chunks created: 12500
#    Chunks indexed: 12500
```

This creates vector embeddings and indexes them in Redis Enterprise using RediSearch.

---

## 8. Start the Agent and Worker

The agent consists of two processes:

- **API**: FastAPI server (port 8000)
- **Worker**: Background task processor

### Start the Worker (Terminal 1)
```bash
cd redis-sre-agent
uv run redis-sre-agent worker --concurrency 4
```

Expected output:
```
✅ SRE tasks registered with Docket
✅ Worker started, waiting for SRE tasks... Press Ctrl+C to stop
Prometheus metrics server started on :9101
```

### Start the API (Terminal 2)
```bash
cd redis-sre-agent
uv run uvicorn redis_sre_agent.api.app:app --host 0.0.0.0 --port 8000
```

Expected output:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Verify Health
```bash
# Quick health check
curl -fsS http://localhost:8000/

# Detailed health check
curl -fsS http://localhost:8000/api/v1/health | jq

# Expected: status "healthy" or "degraded" (degraded is OK if workers just started)
```

---

## 9. Create a Target Redis Instance

Create an instance record for a Redis you want to monitor/triage:

```bash
uv run redis-sre-agent instance create \
  --name "Production Cache" \
  --connection-url "redis://prod-redis:6379/0" \
  --environment production \
  --usage cache \
  --description "Primary production cache" \
  --monitoring-identifier "redis-prod-cache" \
  --logging-identifier "redis-prod-cache"

# Output: ✅ Created instance redis-production-1234567890
```

List instances to get the instance ID:
```bash
uv run redis-sre-agent instance list
```

---

## 10. Test the Agent with a Health Check

Run a triage query against your target instance:

```bash
# Replace <instance-id> with the ID from step 9
uv run redis-sre-agent query \
  "Check memory pressure and identify any slow operations" \
  --redis-instance-id <instance-id>
```

The agent will:

1. Create a task and thread
2. Use the triage agent with parallel research tracks
3. Query Prometheus metrics (if configured)
4. Run Redis command diagnostics (INFO, SLOWLOG, etc.)
5. Analyze findings and provide recommendations

Expected output:
```
✅ Task created: task_01JXXXXXXXXXXXXXXXXXXXXX
📋 Thread: thread_01JXXXXXXXXXXXXXXXXXXXXX
🔄 Status: running

[Agent output with analysis and recommendations]

✅ Task completed
```

---

## 11. Production Deployment

### Run as Systemd Services

Create `/etc/systemd/system/redis-sre-worker.service`:
```ini
[Unit]
Description=Redis SRE Agent Worker
After=network.target

[Service]
Type=simple
User=sre-agent
WorkingDirectory=/opt/redis-sre-agent
Environment="PATH=/home/sre-agent/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/sre-agent/.cargo/bin/uv run redis-sre-agent worker --concurrency 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/redis-sre-api.service`:
```ini
[Unit]
Description=Redis SRE Agent API
After=network.target redis-sre-worker.service

[Service]
Type=simple
User=sre-agent
WorkingDirectory=/opt/redis-sre-agent
Environment="PATH=/home/sre-agent/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/sre-agent/.cargo/bin/uv run uvicorn redis_sre_agent.api.app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable redis-sre-worker redis-sre-api
sudo systemctl start redis-sre-worker redis-sre-api

# Check status
sudo systemctl status redis-sre-worker
sudo systemctl status redis-sre-api

# View logs
sudo journalctl -u redis-sre-worker -f
sudo journalctl -u redis-sre-api -f
```

### Reverse Proxy (Optional)
Put the API behind nginx or similar:

```nginx
server {
    listen 443 ssl;
    server_name sre-agent.example.com;

    ssl_certificate /etc/ssl/certs/sre-agent.crt;
    ssl_certificate_key /etc/ssl/private/sre-agent.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/v1/ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 12. Monitoring the Agent

### Prometheus Metrics
The agent exposes metrics at:

- API: `http://localhost:8000/api/v1/metrics`
- Worker: `http://localhost:9101/`

Add to your Prometheus scrape config:
```yaml
scrape_configs:
  - job_name: 'redis-sre-agent'
    static_configs:
      - targets: ['sre-agent-vm:8000']
    metrics_path: /api/v1/metrics

  - job_name: 'redis-sre-worker'
    static_configs:
      - targets: ['sre-agent-vm:9101']
```

### Logs
- Worker logs: `sudo journalctl -u redis-sre-worker -f`
- API logs: `sudo journalctl -u redis-sre-api -f`
- Set `LOG_LEVEL=DEBUG` in `.env` for verbose logging

---

## Troubleshooting

### Agent can't connect to Redis Enterprise
- Verify connection URL and credentials
- Check network connectivity: `redis-cli -u "redis://user:pass@host:port" PING`
- Ensure RediSearch module is enabled: `redis-cli -u "..." MODULE LIST`

### Knowledge base ingestion fails
- Check Redis memory: `redis-cli -u "..." INFO memory`
- Verify RediSearch index: `redis-cli -u "..." FT._LIST`
- Check artifacts directory exists and has content

### Worker not processing tasks
- Verify worker is running: `ps aux | grep redis-sre-agent`
- Check Redis connectivity from worker
- Review worker logs for errors

### High memory usage
- Reduce worker concurrency: `--concurrency 2`
- Limit LLM context in `.env`: `MAX_ITERATIONS=15`
- Monitor with: `ps aux | grep redis-sre-agent`

---

## Next Steps

- Configure schedules for recurring health checks: `docs/how-to/scheduling-flows.md`
- Set up tool providers (Prometheus, Loki): `docs/how-to/tool-providers.md`
- Enable observability (OTel, LangSmith): `docs/operations/observability.md`
- Explore the API: `http://localhost:8000/docs`

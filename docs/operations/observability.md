## Observability & Health

This guide covers how to observe the Redis SRE Agent itself: health checks, metrics, distributed tracing, and logs.

The docker-compose stack includes Prometheus, Grafana, Loki, and Tempo for local development and testing. These are optional in production - use your existing observability infrastructure.

---

## Health Checks

### Quick health check
Fast endpoint for load balancers (no external dependencies):
```bash
curl -fsS http://localhost:8080/
```

### Detailed health check
Checks Redis connectivity, vector index, and worker availability:
```bash
curl -fsS http://localhost:8080/api/v1/health | jq
```

Returns status and component details. Status may be `degraded` if workers aren't running.

---

## Prometheus Metrics

The agent exposes Prometheus metrics at `/api/v1/metrics` for scraping.

### What's exposed
- **Application info**: version, embedding model
- **Redis connection status**: connectivity to the agent's operational Redis
- **Vector index status**: search index health
- **Knowledge base stats**: document count
- **Worker count**: active Docket workers
- **LLM metrics** (from `redis_sre_agent/observability/llm_metrics.py`):
  - `sre_agent_llm_tokens_prompt_total` - prompt tokens by model and component
  - `sre_agent_llm_tokens_completion_total` - completion tokens by model and component
  - `sre_agent_llm_tokens_total` - total tokens by model and component
  - `sre_agent_llm_requests_total` - request count by model, component, and status
  - `sre_agent_llm_duration_seconds` - latency histogram by model and component

### Scrape the API
```bash
curl -fsS http://localhost:8080/api/v1/metrics | head -n 30
```

### Prometheus configuration
Add the agent to your Prometheus scrape config:
```yaml
scrape_configs:
  - job_name: 'sre-agent'
    static_configs:
      - targets: ['sre-agent:8000']
    metrics_path: /api/v1/metrics
    scrape_interval: 30s
```

The worker also exposes metrics on port 9101 (started automatically when the worker runs).

---

## OpenTelemetry Tracing

The agent supports distributed tracing via OpenTelemetry. Tracing is **opt-in** and disabled by default.

### Enable tracing
Set the OTLP endpoint environment variable:
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4318/v1/traces
# Optional: add headers for auth
export OTEL_EXPORTER_OTLP_HEADERS="x-api-key=your-key"
```

Both the API and worker will automatically instrument and export spans when this variable is set.

### What gets traced
- **FastAPI requests** (excluding health/metrics endpoints)
- **Redis operations** (via RedisInstrumentor)
- **HTTP clients** (HTTPX, AioHTTP)
- **OpenAI API calls** (via OpenAIInstrumentor)
- **LangGraph nodes**: Each node in the agent workflow gets a custom span with attributes:
  - `langgraph.graph` - which graph (e.g., `sre_agent`, `knowledge`, `runbook`)
  - `langgraph.node` - which node (e.g., `agent`, `tools`, `reasoning`)
- **LLM calls**: Token usage and latency are added as span attributes

### Example: Tempo (local dev)
The docker-compose stack includes Tempo as an OTLP collector:
```yaml
environment:
  - OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4318/v1/traces
```

Query traces in Grafana (Tempo datasource at `http://tempo:3200`).

### Example: Production
Point to your existing OTLP collector (Jaeger, Honeycomb, Datadog, etc.):
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io/v1/traces
export OTEL_EXPORTER_OTLP_HEADERS="x-honeycomb-team=your-api-key"
```

---

## LangSmith Tracing

LangSmith provides specialized tracing for LangGraph workflows. The agent uses LangChain/LangGraph, so LangSmith works out of the box.

### Enable LangSmith
Set standard LangChain environment variables:
```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=your-langsmith-api-key
export LANGCHAIN_PROJECT=redis-sre-agent
```

LangSmith will capture LangGraph execution, tool calls, and LLM interactions. This is complementary to OpenTelemetry - you can use both simultaneously.

LangGraph nodes are also visible in OpenTelemetry traces due to custom instrumentation in the agent code.

---

## Logs

### Structured logging
The agent uses Python's standard logging with configurable levels:
```bash
export LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

### Local development
View logs from docker-compose services:
```bash
docker compose logs -f sre-agent sre-worker
```

### Centralized logging (optional)
The docker-compose stack includes Loki for testing centralized logging. In production, use your existing log aggregation system (Loki, Elasticsearch, Datadog, etc.).

Promtail is configured in docker-compose to scrape container logs and ship them to Loki.

---

## Local Development Stack

The docker-compose setup includes a full observability stack for testing:
- **Prometheus** (http://localhost:9090) - scrapes agent metrics
- **Grafana** (http://localhost:3001, admin/admin) - visualizes metrics and traces
- **Loki** (http://localhost:3100) - log aggregation
- **Tempo** (http://localhost:3200) - trace storage and querying
- **Promtail** - log shipper

This stack serves two purposes:
1. Test the agent's own observability (metrics, traces, logs)
2. Test the agent's tool providers (Prometheus/Loki providers for querying Redis instance health)

In production, you don't need to run this stack - integrate with your existing observability infrastructure.

---

## Tips

- For long-running triage tasks, watch thread updates via WebSocket instead of polling task status
- Use schedules for recurring health checks and alert from your monitoring system
- Enable OpenTelemetry tracing in production to debug complex agent workflows
- LLM token metrics help track costs and identify expensive operations

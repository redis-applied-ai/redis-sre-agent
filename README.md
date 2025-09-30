# Redis SRE Agent

A LangGraph-based Redis SRE Agent for intelligent infrastructure monitoring and incident response.

## Architecture

**Flow**: API/CLI → LangGraph Agent → SRE Tools → Redis/Monitoring Systems → Automated Response

<img src="images/sre-arch-flow.png" style="max-width: 800px;"/>

## Core Components

- **LangGraph Agent**: Multi-step workflow with semantic caching and quality evaluation
- **SRE Tools**: Metrics queries, log analysis, health checks, runbook search, basic remediation
- **Docket Tasks**: Background processing for data ingestion and long-running operations
- **Redis Infrastructure**: Vector search (RedisVL) + task queue + caching + raw metrics storage
- **FastAPI**: REST endpoints for agent queries and system status

## Quick Start

### Prerequisites
- Python 3.12+, Redis 8+ or 7.x with RediSearch module, UV package manager
- OpenAI API key
- Optional: Prometheus, Grafana access for monitoring integration

### Development Setup
```bash
# Clone and setup
git clone <repo-url>
cd redis-sre-agent

# Install dependencies
uv sync

# Environment setup
cp .env.example .env
# Edit .env with your API keys and configuration

# Start Redis 8
docker run -d -p 6379:6379 redis:8-alpine

# Seed knowledge base (TODO)
uv run python scripts/seed.py

# Start worker (Terminal 1)
uv run python -m redis_sre_agent.worker

# Start API (Terminal 2)
uv run fastapi dev redis_sre_agent/api/app.py
```

### Usage

**API**:
```bash
# Health check
curl http://localhost:8000/health

# Agent query
curl -X POST http://localhost:8000/agent/query \\
  -H "Content-Type: application/json" \\
  -d '{"query": "Check Redis cluster health and memory usage"}'
```

## Configuration

Essential environment variables:
```bash
# Required
OPENAI_API_KEY=your-openai-key
REDIS_URL=redis://localhost:6379/0

# Optional Monitoring
PROMETHEUS_URL=http://prometheus:9090
GRAFANA_URL=http://grafana:3000
GRAFANA_API_KEY=your-grafana-key
```

## SRE Tools

The agent uses a **Protocol-based tool system** that provides extensible interfaces for different SRE capabilities:

- **query_instance_metrics**: Get metrics from Redis instances or monitoring systems (Redis CLI, Prometheus)
- **search_logs**: Pattern analysis and error detection across log providers (CloudWatch, etc.)
- **create_incident_ticket**: Create tickets in incident management systems (GitHub Issues, Jira)
- **search_related_repositories**: Search code across repositories (GitHub, GitLab)
- **list_available_metrics**: Discover available metrics across all providers

For detailed information on implementing custom providers and using the protocol system, see [Protocol-Based Tools Documentation](docs/protocol-tools.md).

## Testing

### Unit Tests
```bash
# Run all unit tests
uv run pytest tests/unit/ -v

# With coverage report
uv run pytest tests/unit/ --cov=redis_sre_agent --cov-report=html --cov-report=term-missing

# Quick test (no coverage)
uv run pytest tests/unit/ -v --tb=short
```

### Integration Tests (Require Service Keys)

**Redis Integration Tests:**
```bash
# Enable Redis integration tests
export INTEGRATION_TESTS=true

# Run with Redis container (requires testcontainers)
uv run pytest tests/integration/test_redis_integration.py -v -m integration
```

**OpenAI Integration Tests:**
```bash
# Enable OpenAI tests (requires API key)
export OPENAI_API_KEY=your-key
export OPENAI_INTEGRATION_TESTS=true

# Run OpenAI integration tests (makes real API calls)
uv run pytest tests/integration/test_openai_integration.py -v -m openai_integration
```

**Docket Task Integration Tests:**
```bash
# Enable Docket integration tests
export DOCKET_INTEGRATION_TESTS=true

# Run Docket tests with real Redis
uv run pytest tests/integration/test_docket_sre_integration.py -v -m docket_integration
```

# Run end-to-end agent tests (real OpenAI + Redis)
uv run pytest tests/integration/test_agent_behavior.py -v -m agent_behavior
```

### Development

#### Backend Development

```bash
# Code formatting
uv run ruff format .
uv run ruff check .

# Type checking
uv run mypy redis_sre_agent/
```

#### Frontend Development

The UI is a React application located in the `ui/` directory with an integrated UI kit:

```bash
# Install dependencies
cd ui && npm install

# Development server
npm run dev

# Production build
npm run build
```

The UI kit components are included in `ui/ui-kit/` and provide reusable React components with consistent styling.

## Architecture Details

### LangGraph Workflow
Based on "Semantic Caching in Agent Workflows" patterns:
1. **Query Decomposition**: Break complex SRE questions into sub-questions
2. **Cache Check**: Semantic matching for previously answered questions
3. **Tool Execution**: Multi-turn problem solving with SRE tools
4. **Quality Evaluation**: Validate responses before caching
5. **Response Synthesis**: Combine results into actionable guidance

### Data Pipeline
Docket tasks for:
- Redis documentation ingestion
- SRE runbook processing
- Metrics data caching
- Log pattern analysis

### Deployment

**Local Development**:
```bash
docker-compose up -d
```

**Production**:
```bash
# Build with pre-built knowledge base artifacts
docker build -t redis-sre-agent:latest .

# Run with automatic knowledge base initialization
docker run -d \
  -e REDIS_URL=redis://your-redis:6379/0 \
  -e OPENAI_API_KEY=your-key \
  -p 8000:8000 \
  redis-sre-agent:latest

# Skip knowledge base initialization if already populated
docker run -d \
  -e SKIP_KNOWLEDGE_INIT=true \
  -e REDIS_URL=redis://your-redis:6379/0 \
  redis-sre-agent:latest
```

The Docker image includes:
- Pre-built knowledge base artifacts from `source_documents/`
- Automatic initialization on first startup
- Redis 8 (or 7.x with RediSearch module) required

## Project Status

🚧 **Under Development** - Core infrastructure and basic agent workflow in progress.

### Roadmap
- [x] Core project structure and configuration
- [x] FastAPI foundation with health checks
- [x] Redis infrastructure (RedisVL + Docket)
- [x] LangGraph agent implementation
- [x] POC of SRE tools (metrics, logs, health checks)
- [x] POC of data pipeline for knowledge ingestion
- [x] API endpoints
- [ ] CLI
- [ ] Monitoring system integrations (in profress)
- [ ] Safety systems / guardrails (in progress)
- [ ] Deployment and testing

---

Built with FastAPI, LangGraph, RedisVL, and Docket for reliable SRE automation.

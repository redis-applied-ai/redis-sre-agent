# Redis SRE Agent

A LangGraph-based Redis SRE Agent for intelligent infrastructure monitoring and incident response.

## Architecture

**Flow**: API/CLI → LangGraph Agent → SRE Tools → Redis/Monitoring Systems → Automated Response

## Core Components

- **LangGraph Agent**: Multi-step workflow with semantic caching and quality evaluation
- **SRE Tools**: Metrics queries, log analysis, health checks, runbook search, basic remediation
- **Docket Tasks**: Background processing for data ingestion and long-running operations
- **Redis Infrastructure**: Vector search (RedisVL) + task queue + caching + raw metrics storage
- **FastAPI**: REST endpoints for agent queries and system status

## Quick Start

### Prerequisites
- Python 3.12+, Redis 8+, UV package manager
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

**CLI** (TODO):
```bash
# Direct agent queries
redis-sre-agent query "What's the current Redis memory usage?"

# System status
redis-sre-agent status
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

The agent has access to these SRE-specific tools:

- **query_metrics**: Get metrics from Prometheus/Grafana
- **analyze_logs**: Pattern analysis and error detection  
- **check_health**: System and service health checks
- **search_runbooks**: Procedure and documentation lookup
- **basic_remediation**: Safe automated fixes (restart services, clear caches)

## Testing

Comprehensive test suite with 79% coverage across unit and integration tests.

### Unit Tests (Fast)
```bash
# Run all unit tests
uv run pytest tests/unit/ -v

# With coverage report
uv run pytest tests/unit/ --cov=redis_sre_agent --cov-report=html --cov-report=term-missing

# Quick test (no coverage)
uv run pytest tests/unit/ -v --tb=short
```

### Integration Tests (Require Services)

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

**Agent Behavior Tests:**
```bash
# Enable agent behavior tests (when agent is implemented)
export AGENT_BEHAVIOR_TESTS=true

# Run end-to-end agent tests (real OpenAI + Redis)
uv run pytest tests/integration/test_agent_behavior.py -v -m agent_behavior
```

### Test Categories

- **Unit Tests**: Mock all external dependencies, fast execution
- **Integration Tests**: Real Redis, real services, slower but thorough
- **OpenAI Tests**: Real OpenAI API calls, validates embeddings and search
- **Agent Behavior Tests**: Full end-to-end workflows with quality evaluation

### Running Specific Test Types
```bash
# Skip expensive tests
uv run pytest -m "not openai_integration and not agent_behavior"

# Only integration tests
uv run pytest -m integration

# Everything except agent behavior
uv run pytest -m "not agent_behavior"
```

### Development
```bash
# Code formatting
uv run ruff format .
uv run ruff check .

# Type checking  
uv run mypy redis_sre_agent/
```

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

**Production**: Docker containers with Redis 8 and monitoring integration.

## Project Status

🚧 **Under Development** - Core infrastructure and basic agent workflow in progress.

### Roadmap
- [ ] Core project structure and configuration
- [ ] FastAPI foundation with health checks
- [ ] Redis infrastructure (RedisVL + Docket)
- [ ] LangGraph agent implementation  
- [ ] SRE tools (metrics, logs, health checks)
- [ ] Data pipeline for knowledge ingestion
- [ ] API endpoints and CLI
- [ ] Monitoring system integrations
- [ ] Deployment and testing

---

Built with FastAPI, LangGraph, RedisVL, and Docket for reliable SRE automation.
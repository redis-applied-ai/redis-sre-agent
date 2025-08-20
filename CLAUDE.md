# Redis SRE Agent - Claude Configuration

## Project Overview
This is a production-ready Redis Site Reliability Engineering (SRE) agent built with LangGraph, FastAPI, and comprehensive monitoring tools. The agent provides automated Redis health monitoring, issue detection, and conversational troubleshooting.

## Architecture Components
- **LangGraph Agent**: Multi-turn conversation with 4 specialized SRE tools
- **FastAPI API**: Production endpoints for agent interaction
- **Redis Monitoring**: 8-category diagnostic analysis system
- **Prometheus Integration**: Time series metrics and alerting
- **Vector Knowledge Base**: SRE runbook search and retrieval
- **Docker Stack**: Complete monitoring environment with Grafana dashboards

## Development Commands

### Environment Setup
```bash
uv sync --dev
uv run python -m redis_sre_agent.cli --help
```

### Testing
```bash
# Run all tests
uv run pytest

# Run with Redis integration tests
uv run pytest -m "not integration"  # Skip integration tests
uv run pytest -m integration        # Run integration tests only

# Test with coverage
uv run pytest --cov=redis_sre_agent --cov-report=html
```

### Docker Environment
```bash
# Start full monitoring stack
docker-compose up -d

# View logs
docker-compose logs -f sre-agent
docker-compose logs -f redis

# Access services
# - SRE Agent API: http://localhost:8000
# - Prometheus: http://localhost:9090  
# - Grafana: http://localhost:3000 (admin/admin)
# - Redis: localhost:6379
```

### Development Workflow
1. Make code changes
2. Run tests: `uv run pytest`
3. Test integration: `docker-compose up --build`
4. Commit changes
5. Create PR

## Key File Locations
- Agent core: `redis_sre_agent/agent/langgraph_agent.py`
- Redis tools: `redis_sre_agent/tools/redis_diagnostics.py`
- API endpoints: `redis_sre_agent/api/app.py`
- Configuration: `redis_sre_agent/config.py`
- Docker config: `docker-compose.yml`
- Redis config: `monitoring/redis.conf`

## Testing Scenarios
The agent handles various Redis issues:
- Memory pressure and eviction policies
- Connection limit problems
- Performance degradation
- Configuration issues
- Slow query analysis
- Client connection problems

## Environment Variables
See `.env.example` for required configuration:
- `OPENAI_API_KEY`: Required for agent functionality
- `REDIS_URL`: Redis connection string
- `PROMETHEUS_URL`: Metrics endpoint
- `GRAFANA_URL`: Dashboard access
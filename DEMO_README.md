# Redis SRE Agent - Full Stack Demo

This is a complete end-to-end demonstration of the Redis SRE Agent system with real monitoring, diagnostics, and knowledge management.

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Prometheus    │    │      Redis      │    │    SRE Agent    │
│   (Metrics)     │◄──►│   (Data Store)  │◄──►│   (LangGraph)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ▲                        ▲                        ▲
         │                        │                        │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Grafana      │    │  Redis Exporter │    │  Data Pipeline  │
│ (Visualization) │    │   (Monitoring)  │    │ (OSS/Ent/Shared)│
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### 1. Start the Monitoring Stack

```bash
# Start all services (Redis, Prometheus, Grafana, SRE Agent)
docker-compose up -d

# Check services are running
docker-compose ps
```

**Service URLs:**
- SRE Agent API: http://localhost:8000
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Redis: localhost:6379

### 2. Populate the Knowledge Base

```bash
# Run the data pipeline to scrape and ingest runbooks
uv run redis-sre-agent pipeline full

# Check pipeline status
uv run redis-sre-agent pipeline status

# View batch details
uv run redis-sre-agent pipeline show-batch $(date +%Y-%m-%d)
```

### 3. Test the SRE Agent

```bash
# Check agent status
curl http://localhost:8000/api/v1/agent/status

# Ask the agent about Redis performance
curl -X POST http://localhost:8000/api/v1/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Redis is running slowly, what should I check?",
    "user_id": "demo-user"
  }'

# Check Redis health directly
curl -X POST http://localhost:8000/api/v1/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Run Redis diagnostics and tell me the health status",
    "user_id": "demo-user"
  }'
```

### 4. Monitor with Prometheus and Grafana

Visit http://localhost:3000 and create dashboards for:
- Redis memory usage: `redis_memory_used_bytes`
- Operations per second: `rate(redis_commands_processed_total[1m])`
- Connected clients: `redis_connected_clients`

## 🛠️ SRE Tools Available

### 1. Real Prometheus Integration
- **`analyze_system_metrics`**: Queries actual Prometheus for Redis metrics
- Supports time ranges (1h, 6h, 1d)
- Anomaly detection using statistical analysis
- Threshold breach detection

### 2. Direct Redis Diagnostics
- **`check_service_health`**: Comprehensive Redis health analysis
- Memory usage analysis and recommendations
- Performance metrics (hit rate, ops/sec)
- Slow query log analysis
- Client connection analysis
- Configuration validation

### 3. Knowledge Base Search
- **`search_knowledge_base`**: Vector search through SRE procedures
- Categorized content: OSS, Enterprise, Shared
- Document types: Runbooks, troubleshooting guides, best practices

### 4. Document Ingestion
- **`ingest_sre_document`**: Add new procedures to knowledge base
- Automatic categorization and vectorization

## 📊 Data Pipeline System

### Two-Stage Architecture

**Stage 1: Scraping** → Dated Artifacts
```bash
# Scrape Redis documentation and runbooks
uv run redis-sre-agent pipeline scrape

# Scrape specific sources
uv run redis-sre-agent pipeline scrape --scrapers redis_docs,redis_runbooks
```

**Stage 2: Ingestion** → Vector Store
```bash
# Ingest today's batch
uv run redis-sre-agent pipeline ingest

# Ingest specific batch
uv run redis-sre-agent pipeline ingest --batch-date 2025-08-20
```

### Content Categories

- **OSS**: Redis open source documentation and runbooks
- **Enterprise**: Redis Enterprise-specific procedures
- **Shared**: Common SRE practices and troubleshooting

### Document Types

- **Runbooks**: Step-by-step operational procedures
- **Troubleshooting**: Problem diagnosis and resolution
- **Documentation**: Reference material and guides
- **Best Practices**: SRE recommendations and patterns

## 🎯 Demo Scenarios

### Scenario 1: Performance Troubleshooting

```bash
# Agent query for performance issues
curl -X POST http://localhost:8000/api/v1/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "CPU usage is at 95% and Redis latency increased to 50ms, what should I do?",
    "user_id": "sre-engineer"
  }'
```

The agent will:
1. Search runbooks for performance troubleshooting procedures
2. Query Prometheus for current CPU metrics
3. Run Redis diagnostics to check for slow queries
4. Provide step-by-step remediation plan

### Scenario 2: Memory Management

```bash
# Memory usage concern
curl -X POST http://localhost:8000/api/v1/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Redis memory usage is at 90%, what are the immediate steps I should take?",
    "user_id": "sre-engineer"
  }'
```

The agent will:
1. Get current memory metrics from Prometheus
2. Run comprehensive Redis memory diagnostics
3. Search for memory troubleshooting runbooks
4. Provide immediate actions and escalation procedures

### Scenario 3: Multi-turn Conversation

```bash
# Initial query
curl -X POST http://localhost:8000/api/v1/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "I need help with Redis monitoring setup",
    "user_id": "sre-engineer",
    "session_id": "monitoring-setup-123"
  }'

# Follow-up in same session
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What specific metrics should I monitor?",
    "session_id": "monitoring-setup-123",
    "user_id": "sre-engineer"
  }'

# Get conversation history
curl http://localhost:8000/api/v1/agent/sessions/monitoring-setup-123/history
```

## 🔧 Configuration

### Environment Variables

```bash
# Core settings
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=your_openai_key

# Monitoring integration
PROMETHEUS_URL=http://localhost:9090
GRAFANA_URL=http://localhost:3000

# Pipeline settings
ARTIFACTS_PATH=./artifacts
```

### Pipeline Configuration

The pipeline can be configured via the orchestrator:

```python
config = {
    "redis_docs": {
        "max_pages": 50,
        "delay_between_requests": 1.0
    },
    "ingestion": {
        "chunk_size": 1000,
        "chunk_overlap": 200
    }
}
```

## 📈 Metrics and Monitoring

### Prometheus Metrics Available

- **Redis Core**: `redis_memory_used_bytes`, `redis_connected_clients`
- **Performance**: `redis_commands_processed_total`, `redis_keyspace_hits_total`
- **System**: `process_cpu_seconds_total`, `node_memory_usage_bytes`

### SRE Agent Metrics

- Agent query response times
- Tool execution success rates
- Knowledge base hit rates
- Pipeline processing statistics

## 🧪 Testing

### Unit Tests
```bash
# Run all tests
uv run pytest

# Test with coverage
uv run pytest --cov=redis_sre_agent --cov-report=html

# Test specific components
uv run pytest tests/unit/test_agent.py -v
```

### Integration Tests
```bash
# OpenAI integration (requires API key)
uv run pytest tests/integration/test_openai_integration.py

# Agent behavior tests
AGENT_BEHAVIOR_TESTS=true uv run pytest tests/integration/test_agent_behavior.py
```

### Manual Testing
```bash
# Test Redis diagnostics
uv run python -c "
from redis_sre_agent.tools.redis_diagnostics import get_redis_diagnostics
import asyncio
async def test():
    diag = get_redis_diagnostics()
    result = await diag.run_diagnostic_suite()
    print(result)
asyncio.run(test())
"

# Test Prometheus client
uv run python -c "
from redis_sre_agent.tools.prometheus_client import get_prometheus_client
import asyncio
async def test():
    prom = get_prometheus_client()
    health = await prom.health_check()
    print(health)
asyncio.run(test())
"
```

## 🚨 Troubleshooting

### Common Issues

1. **Redis Connection Failed**
   ```bash
   # Check Redis is running
   docker-compose ps redis
   
   # Check Redis logs
   docker-compose logs redis
   ```

2. **Prometheus Not Available**
   ```bash
   # Verify Prometheus is up
   curl http://localhost:9090/api/v1/query?query=up
   
   # Check Redis exporter metrics
   curl http://localhost:9121/metrics
   ```

3. **OpenAI API Issues**
   ```bash
   # Verify API key is set
   echo $OPENAI_API_KEY
   
   # Check API connectivity
   uv run python -c "import openai; print(openai.OpenAI().models.list().data[0])"
   ```

4. **Pipeline Failures**
   ```bash
   # Check artifacts directory permissions
   ls -la ./artifacts/
   
   # Run pipeline with debug logging
   export LOG_LEVEL=DEBUG
   uv run redis-sre-agent pipeline scrape
   ```

## 📋 Production Checklist

For production deployment:

- [ ] Configure authentication for all services
- [ ] Set up SSL/TLS certificates
- [ ] Configure persistent storage for Redis
- [ ] Set up alerting rules in Prometheus
- [ ] Configure log aggregation
- [ ] Set up backup procedures for artifacts
- [ ] Configure resource limits in Docker
- [ ] Set up monitoring dashboards in Grafana
- [ ] Configure rate limiting for agent API
- [ ] Set up proper secrets management

## 🎉 What's Included

This demo provides a complete SRE agent system with:

✅ **LangGraph Agent**: Multi-turn conversations with tool calling  
✅ **Real Monitoring**: Prometheus + Grafana + Redis exporters  
✅ **Direct Diagnostics**: Comprehensive Redis health analysis  
✅ **Knowledge Pipeline**: OSS/Enterprise/Shared document processing  
✅ **Vector Search**: Semantic search through SRE procedures  
✅ **REST API**: Complete API for agent interactions  
✅ **CLI Tools**: Pipeline management and operations  
✅ **Docker Stack**: Production-ready containerized services  
✅ **Testing Suite**: Unit, integration, and behavior tests  

The system demonstrates real-world SRE operations with actual monitoring data, diagnostic tools, and knowledge management - ready for production use! 🚀

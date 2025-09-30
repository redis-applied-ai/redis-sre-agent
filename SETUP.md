# Redis SRE Agent Setup Guide

This guide will help you set up the Redis SRE Agent environment for development, testing, or production use.

## 🚀 Quick Start

For the fastest setup with essential features:

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Quick setup (Redis + SRE Agent + UI)
./scripts/quick-setup.sh
```

This will start:
- ✅ Redis instances (operational + demo)
- ✅ SRE Agent API and Worker
- ✅ Web UI
- ✅ Basic demo data

**Ready to use**: http://localhost:3002

## 🎯 Full Setup

For complete setup with monitoring and Redis Enterprise:

```bash
# Full setup with all features
./scripts/setup.sh
```

This includes everything from quick setup plus:
- ✅ Redis Enterprise cluster and database
- ✅ Prometheus metrics collection
- ✅ Grafana dashboards
- ✅ Node exporter for system metrics
- ✅ Enterprise demo data

## 📚 Knowledge Base Setup

To populate the knowledge base with Redis documentation:

```bash
# Setup knowledge base (run after quick or full setup)
./scripts/setup-knowledge.sh
```

This adds:
- ✅ Redis documentation
- ✅ SRE runbooks and troubleshooting guides
- ✅ Best practices and configuration examples

## 🧹 Cleanup

To stop services and optionally remove data:

```bash
# Stop services only
./scripts/cleanup.sh

# Stop services and remove all data
./scripts/cleanup.sh --remove-data

# Full cleanup including Docker images
./scripts/cleanup.sh --remove-data --remove-images
```

## 📋 Prerequisites

- **Docker**: Version 20.10 or later
- **Docker Compose**: Version 2.0 or later
- **System Resources**:
  - 4GB RAM minimum (8GB recommended)
  - 2GB free disk space

## 🔧 Manual Setup

If you prefer manual setup or need to customize:

### 1. Start Core Services

```bash
docker-compose up -d redis redis-demo prometheus grafana
```

### 2. Start SRE Agent

```bash
docker-compose up -d sre-agent sre-worker sre-ui
```

### 3. Configure Instances

```bash
# Add demo instance
curl -X POST "http://localhost:8000/api/v1/instances" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Demo Redis",
    "connection_url": "redis://redis-demo:6379",
    "environment": "development",
    "usage": "App data",
    "description": "Demo Redis instance for testing"
  }'
```

### 4. Load Demo Data

```bash
# Load sample data
docker-compose exec redis-demo bash -c '
  for i in {1..100}; do
    redis-cli SET "user:$i" "{\"id\":$i,\"name\":\"User$i\"}"
  done
'
```

## 🌐 Service URLs

After setup, these services will be available:

| Service | URL | Credentials |
|---------|-----|-------------|
| **SRE Agent UI** | http://localhost:3002 | None |
| **SRE Agent API** | http://localhost:8000 | None |
| **Prometheus** | http://localhost:9090 | None |
| **Grafana** | http://localhost:3001 | admin/admin |
| **Redis Enterprise** | https://localhost:8443 | admin@redis.com/admin |

## 🔌 Redis Instances

| Instance | Host | Port | Purpose |
|----------|------|------|---------|
| **Agent Redis** | localhost | 7843 | SRE Agent operational data |
| **Demo Redis** | localhost | 7844 | Demo/testing scenarios |
| **Enterprise Redis** | localhost | 12000 | Redis Enterprise features |

## 🛠️ Development

### Building from Source

```bash
# Build all services
docker-compose build

# Build specific service
docker-compose build sre-agent
```

### Running Tests

```bash
# Run unit tests
docker-compose exec sre-agent uv run pytest tests/unit/

# Run integration tests
docker-compose exec sre-agent uv run pytest tests/integration/
```

### Logs and Debugging

```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f sre-agent
docker-compose logs -f sre-worker

# Check service health
curl http://localhost:8000/health
```

## 🔍 Troubleshooting

### Common Issues

**Services won't start:**
```bash
# Check Docker resources
docker system df
docker system prune  # If needed

# Check port conflicts
netstat -tulpn | grep -E ':(3002|8000|7843|7844)'
```

**Redis Enterprise setup fails:**
```bash
# Check container status
docker logs redis-enterprise-node1

# Manual cluster creation
docker exec redis-enterprise-node1 rladmin cluster create \
  name cluster.local username admin@redis.com password admin
```

**Worker not processing tasks:**
```bash
# Check worker logs
docker-compose logs sre-worker

# Restart worker
docker-compose restart sre-worker
```

**Knowledge base not working:**
```bash
# Repopulate knowledge base
./scripts/setup-knowledge.sh

# Check search index
curl "http://localhost:8000/knowledge/search?q=redis&limit=1"
```

### Health Checks

```bash
# Check all services
curl http://localhost:8000/health

# Check specific components
curl http://localhost:8000/health | jq '.redis_connection'
curl http://localhost:8000/health | jq '.vector_search'
```

## 📖 Next Steps

1. **Open the UI**: http://localhost:3002
2. **Select a Redis instance** from the dropdown
3. **Ask questions** about Redis performance, troubleshooting, or configuration
4. **Explore the knowledge base** with search queries
5. **Monitor metrics** in Grafana dashboards

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and contribution instructions.

## 📄 License

See [LICENSE](LICENSE) for license information.

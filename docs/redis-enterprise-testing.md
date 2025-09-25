# Redis Enterprise Testing Guide

This guide explains how to set up and test Redis Enterprise Software locally using Docker to validate enterprise runbooks and SRE agent functionality.

## Overview

The Redis Enterprise setup provides:
- **Redis Enterprise Software cluster** running in Docker
- **Cluster Manager UI** for administration
- **REST API** for programmatic access
- **Test databases** for runbook validation
- **rladmin CLI** access for enterprise operations

## Quick Setup

### 1. Start Redis Enterprise

```bash
# Start the container
docker-compose up -d redis-enterprise

# Wait for services to start (about 60 seconds)
sleep 60
```

### 2. Manual Cluster Setup via Web UI

1. **Open the Cluster Manager UI**: https://localhost:8443
2. **Accept the self-signed certificate** in your browser
3. **Create a new cluster**:
   - Cluster FQDN: `cluster.local`
   - Admin Email: `admin@redis.local`
   - Admin Password: `RedisEnterprise123!`
   - License: Leave empty for trial
4. **Wait for cluster initialization** (2-3 minutes)

### 3. Create Test Database

After cluster setup, create a test database:

1. **Go to "Databases" tab** in the web UI
2. **Click "Create Database"**
3. **Configure database**:
   - Database name: `test-db`
   - Port: `12000`
   - Memory limit: `100 MB`
   - Replication: Disabled
   - Persistence: Disabled
4. **Click "Create"**

### 4. Test Database Connection

```bash
# Test connection
docker exec redis-enterprise-node1 redis-cli -p 12000 ping

# Check cluster status
docker exec redis-enterprise-node1 rladmin cluster status

# Check database status
docker exec redis-enterprise-node1 rladmin status databases
```

## Enterprise Runbook Testing

### Available Test Scenarios

#### 1. Database Sync Issues
```bash
# Check database status
docker exec redis-enterprise-node1 rladmin status databases

# Simulate sync issues (for testing)
docker exec redis-enterprise-node1 rladmin restart db test-db
```

#### 2. High Latency Investigation
```bash
# Check cluster resources
docker exec redis-enterprise-node1 rladmin info cluster

# Check shard distribution
docker exec redis-enterprise-node1 rladmin status shards

# Monitor database performance
docker exec redis-enterprise-node1 rladmin info db test-db
```

#### 3. Connection Issues
```bash
# Check database endpoints
docker exec redis-enterprise-node1 rladmin info db test-db | grep endpoint

# Test connectivity
docker exec redis-enterprise-node1 redis-cli -h localhost -p 12000 ping

# Check connection limits
docker exec redis-enterprise-node1 rladmin info db test-db | grep connections
```

#### 4. Node Maintenance Mode
```bash
# Check current node status
docker exec redis-enterprise-node1 rladmin status nodes

# Put node in maintenance mode (for testing)
docker exec redis-enterprise-node1 rladmin node 1 maintenance_mode on

# Exit maintenance mode
docker exec redis-enterprise-node1 rladmin node 1 maintenance_mode off
```

### SRE Agent Integration

#### Test Enterprise Queries
```bash
# Search for enterprise runbooks
redis-sre-agent search "rladmin cluster status"

# Query database sync issues
redis-sre-agent search "database sync problems"

# Find maintenance mode procedures
redis-sre-agent search "node maintenance mode"
```

#### Agent with Enterprise Context
```bash
# Start agent with enterprise context
redis-sre-agent query "My Redis Enterprise database is showing high latency" \
  --redis-url redis://localhost:12000
```

## Advanced Testing Scenarios

### 1. Multi-Database Setup

Create additional databases for testing:

```bash
# Create second database
curl -k -X POST \
  -H "Content-Type: application/json" \
  -u "admin@redis.local:RedisEnterprise123!" \
  -d '{
    "name": "test-db-2",
    "type": "redis",
    "memory_size": 100000000,
    "port": 12001,
    "replication": false
  }' \
  https://localhost:9443/v1/bdbs
```

### 2. Simulate Resource Pressure

```bash
# Check current memory usage
docker exec redis-enterprise-node1 rladmin info cluster | grep memory

# Load test data to simulate memory pressure
docker exec redis-enterprise-node1 redis-cli -p 12000 eval "
  for i=1,10000 do
    redis.call('set', 'test:key:' .. i, string.rep('x', 1000))
  end
  return 'OK'
" 0
```

### 3. Test Cluster Operations

```bash
# Check cluster configuration
docker exec redis-enterprise-node1 rladmin info cluster

# View cluster events
docker exec redis-enterprise-node1 rladmin status | grep -A10 "Events"

# Check cluster health
docker exec redis-enterprise-node1 rladmin status | grep -E "status|health"
```

## Monitoring and Metrics

### Prometheus Integration

The Redis Enterprise container exposes metrics that can be scraped by Prometheus:

```yaml
# Add to prometheus.yml
- job_name: 'redis-enterprise'
  static_configs:
    - targets: ['redis-enterprise:8070']
  scheme: https
  tls_config:
    insecure_skip_verify: true
```

### Key Metrics to Monitor

- **Database latency**: `bdb_avg_latency`
- **Memory usage**: `bdb_used_memory`
- **Connection count**: `bdb_conns`
- **Cluster health**: `cluster_state`

## Troubleshooting

### Common Issues

#### 1. Container Won't Start
```bash
# Check container logs
docker logs redis-enterprise-node1

# Ensure sufficient memory (4GB minimum)
docker stats redis-enterprise-node1
```

#### 2. Cluster Setup Fails
```bash
# Reset cluster
docker-compose down redis-enterprise
docker volume rm redis-sre-agent_redis_enterprise_data
./scripts/setup_redis_enterprise.sh
```

#### 3. Database Connection Issues
```bash
# Check database status
docker exec redis-enterprise-node1 rladmin status databases

# Verify port mapping
docker port redis-enterprise-node1
```

### Useful Commands

```bash
# Container management
docker exec -it redis-enterprise-node1 bash          # Shell access
docker exec redis-enterprise-node1 rladmin help      # rladmin help
docker logs -f redis-enterprise-node1                # Follow logs

# Cluster operations
docker exec redis-enterprise-node1 rladmin status    # Cluster status
docker exec redis-enterprise-node1 rladmin info cluster  # Cluster info
docker exec redis-enterprise-node1 rladmin status databases  # Database status

# Database operations
docker exec redis-enterprise-node1 redis-cli -p 12000 info  # Database info
docker exec redis-enterprise-node1 redis-cli -p 12000 monitor  # Monitor commands
```

## Cleanup

### Stop Redis Enterprise
```bash
# Stop container
docker-compose down redis-enterprise

# Remove data (optional)
docker volume rm redis-sre-agent_redis_enterprise_data
```

### Complete Cleanup
```bash
# Use cleanup script
./scripts/setup_redis_enterprise.sh cleanup
```

## Integration with SRE Agent

### Testing Enterprise Runbooks

1. **Start Redis Enterprise**: `./scripts/setup_redis_enterprise.sh`
2. **Create test scenarios**: Use rladmin commands to simulate issues
3. **Query SRE agent**: Test enterprise-specific queries
4. **Validate responses**: Ensure agent provides relevant enterprise guidance

### Example Test Flow

```bash
# 1. Setup
./scripts/setup_redis_enterprise.sh

# 2. Create a scenario (high memory usage)
docker exec redis-enterprise-node1 redis-cli -p 12000 eval "
  for i=1,50000 do
    redis.call('set', 'load:test:' .. i, string.rep('data', 100))
  end
  return 'OK'
" 0

# 3. Query the agent
redis-sre-agent query "My Redis Enterprise database is using too much memory, what should I check?"

# 4. Validate the response includes enterprise-specific guidance
```

This setup provides a comprehensive testing environment for validating Redis Enterprise runbooks and ensuring the SRE agent can effectively handle enterprise-specific scenarios.

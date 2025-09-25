# Redis Enterprise Setup for SRE Agent Testing

## Summary of Changes Made

✅ **Added Redis Enterprise to docker-compose.yml**
- Redis Enterprise Software container with proper port mappings
- Cluster Manager UI on port 8443
- REST API on port 9443
- Database ports 12000-12002 for testing

✅ **Created Redis Cloud API scraper**
- New scraper: `redis_sre_agent/pipelines/scraper/redis_cloud_api.py`
- Integrated into pipeline orchestrator
- Scrapes Redis Cloud API documentation from Swagger specs

✅ **Added 4 comprehensive enterprise runbooks**
- `redis-enterprise-database-sync-issues.md`
- `redis-enterprise-high-latency-investigation.md`
- `redis-enterprise-connection-issues.md`
- `redis-enterprise-node-maintenance-mode.md`

✅ **Created setup automation**
- Setup script: `scripts/setup_redis_enterprise.sh`
- Testing documentation: `docs/redis-enterprise-testing.md`

## Quick Start Guide

### 1. Start Redis Enterprise Container

```bash
# Start the Redis Enterprise container
docker-compose up -d redis-enterprise

# Wait for all services to initialize (about 60 seconds)
sleep 60

# Verify the web UI is accessible
curl -k -I https://localhost:8443
```

### 2. Manual Cluster Setup

Since automated cluster setup requires specific configuration, use the web UI:

1. **Open browser**: https://localhost:8443
2. **Accept certificate warning** (self-signed certificate)
3. **Create cluster**:
   - Cluster FQDN: `cluster.local`
   - Admin Email: `admin@redis.local`
   - Admin Password: `RedisEnterprise123!`
   - License: Leave empty (trial mode)
4. **Wait for initialization** (2-3 minutes)

### 3. Create Test Database

1. **Navigate to "Databases"** tab
2. **Click "Create Database"**
3. **Configure**:
   - Name: `test-db`
   - Port: `12000`
   - Memory: `100 MB`
   - Disable replication and persistence for testing
4. **Create database**

### 4. Verify Setup

```bash
# Test database connection
docker exec redis-enterprise-node1 redis-cli -p 12000 ping

# Check cluster status (after setup)
docker exec redis-enterprise-node1 rladmin cluster status

# List databases
docker exec redis-enterprise-node1 rladmin status databases
```

## Testing Enterprise Runbooks

### Test Scenarios

#### 1. Database Sync Issues
```bash
# Check database status
docker exec redis-enterprise-node1 rladmin status databases

# Query SRE agent
redis-sre-agent search "database sync problems"
```

#### 2. High Latency Investigation
```bash
# Check cluster resources
docker exec redis-enterprise-node1 rladmin info cluster

# Query SRE agent
redis-sre-agent search "Redis Enterprise high latency"
```

#### 3. Connection Issues
```bash
# Test connectivity
docker exec redis-enterprise-node1 redis-cli -p 12000 ping

# Query SRE agent
redis-sre-agent search "can't connect to Redis Enterprise"
```

#### 4. Node Maintenance Mode
```bash
# Check node status
docker exec redis-enterprise-node1 rladmin status nodes

# Query SRE agent
redis-sre-agent search "node maintenance mode"
```

### SRE Agent Integration

Test that the agent can provide enterprise-specific guidance:

```bash
# Test enterprise runbook search
redis-sre-agent search "rladmin cluster status"

# Test enterprise scenarios
redis-sre-agent query "My Redis Enterprise database is showing high latency, what should I check?"

# Test maintenance scenarios
redis-sre-agent query "A Redis Enterprise node is stuck in maintenance mode"
```

## Available Enterprise Commands

Once the cluster is set up, you can test these `rladmin` commands:

```bash
# Cluster management
docker exec redis-enterprise-node1 rladmin cluster status
docker exec redis-enterprise-node1 rladmin info cluster

# Database management
docker exec redis-enterprise-node1 rladmin status databases
docker exec redis-enterprise-node1 rladmin info db test-db

# Node management
docker exec redis-enterprise-node1 rladmin status nodes
docker exec redis-enterprise-node1 rladmin info node 1

# Shard management
docker exec redis-enterprise-node1 rladmin status shards
```

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker logs redis-enterprise-node1

# Ensure sufficient memory (4GB recommended)
docker stats redis-enterprise-node1
```

### Web UI Not Accessible
```bash
# Check if port is mapped correctly
docker port redis-enterprise-node1

# Verify container is running
docker ps | grep redis-enterprise
```

### Cluster Setup Issues
```bash
# Reset and try again
docker-compose down redis-enterprise
docker volume rm redis-sre-agent_redis_enterprise_data
docker-compose up -d redis-enterprise
```

## Cleanup

```bash
# Stop Redis Enterprise
docker-compose down redis-enterprise

# Remove data volume (optional)
docker volume rm redis-sre-agent_redis_enterprise_data
```

## Next Steps

1. **Complete manual cluster setup** via web UI
2. **Create test databases** for different scenarios
3. **Test enterprise runbooks** with real `rladmin` commands
4. **Validate SRE agent responses** for enterprise scenarios
5. **Document additional test cases** based on customer requirements

## Files Created/Modified

- `docker-compose.yml` - Added Redis Enterprise service
- `redis_sre_agent/pipelines/scraper/redis_cloud_api.py` - New scraper
- `redis_sre_agent/pipelines/orchestrator.py` - Added Redis Cloud API scraper
- `source_documents/runbooks/redis-enterprise-*.md` - 4 new runbooks
- `scripts/setup_redis_enterprise.sh` - Setup automation script
- `docs/redis-enterprise-testing.md` - Testing guide

The Redis Enterprise setup provides a comprehensive testing environment for validating enterprise runbooks and ensuring the SRE agent can handle Redis Enterprise Software scenarios effectively.

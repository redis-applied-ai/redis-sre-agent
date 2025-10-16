# Redis Enterprise High Latency Investigation

**Category**: enterprise
**Severity**: warning
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Application response times increased
- Redis command latency > 10ms consistently
- Client timeouts and connection errors
- Slow query alerts from monitoring
- User complaints about application performance

## Root Cause Analysis

### 1. Check Database Latency Metrics
```bash
# Check current latency statistics
rladmin status | grep -A 20 "DATABASES:" | grep -E "name:|latency"

# Get detailed database metrics
rladmin info db <database_name> | grep -i latency
```

### 2. Check Cluster Resource Utilization
```bash
# Check overall cluster resources
rladmin info cluster

# Check per-node resource usage
rladmin status | grep -A 20 "NODES:" | grep -E "node:|cpu|memory|free_disk"
```

### 3. Check Database Sharding and Distribution
```bash
# Check shard distribution
rladmin status | grep -A 50 "SHARDS:" | grep <database_name>

# Check if shards are balanced across nodes
rladmin placement db <database_name>
```

### 4. Check Network and Connectivity
```bash
# Check cluster network status
rladmin status | grep -i network

# Test connectivity between nodes
rladmin status | grep -A 20 "NODES:" | grep -E "status:|addr:"
```

### 5. Analyze Slow Commands
```bash
# Check for slow commands (if slowlog is enabled)
redis-cli -p <database_port> slowlog get 10

# Check command statistics
redis-cli -p <database_port> info commandstats
```

## Immediate Remediation

### Option 1: Check for Resource Bottlenecks
```bash
# Check CPU usage on nodes hosting the database
rladmin status | grep -A 20 "NODES:"

# If CPU > 80%, consider:
# 1. Moving shards to less loaded nodes
# 2. Adding more nodes to the cluster
# 3. Optimizing application queries
```

### Option 2: Check Memory Pressure
```bash
# Check memory usage
rladmin info db <database_name> | grep memory

# Check for memory fragmentation
redis-cli -p <database_port> info memory | grep fragmentation

# If memory pressure detected:
redis-cli -p <database_port> memory purge
```

### Option 3: Optimize Database Configuration
```bash
# Check current database configuration
rladmin info db <database_name>

# Consider adjusting:
# - Eviction policy if cache database
# - Persistence settings if causing I/O bottlenecks
# - Proxy policy for better load distribution
```

### Option 4: Check for Blocking Operations
```bash
# Check for long-running operations
redis-cli -p <database_port> info persistence

# Check for active AOF rewrite or RDB save
redis-cli -p <database_port> lastsave
```

## Advanced Troubleshooting

### 1. Analyze Shard Performance
```bash
# Check individual shard performance
rladmin status | grep -A 50 "SHARDS:" | grep <database_name>

# Look for shards with high CPU or memory usage
# Consider rebalancing if needed
```

### 2. Check Proxy Performance
```bash
# Check proxy statistics
rladmin status | grep -A10 "Proxy"

# Check proxy CPU usage
rladmin status | grep -A 20 "NODES:" | grep -E "proxy|cpu"
```

### 3. Network Latency Analysis
```bash
# Check inter-node latency
# Use ping or specialized network tools between cluster nodes

# Check client-to-cluster latency
# Test from application servers to Redis Enterprise nodes
```

### 4. Database Hotspots
```bash
# Check for key hotspots
redis-cli -p <database_port> --hotkeys

# Check command patterns
redis-cli -p <database_port> monitor | head -100
```

### 5. Check Flash Storage (if enabled)
```bash
# Check flash storage performance
rladmin info db <database_name> | grep -i flash

# Monitor flash I/O if Redis on Flash is enabled
```

## Performance Optimization

### 1. Shard Rebalancing
```bash
# Rebalance shards across nodes
rladmin migrate shard <shard_id> target_node <node_id>

# Or use automatic rebalancing
rladmin rebalance
```

### 2. Database Tuning
```bash
# Optimize database settings based on workload
rladmin tune db <database_name> max_connections <value>
rladmin tune db <database_name> eviction_policy <policy>
```

### 3. Proxy Optimization
```bash
# Adjust proxy settings if needed
rladmin tune proxy <proxy_id> max_connections <value>
```

## Long-term Prevention

### 1. Monitoring and Alerting
- Set up latency alerts (> 5ms warning, > 10ms critical)
- Monitor resource utilization trends
- Track slow query patterns
- Monitor shard distribution balance

### 2. Capacity Planning
```bash
# Regular capacity assessment
rladmin info cluster | grep -E "memory|cpu|nodes"

# Plan for growth based on trends
```

### 3. Performance Baselines
- Establish performance baselines for each database
- Regular performance testing
- Document normal vs. abnormal patterns

### 4. Application Optimization
- Review application Redis usage patterns
- Optimize queries and data structures
- Implement proper connection pooling
- Use pipelining where appropriate

## Emergency Escalation

### When to Escalate
- Latency > 50ms consistently
- Multiple databases affected
- Resource utilization > 90%
- Client applications timing out

### Escalation Information to Collect
```bash
# Collect performance data
rladmin status > cluster_status.txt
rladmin info cluster > cluster_info.txt
rladmin info db all > all_databases.txt
rladmin info node all > all_nodes.txt

# Collect database-specific info
rladmin info db <database_name> > db_info.txt
redis-cli -p <database_port> info > redis_info.txt
redis-cli -p <database_port> slowlog get 50 > slowlog.txt

# System metrics
top -b -n 1 > system_top.txt
iostat -x 1 5 > iostat.txt
```

## Related Runbooks
- Redis Enterprise Database Sync Issues
- Redis Enterprise Connection Issues
- Redis Enterprise Node Maintenance Mode

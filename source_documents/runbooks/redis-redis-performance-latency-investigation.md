# Redis Performance Latency Investigation

**Category**: operational_runbook  
**Severity**: warning  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Redis latency spikes from 1ms to 50ms during peak hours.
- Increased client connection errors.
- Rejected connections.
- High CPU or memory usage on Redis server.
- Network latency issues.

## Root Cause Analysis

### 1. Analyze Redis SLOWLOG
```bash
redis-cli SLOWLOG GET 128
# Look for entries with high execution times. This will help identify slow commands that are contributing to latency.
```

### 2. Check Redis INFO for Latency Stats
```bash
redis-cli INFO stats
# Examine the 'instantaneous_ops_per_sec' and 'total_commands_processed' for anomalies. High values may indicate a bottleneck.
```

### 3. Monitor CPU and Memory Usage
```bash
top -n 1 | grep redis
# Check if Redis is consuming excessive CPU or memory resources.
```

### 4. Network Latency Check
```bash
ping <redis-server-ip>
# Ensure network latency is within acceptable limits. High ping times can contribute to overall latency.
```

## Immediate Remediation

### Option 1: Restart Redis Server
```bash
sudo systemctl restart redis
# A restart can temporarily alleviate high latency by clearing transient issues. Use with caution as it will disconnect clients.
```

### Option 2: Optimize Slow Commands
1. Identify slow commands from SLOWLOG.
2. Optimize data structures or use pipelining to reduce execution time.
3. Consider using Lua scripts for atomic operations.

## Long-term Prevention

### 1. Optimize Redis Configuration
- Increase `maxmemory` to prevent swapping.
- Adjust `timeout` and `tcp-keepalive` settings to manage idle connections.
- Use `maxclients` to limit the number of simultaneous connections.

### 2. Scale Redis Deployment
- Consider sharding data across multiple Redis instances.
- Use Redis Cluster for horizontal scaling.
- Implement read replicas to distribute read load.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli INFO memory
redis-cli INFO cpu
redis-cli INFO stats
```

### Alert Thresholds
- Alert if latency exceeds 10ms for more than 5 minutes.
- Alert if CPU usage exceeds 80%.
- Alert if memory usage exceeds 75% of `maxmemory`.

## Production Checklist
- [ ] Verify Redis configuration settings are optimized for current workload.
- [ ] Ensure monitoring and alerting systems are configured with appropriate thresholds.
- [ ] Conduct regular SLOWLOG reviews to identify and optimize slow commands.
- [ ] Plan and test scaling strategies, such as sharding or clustering, to handle peak loads.
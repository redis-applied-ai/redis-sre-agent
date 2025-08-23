# Redis Performance Latency Investigation

**Category**: operational_runbook  
**Severity**: warning  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Redis latency spikes from 1ms to 50ms during peak hours.
- Increased response times observed in application logs.
- Occasional rejected connections.
- Client connection errors reported.

## Root Cause Analysis

### 1. Analyze Redis Slow Log
```bash
redis-cli SLOWLOG GET 128
# Look for entries with high execution times. Note the command types and patterns.
```

### 2. Check Latency with Latency Doctor
```bash
redis-cli LATENCY DOCTOR
# Review the report for any latency spikes and their potential causes.
```

### 3. Monitor CPU and Memory Usage
```bash
top -b -n1 | grep redis
# Check if Redis is consuming excessive CPU or memory resources.
```

### 4. Network Latency Check
```bash
ping <redis-server-ip>
# Ensure network latency is within acceptable limits.
```

## Immediate Remediation

### Option 1: Flush Slow Log
```bash
redis-cli SLOWLOG RESET
# Clears the slow log to prevent it from growing too large. Use with caution as it will remove all historical data.
```

### Option 2: Optimize Slow Commands
1. Identify slow commands from the Slow Log.
2. Optimize data structures or query patterns causing delays.
3. Consider using pipelining to reduce round-trip time.

## Long-term Prevention

### 1. Optimize Redis Configuration
- Increase `maxmemory` if memory is a bottleneck.
- Adjust `timeout` settings to prevent long-running connections.
- Use `maxclients` to limit the number of simultaneous connections.

### 2. Scale Redis Deployment
- Consider sharding data across multiple Redis instances.
- Use Redis Cluster for horizontal scaling.
- Deploy Redis on modern EC2 instances with optimized network and I/O performance.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli INFO stats | grep -E 'instantaneous_ops_per_sec|total_commands_processed|rejected_connections|connected_clients'
```

### Alert Thresholds
- Latency > 10ms for more than 5 minutes.
- Rejected connections > 0.
- Connected clients approaching `maxclients` limit.

## Production Checklist
- [ ] Verify Redis Slow Log is enabled and configured correctly.
- [ ] Ensure Redis is running on a modern, optimized instance.
- [ ] Monitor key metrics and set up alerts for threshold breaches.
- [ ] Regularly review and optimize slow commands.
- [ ] Implement a scaling strategy for peak load periods.
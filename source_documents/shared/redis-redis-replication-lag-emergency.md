# Redis Replication Lag Emergency

**Category**: shared  
**Severity**: warning  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Master-replica lag exceeds 45 seconds.
- Read queries return stale data.
- Application inconsistencies and user complaints.
- Latency spikes and rejected connections.
- Client connection errors in application logs.

## Root Cause Analysis

### 1. Check Replication Lag
```bash
redis-cli INFO replication
# Look for 'lag' under the 'replication' section. A value greater than 45 seconds indicates a problem.
```

### 2. Analyze Slow Commands
```bash
redis-cli SLOWLOG GET 10
# Identify slow commands that might be blocking the server. Look for high execution times.
```

## Immediate Remediation

### Option 1: Reduce Write Load
```bash
# Temporarily reduce the write load to the master to allow replicas to catch up.
# This can be done by throttling the application or redirecting some writes to a queue.
```

### Option 2: Optimize Network and Infrastructure
1. Ensure that the network between master and replicas is stable and has low latency.
2. Upgrade to modern HVM-based EC2 instances if using AWS.
3. Check for any network throttling or bandwidth limitations.

## Long-term Prevention

### 1. Optimize Redis Configuration
- Increase `repl-backlog-size` to handle more data during high write loads.
- Adjust `repl-timeout` to ensure replicas have enough time to catch up.

### 2. Implement Read Consistency Management
- Use `WAIT` command to ensure write operations are acknowledged by replicas before proceeding.
- Consider using Redis Sentinel or Redis Cluster for automatic failover and load balancing.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli INFO replication | grep 'lag'
# Monitor replication lag continuously.
```

### Alert Thresholds
- Set alerts for replication lag exceeding 30 seconds.
- Alert on slow log entries with execution times over 100ms.

## Production Checklist
- [ ] Verify network stability and bandwidth between master and replicas.
- [ ] Ensure Redis configuration is optimized for high write loads.
- [ ] Implement monitoring and alerting for replication lag and slow commands.
- [ ] Regularly review and adjust infrastructure resources to meet demand.
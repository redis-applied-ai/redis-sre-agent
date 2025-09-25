# Redis Distributed Rate Limiting Deadlock

**Category**: shared  
**Severity**: critical  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Applications receiving "ERR max number of clients reached" errors
- Increased latency and timeouts in Redis operations
- Services unable to acquire locks, leading to degraded throughput
- High number of rejected connections and client connection errors in logs

## Root Cause Analysis

### 1. Lock Contention Analysis
```bash
redis-cli --scan --pattern "lock:*"
# Look for a high number of lock keys indicating contention
```

### 2. Deadlock Detection
```bash
redis-cli monitor | grep "SET lock:"
# Monitor for repeated attempts to set locks without success
```

## Immediate Remediation

### Option 1: Release Stale Locks
```bash
redis-cli --scan --pattern "lock:*" | xargs redis-cli del
# WARNING: This will forcefully release all locks. Ensure this is safe for your application logic.
```

### Option 2: Increase Client Limit
1. Edit the Redis configuration file (redis.conf):
   ```bash
   maxclients 10000
   ```
2. Restart the Redis server:
   ```bash
   sudo systemctl restart redis
   ```
3. Monitor the client connections to ensure stability.

## Long-term Prevention

### 1. Optimize Lock Acquisition Strategy
- Implement a backoff strategy for retrying lock acquisition.
- Use a shorter TTL for locks to prevent long-held locks.

### 2. Implement Robust Timeout and Retry Mechanisms
- Use Redis transactions (MULTI/EXEC) to ensure atomic operations.
- Set a reasonable timeout for lock acquisition attempts.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli info clients | grep connected_clients
redis-cli info stats | grep rejected_connections
redis-cli info stats | grep total_commands_processed
```

### Alert Thresholds
- Connected clients > 80% of maxclients
- Rejected connections > 0
- Average command latency > 10ms

## Production Checklist
- [ ] Ensure Redis configuration is optimized for high concurrency.
- [ ] Implement monitoring for lock contention and client limits.
- [ ] Review and test lock acquisition and release logic.
- [ ] Validate that all services handle lock acquisition failures gracefully.

By following this runbook, SREs can effectively diagnose and remediate Redis distributed rate limiting deadlocks, ensuring system stability and performance.
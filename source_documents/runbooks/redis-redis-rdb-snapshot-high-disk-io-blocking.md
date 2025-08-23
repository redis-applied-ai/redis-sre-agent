# Redis RDB Snapshot High Disk IO Blocking

**Category**: operational_runbook  
**Severity**: warning  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Prolonged periods of 100% disk I/O usage during BGSAVE operations.
- Application timeouts and increased latency.
- Redis operations blocked or delayed.
- High latency observed in Redis Slow Log.

## Root Cause Analysis

### 1. Check Disk I/O Utilization
```bash
iostat -x 1 3
# Look for high %util (close to 100%) indicating disk saturation.
```

### 2. Analyze Redis Slow Log
```bash
redis-cli SLOWLOG GET 10
# Check for slow commands that coincide with BGSAVE operations.
```

## Immediate Remediation

### Option 1: Adjust BGSAVE Frequency
```bash
redis-cli CONFIG SET save "900 1 300 10 60 10000"
# Adjust the frequency of BGSAVE to reduce I/O load. Ensure this aligns with your data durability requirements.
```

### Option 2: Use AOF Instead of RDB
1. Enable AOF persistence:
   ```bash
   redis-cli CONFIG SET appendonly yes
   ```
2. Adjust AOF rewrite settings to balance I/O:
   ```bash
   redis-cli CONFIG SET auto-aof-rewrite-percentage 100
   redis-cli CONFIG SET auto-aof-rewrite-min-size 64mb
   ```

## Long-term Prevention

### 1. Optimize Disk I/O Performance
- Upgrade to SSDs or faster storage solutions.
- Use dedicated disks for Redis data to avoid contention.

### 2. Schedule Snapshots During Low Traffic
- Analyze traffic patterns and schedule BGSAVE during off-peak hours.
- Use cron jobs or Redis event notifications to trigger BGSAVE at optimal times.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli INFO persistence | grep rdb_bgsave_in_progress
# Monitor if BGSAVE is in progress.

redis-cli INFO stats | grep latest_fork_usec
# Track the time taken for the last fork operation.
```

### Alert Thresholds
- Alert if `rdb_bgsave_in_progress` is true for more than 30 seconds.
- Alert if `latest_fork_usec` exceeds 1000000 microseconds (1 second).

## Production Checklist
- [ ] Verify disk I/O capacity and upgrade if necessary.
- [ ] Configure Redis persistence settings to balance performance and durability.
- [ ] Implement monitoring for BGSAVE operations and disk I/O.
- [ ] Schedule regular reviews of Redis performance and adjust configurations as needed.

Focus on practical, production-ready guidance with specific commands, thresholds, and procedures.
# Redis Replica Promotion Disk Space Failure

**Category**: shared
**Severity**: critical
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Automatic failover fails; no master node available.
- Replication lag increases significantly.
- Error logs indicating insufficient disk space for replication backlog.
- Replica unable to promote to master.

## Root Cause Analysis

### 1. Check Disk Space
```bash
df -h /path/to/redis/data
# Look for high disk usage on the partition where Redis data is stored.
```

### 2. Check Redis Logs for Errors
```bash
tail -n 100 /var/log/redis/redis-server.log
# Look for errors related to disk space or replication backlog.
```

## Immediate Remediation

### Option 1: Free Up Disk Space
```bash
# Identify large files and remove unnecessary ones
du -sh /path/to/redis/data/* | sort -h
# Remove or archive old RDB or AOF files if safe to do so.
rm /path/to/redis/data/old-file.rdb
# Warning: Ensure that files are not needed before deletion.
```

### Option 2: Manual Replica Promotion
1. **Identify the Best Replica**:
   - Check replication lag and data consistency.
   - Use `INFO REPLICATION` to find the replica with the least lag.

2. **Promote Replica to Master**:
   ```bash
   redis-cli -h <replica-host> -p <replica-port> SLAVEOF NO ONE
   # This command promotes the replica to master.
   ```

3. **Reconfigure Other Replicas**:
   ```bash
   redis-cli -h <other-replica-host> -p <other-replica-port> SLAVEOF <new-master-ip> <new-master-port>
   # Point other replicas to the new master.
   ```

## Long-term Prevention

### 1. Disk Space Monitoring
- Implement disk space monitoring using tools like Prometheus or Nagios.
- Set alerts for disk usage exceeding 80%.

### 2. Backlog Sizing Calculations
- Calculate the required backlog size based on peak write traffic.
- Adjust `repl-backlog-size` in `redis.conf` accordingly.

## Monitoring & Alerting

### Key Metrics to Track
```bash
# Monitor disk usage
df -h /path/to/redis/data

# Monitor replication lag
redis-cli INFO REPLICATION | grep lag
```

### Alert Thresholds
- Disk usage > 80%
- Replication lag > 1000 ms

## Production Checklist
- [ ] Verify disk space availability on all Redis nodes.
- [ ] Ensure all replicas are configured with sufficient backlog size.
- [ ] Set up monitoring and alerting for disk space and replication lag.
- [ ] Document manual promotion procedures and test in a staging environment.

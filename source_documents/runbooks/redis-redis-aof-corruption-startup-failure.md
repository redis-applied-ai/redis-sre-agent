# Redis AOF Corruption Startup Failure

**Category**: operational_runbook  
**Severity**: critical  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Redis fails to start after a server crash.
- Error message: 'Bad file format reading the append only file'.
- AOF file appears corrupted, preventing Redis recovery.

## Root Cause Analysis

### 1. Check Redis Logs for Errors
```bash
tail -n 100 /var/log/redis/redis-server.log
# Look for 'Bad file format reading the append only file' or similar errors indicating AOF corruption.
```

### 2. Verify AOF File Integrity
```bash
redis-check-aof --fix /path/to/appendonly.aof
# This command attempts to repair the AOF file. Look for messages indicating successful repair or further corruption.
```

## Immediate Remediation

### Option 1: Repair AOF File
```bash
redis-check-aof --fix /path/to/appendonly.aof
# Use this command to attempt automatic repair of the AOF file. Be aware that some data may be lost during the repair process.
```

### Option 2: Restore from Backup
1. Stop the Redis server if it's running:
   ```bash
   sudo systemctl stop redis
   ```
2. Move the corrupted AOF file to a backup location:
   ```bash
   mv /path/to/appendonly.aof /path/to/backup/appendonly.aof.bak
   ```
3. Restore the AOF file from the latest backup:
   ```bash
   cp /path/to/backup/appendonly.aof /path/to/appendonly.aof
   ```
4. Start the Redis server:
   ```bash
   sudo systemctl start redis
   ```

## Long-term Prevention

### 1. Regular Backups
- Implement a regular backup strategy using both AOF and RDB snapshots.
- Schedule backups during low-traffic periods to minimize performance impact.

### 2. Configure AOF fsync Policy
- Set `appendfsync` to `everysec` to balance performance and data safety:
  ```bash
  CONFIG SET appendfsync everysec
  ```
- Consider using `no-appendfsync-on-rewrite yes` to prevent fsync during AOF rewrites.

## Monitoring & Alerting

### Key Metrics to Track
```bash
# Monitor AOF rewrite operations
INFO persistence | grep aof_rewrite_in_progress
# Monitor disk I/O performance
iostat -x 1 10
```

### Alert Thresholds
- Alert if `aof_rewrite_in_progress` is consistently high.
- Alert if disk I/O wait time exceeds 10% for more than 5 minutes.

## Production Checklist
- [ ] Verify Redis logs for any signs of AOF corruption.
- [ ] Ensure regular backups are configured and tested.
- [ ] Confirm `appendfsync` configuration aligns with performance and safety requirements.
- [ ] Monitor key metrics and set up alerts for abnormal conditions.

This runbook provides a structured approach to diagnosing and resolving Redis AOF corruption issues, ensuring minimal data loss and system downtime.
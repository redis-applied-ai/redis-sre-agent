# Redis AOF Corruption Startup Failure

**Category**: shared  
**Severity**: critical  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Redis fails to start after a server crash.
- Error message: "Bad file format reading the append only file".
- Redis logs indicate AOF file corruption.

## Root Cause Analysis

### 1. Check Redis Logs for Errors
```bash
tail -n 100 /var/log/redis/redis-server.log
# Look for error messages related to AOF corruption, such as "Bad file format reading the append only file".
```

### 2. Verify AOF File Integrity
```bash
redis-check-aof /path/to/appendonly.aof
# This command checks the integrity of the AOF file. Look for any corruption messages.
```

## Immediate Remediation

### Option 1: Repair AOF File
```bash
redis-check-aof --fix /path/to/appendonly.aof
# Use this command to attempt automatic repair of the AOF file. Be aware that this may result in some data loss.
```

### Option 2: Restore from Backup
1. Identify the latest backup file (AOF or RDB).
2. Stop the Redis server if it is running:
   ```bash
   sudo systemctl stop redis
   ```
3. Replace the corrupted AOF file with the backup:
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
- Store backups in a secure, redundant location.

### 2. Disk I/O Monitoring
- Monitor disk I/O performance to detect potential issues early.
- Set alerts for high disk I/O wait times, e.g., if disk I/O wait time exceeds 10% for more than 5 minutes.

## Monitoring & Alerting

### Key Metrics to Track
```bash
# Monitor Redis server logs for errors
tail -f /var/log/redis/redis-server.log

# Monitor disk I/O performance
iostat -x 1 10
```

### Alert Thresholds
- Alert if "Bad file format reading the append only file" appears in logs.
- Alert if disk I/O wait time exceeds 10% for more than 5 minutes.

## Production Checklist
- [ ] Verify Redis logs for any signs of AOF corruption.
- [ ] Ensure regular backups are configured and tested.
- [ ] Monitor disk I/O performance and set appropriate alerts.
- [ ] Document any changes made during remediation for future reference.
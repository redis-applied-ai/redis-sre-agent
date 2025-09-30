# Redis RDB Snapshot High Disk IO Blocking

**Category**: shared
**Severity**: warning
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Prolonged periods of 100% disk I/O usage.
- Application timeouts during BGSAVE operations.
- Increased latency in Redis operations.
- Redis logs showing frequent BGSAVE operations.

## Root Cause Analysis

### 1. Check Disk I/O Utilization
```bash
iostat -x 1 3
# Look for high %util (close to 100%) indicating disk saturation.
```

### 2. Analyze Redis Logs for BGSAVE Frequency
```bash
grep "BGSAVE" /var/log/redis/redis-server.log
# Identify frequent BGSAVE operations and their duration.
```

## Immediate Remediation

### Option 1: Adjust BGSAVE Frequency
```bash
redis-cli CONFIG SET save "900 1 300 10 60 10000"
# Adjust the frequency of BGSAVE to reduce I/O load. Ensure this aligns with your data durability requirements.
```

### Option 2: Temporarily Disable BGSAVE
```bash
redis-cli CONFIG SET save ""
# Temporarily disable BGSAVE to alleviate immediate I/O pressure. Use with caution as it impacts data durability.
```

## Long-term Prevention

### 1. Optimize BGSAVE Scheduling
- Schedule BGSAVE during off-peak hours to minimize impact on application performance.
- Use cron jobs to control the timing of BGSAVE operations.

### 2. Implement Disk I/O Tuning
- Upgrade to SSDs if using HDDs to improve I/O performance.
- Increase disk I/O bandwidth by using RAID configurations.

## Monitoring & Alerting

### Key Metrics to Track
```bash
iostat -x 1
# Monitor %util and await for disk I/O performance.
```

### Alert Thresholds
- Alert if disk I/O %util exceeds 90% for more than 5 minutes.
- Alert if Redis latency exceeds 100ms during BGSAVE operations.

## Production Checklist
- [ ] Verify Redis logs for BGSAVE operation frequency and duration.
- [ ] Ensure disk I/O monitoring is active and thresholds are set.
- [ ] Review and adjust BGSAVE scheduling to align with application load.
- [ ] Confirm that disk I/O tuning parameters are optimized for current hardware.
- [ ] Test Redis performance after implementing changes to ensure stability.

# Redis maxmemory exceeded OOM killer prevention

**Category**: operational_runbook  
**Severity**: critical  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Redis process terminated unexpectedly by the Linux OOM killer.
- Applications failing with "connection refused" errors.
- System-wide memory pressure observed.
- Redis logs showing "OOM command not allowed when used memory > 'maxmemory'."

## Root Cause Analysis

### 1. Check Redis Memory Usage
```bash
redis-cli info memory
# Look for 'used_memory' and compare it with 'maxmemory'. If 'used_memory' exceeds 'maxmemory', it indicates Redis is consuming more memory than allocated.
```

### 2. Check System Memory and Swap Usage
```bash
free -m
# Check 'Mem' and 'Swap' usage. High 'used' memory with low 'free' memory and swap indicates system-wide memory pressure.
```

## Immediate Remediation

### Option 1: Increase Swap Space
```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
# Temporarily increase swap space to alleviate memory pressure. Ensure swap size is at least equal to system RAM.
```

### Option 2: Adjust Redis maxmemory Configuration
1. Edit the Redis configuration file (usually located at `/etc/redis/redis.conf`).
2. Increase the `maxmemory` setting to a value that the system can handle without causing OOM.
   ```bash
   maxmemory 2gb
   ```
3. Restart Redis to apply changes.
   ```bash
   sudo systemctl restart redis
   ```

## Long-term Prevention

### 1. Optimize Redis Memory Usage
- Enable `maxmemory-policy` to `allkeys-lru` to evict less frequently used keys.
- Regularly monitor and clean up unnecessary keys.

### 2. System Memory Management
- Ensure swap is permanently enabled by adding the swap entry to `/etc/fstab`.
- Consider upgrading system RAM if persistent memory pressure is observed.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli info memory | grep used_memory
# Monitor 'used_memory' and set alerts if it approaches 'maxmemory'.
```

### Alert Thresholds
- Alert if `used_memory` exceeds 80% of `maxmemory`.
- Alert if system free memory drops below 10% of total memory.

## Production Checklist
- [ ] Verify Redis `maxmemory` is set appropriately for the workload.
- [ ] Ensure swap is enabled and configured correctly.
- [ ] Monitor Redis memory usage and system memory pressure.
- [ ] Implement alerts for memory usage thresholds.
- [ ] Regularly review and optimize Redis data structures and eviction policies.
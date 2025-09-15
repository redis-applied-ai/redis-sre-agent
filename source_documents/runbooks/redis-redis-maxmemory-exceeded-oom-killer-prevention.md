# Redis maxmemory Exceeded OOM Killer Prevention

**Category**: operational_runbook  
**Severity**: critical  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Redis process terminated unexpectedly.
- Applications receiving "connection refused" errors.
- System logs indicate the Linux OOM killer was triggered.
- High memory usage observed during peak traffic periods.

## Root Cause Analysis

### 1. Check Redis Logs for OOM Events
```bash
grep -i "oom" /var/log/redis/redis-server.log
# Look for entries indicating Redis was terminated due to OOM conditions.
```

### 2. Verify System Memory and Swap Usage
```bash
free -m
# Check 'Mem' and 'Swap' usage. High 'used' memory with low 'free' memory and swap indicates system-wide memory pressure.
```

## Immediate Remediation

### Option 1: Restart Redis with Reduced Load
```bash
sudo systemctl restart redis
# Restart Redis to recover from OOM termination. Ensure reduced load by temporarily disabling non-critical services.
```

### Option 2: Increase System Swap Space
1. Check current swap usage:
   ```bash
   swapon --show
   ```
2. Create a swap file if necessary:
   ```bash
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```
3. Add to `/etc/fstab` for persistence:
   ```bash
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

## Long-term Prevention

### 1. Optimize Redis Memory Usage
- Set `maxmemory` to a value that leaves headroom for other system processes (typically 60-80% of total system RAM):
  ```bash
  # Example: On a 4GB system, set maxmemory to 2GB to prevent system OOM
  redis-cli config set maxmemory 2gb
  ```
- Configure `maxmemory-policy` to `allkeys-lru` to evict less frequently used keys:
  ```bash
  redis-cli config set maxmemory-policy allkeys-lru
  ```

### 2. Implement System-Level Memory Management
- Enable and configure swap space appropriately to handle memory spikes.
- Monitor and adjust the `vm.swappiness` parameter to balance between RAM and swap usage:
  ```bash
  echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
  sudo sysctl -p
  ```

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli info memory | grep used_memory
# Monitor 'used_memory' to ensure it stays within limits.
```

### Alert Thresholds
- Set alerts for when Redis memory usage exceeds 80% of `maxmemory`.
- Alert if system swap usage exceeds 50%.

## Production Checklist
- [ ] Verify Redis `maxmemory` is set appropriately for the workload.
- [ ] Ensure swap is enabled and configured correctly.
- [ ] Monitor Redis memory usage and system swap usage regularly.
- [ ] Adjust `maxmemory-policy` to `allkeys-lru` for optimal key eviction.
- [ ] Document and review memory usage patterns during peak traffic periods.
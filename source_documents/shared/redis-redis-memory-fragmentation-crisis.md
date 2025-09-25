# Redis Memory Fragmentation Crisis

**Category**: shared  
**Severity**: warning  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Memory fragmentation ratio exceeds 4.0
- Redis using 8GB RAM for 2GB of data
- System experiencing swap activity
- Noticeable performance degradation

## Root Cause Analysis

### 1. Check Memory Fragmentation Ratio
```bash
redis-cli info memory | grep 'mem_fragmentation_ratio'
# Look for a mem_fragmentation_ratio value greater than 4.0, indicating high fragmentation.
```

### 2. Analyze Memory Usage
```bash
redis-cli info memory | grep 'used_memory_human\|total_system_memory_human'
# Compare used_memory_human with total_system_memory_human to understand the extent of memory usage.
```

## Immediate Remediation

### Option 1: MEMORY PURGE
```bash
redis-cli memory purge
# This command attempts to release memory back to the operating system. Use with caution as it may temporarily impact performance.
```

### Option 2: Defragmentation Procedure
1. **Trigger Manual Defragmentation**:
   ```bash
   redis-cli memory defrag
   # This command will attempt to defragment the memory. Monitor the impact on performance and memory usage.
   ```

2. **Restart Redis Instance**:
   - If defragmentation does not resolve the issue, consider restarting the Redis instance during a maintenance window to clear fragmentation.

## Long-term Prevention

### 1. Optimize Memory Configuration
- **Adjust maxmemory-policy**:
  ```bash
  redis-cli config set maxmemory-policy allkeys-lru
  # Use an appropriate eviction policy to manage memory usage effectively.
  ```

- **Set maxmemory**:
  ```bash
  redis-cli config set maxmemory 6gb
  # Ensure maxmemory is set to a value that allows for efficient memory usage without causing excessive fragmentation.
  ```

### 2. Implement Capacity Planning
- Analyze historical memory usage trends.
- Forecast future memory needs based on application growth.
- Plan for hardware upgrades or Redis cluster scaling as needed.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli info memory | grep 'mem_fragmentation_ratio\|used_memory\|total_system_memory'
```

### Alert Thresholds
- **Fragmentation Ratio**: Alert if `mem_fragmentation_ratio` exceeds 3.5
- **Memory Usage**: Alert if `used_memory` approaches 80% of `maxmemory`

## Production Checklist
- [ ] Verify Redis `maxmemory` is set appropriately for the workload.
- [ ] Ensure swap is enabled and configured correctly.
- [ ] Monitor `mem_fragmentation_ratio` and set alerts for thresholds.
- [ ] Regularly review and adjust eviction policies based on usage patterns.
- [ ] Conduct periodic capacity planning to anticipate future needs.
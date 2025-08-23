# Redis Memory Fragmentation Crisis

**Category**: operational_runbook  
**Severity**: warning  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Memory fragmentation ratio exceeds 4.0
- Redis using significantly more RAM than the actual data size (e.g., 8GB RAM for 2GB of data)
- Increased swap activity
- Noticeable performance degradation and latency issues

## Root Cause Analysis

### 1. Check Memory Fragmentation Ratio
```bash
redis-cli info memory | grep 'mem_fragmentation_ratio'
# Look for a mem_fragmentation_ratio value significantly greater than 1.0, indicating high fragmentation.
```

### 2. Analyze Memory Usage
```bash
redis-cli info memory
# Review 'used_memory', 'used_memory_rss', and 'used_memory_peak' to understand memory allocation and usage patterns.
```

## Immediate Remediation

### Option 1: MEMORY PURGE
```bash
redis-cli memory purge
# This command attempts to release memory back to the operating system. Use with caution as it may temporarily impact performance.
```

### Option 2: Defragmentation Procedure
1. **Enable Active Defragmentation**:
   ```bash
   redis-cli config set activedefrag yes
   # This enables Redis's active defragmentation feature, which can help reduce fragmentation over time.
   ```

2. **Monitor Defragmentation Progress**:
   ```bash
   redis-cli info memory | grep 'active_defrag_running'
   # Check if active defragmentation is running and monitor its progress.
   ```

## Long-term Prevention

### 1. Optimize Memory Configuration
- **Adjust maxmemory-policy**:
  ```bash
  redis-cli config set maxmemory-policy allkeys-lru
  # Use an appropriate eviction policy to manage memory usage effectively.
  ```

- **Tune maxmemory setting**:
  ```bash
  redis-cli config set maxmemory <desired_memory_limit>
  # Set a reasonable maxmemory limit to prevent excessive memory usage.
  ```

### 2. Regular Memory Monitoring
- Implement regular checks on memory usage and fragmentation ratios to detect issues early.
- Schedule periodic reviews of memory allocation patterns and adjust configurations as needed.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli info memory | grep 'used_memory\|used_memory_rss\|mem_fragmentation_ratio'
# Regularly monitor these metrics to track memory usage and fragmentation.
```

### Alert Thresholds
- **Fragmentation Ratio**: Alert if `mem_fragmentation_ratio` > 2.0
- **Used Memory**: Alert if `used_memory` approaches 80% of `maxmemory`

## Production Checklist
- [ ] Ensure active defragmentation is enabled (`activedefrag yes`)
- [ ] Set appropriate `maxmemory` and `maxmemory-policy`
- [ ] Implement monitoring for memory metrics and set alert thresholds
- [ ] Regularly review and adjust memory configurations based on usage patterns

Focus on maintaining optimal memory usage and preventing fragmentation through proactive monitoring and configuration adjustments.
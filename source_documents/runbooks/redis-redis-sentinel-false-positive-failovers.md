# Redis Sentinel False Positive Failovers

**Category**: operational_runbook  
**Severity**: critical  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Frequent failover events logged by Redis Sentinel.
- Application experiencing connection disruptions and timeouts.
- Redis Sentinel logs indicating master down detection without actual master failure.
- Increased latency or network issues reported.

## Root Cause Analysis

### 1. Check Sentinel Logs for Failover Triggers
```bash
tail -n 100 /var/log/redis/sentinel.log
# Look for patterns indicating frequent failover events and reasons for master down detection.
```

### 2. Verify Network Latency and Stability
```bash
ping <master-ip>
# Check for high latency or packet loss that could trigger false positives.
```

### 3. Review Sentinel Configuration
```bash
cat /etc/redis/sentinel.conf | grep -E 'down-after-milliseconds|parallel-syncs'
# Ensure configuration values are appropriate for your environment.
```

## Immediate Remediation

### Option 1: Adjust `down-after-milliseconds`
```bash
# Edit the Sentinel configuration file
vi /etc/redis/sentinel.conf

# Increase the down-after-milliseconds value
# Example: from 5000 to 10000
sentinel down-after-milliseconds mymaster 10000

# Restart Sentinel to apply changes
redis-cli -p <sentinel-port> SENTINEL RESET mymaster
# This increases the time Sentinel waits before declaring a master down.
```

### Option 2: Network Stability Check
1. Ensure network stability between Sentinel and Redis nodes.
2. Use network monitoring tools to identify and resolve latency issues.
3. Consider increasing network bandwidth or reducing network load.

## Long-term Prevention

### 1. Optimize `parallel-syncs`
- Adjust `parallel-syncs` to control the number of replicas that can be synchronized in parallel during a failover.
- Example: Increase from 1 to 2 if network and system resources allow.

### 2. Implement Robust Monitoring
- Set up comprehensive monitoring for network latency, Redis performance metrics, and Sentinel logs.
- Use tools like Prometheus and Grafana for real-time monitoring and alerting.

## Monitoring & Alerting

### Key Metrics to Track
```bash
# Monitor Sentinel failover events
redis-cli -p <sentinel-port> SENTINEL SENTINELS mymaster

# Track network latency
ping <master-ip>

# Monitor Redis performance
redis-cli INFO stats
```

### Alert Thresholds
- Alert if failover events exceed 1 per hour.
- Alert if network latency exceeds 10ms consistently.
- Alert on Redis connection timeouts or errors in application logs.

## Production Checklist
- [ ] Verify Sentinel configuration for `down-after-milliseconds` and `parallel-syncs`.
- [ ] Ensure network stability and low latency between Sentinel and Redis nodes.
- [ ] Implement and test monitoring and alerting for Redis and Sentinel.
- [ ] Document any changes made to configurations and their impact on system performance.
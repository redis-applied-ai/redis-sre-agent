# Redis PubSub Message Loss During Restart

**Category**: operational_runbook  
**Severity**: warning  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Subscribers report missing messages during Redis restart.
- Logs indicate subscriber disconnections or timeouts.
- Critical messages are not received by subscribers despite persistent connections.

## Root Cause Analysis

### 1. Check Redis Logs for Restart Events
```bash
grep "Restart" /var/log/redis/redis-server.log
# Look for entries indicating a restart event and note the timestamp.
```

### 2. Verify Subscriber Connection Status
```bash
redis-cli CLIENT LIST | grep "sub"
# Check for subscriber disconnections or reconnections around the restart time.
```

## Immediate Remediation

### Option 1: Quick Restart with Minimal Downtime
```bash
redis-cli SAVE
sudo systemctl restart redis
# Perform a quick restart to minimize downtime. Ensure SAVE command is successful to persist data.
```

### Option 2: Use Redis Sentinel for High Availability
1. Ensure Redis Sentinel is configured and running.
2. Promote a replica to master before restarting the original master.
3. Restart the original master and reconfigure it as a replica.

## Long-term Prevention

### 1. Implement Message Buffering and Replay
- Use a message queue (e.g., Redis Streams, Kafka) to buffer messages.
- Implement a replay mechanism for subscribers to fetch missed messages after reconnection.

### 2. Enhance Subscriber Reconnection Handling
- Implement exponential backoff for subscriber reconnections.
- Use health checks to ensure subscribers reconnect promptly after a restart.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli INFO stats | grep "pubsub_channels"
redis-cli INFO stats | grep "pubsub_patterns"
# Monitor the number of active PubSub channels and patterns.
```

### Alert Thresholds
- Alert if the number of active subscribers drops by more than 20% during a restart.
- Alert if the time taken for subscribers to reconnect exceeds 30 seconds.

## Production Checklist
- [ ] Ensure Redis persistence is enabled (AOF or RDB).
- [ ] Configure Redis Sentinel for high availability.
- [ ] Implement a message buffering and replay mechanism.
- [ ] Set up monitoring and alerting for PubSub metrics.
- [ ] Test subscriber reconnection logic under simulated restart conditions.

Focus on practical, production-ready guidance with specific commands, thresholds, and procedures.
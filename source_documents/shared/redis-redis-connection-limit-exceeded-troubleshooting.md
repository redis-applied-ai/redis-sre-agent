# Redis Connection Limit Exceeded Troubleshooting

**Category**: shared
**Severity**: critical
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Users experiencing checkout timeouts.
- 'Connection refused' errors in application logs.
- Redis logs showing "ERR max number of clients reached".
- Increased latency and rejected connections.

## Root Cause Analysis

### 1. Check Current Connections
```bash
redis-cli CLIENT LIST | wc -l
# Look for a number close to or exceeding the configured maxclients setting.
```

### 2. Verify Maxclients Setting
```bash
redis-cli CONFIG GET maxclients
# Ensure the maxclients setting is not too low for expected peak loads.
```

## Immediate Remediation

### Option 1: Increase Maxclients Temporarily
```bash
redis-cli CONFIG SET maxclients 5000
# Temporarily increase maxclients to handle the spike. Monitor closely as this may impact server resources.
```

### Option 2: Immediate Connection Cleanup
1. Identify idle connections:
   ```bash
   redis-cli CLIENT LIST | grep "idle=[0-9]\{4,\}" | awk '{print $1}' | cut -d= -f2
   ```
2. Disconnect idle clients:
   ```bash
   for client in $(redis-cli CLIENT LIST | grep "idle=[0-9]\{4,\}" | awk '{print $1}' | cut -d= -f2); do
       redis-cli CLIENT KILL $client
   done
   # This will free up connections by disconnecting clients idle for a long time.
   ```

## Long-term Prevention

### 1. Optimize Connection Pooling
- Ensure application connection pools are configured to reuse connections efficiently.
- Set a reasonable maximum pool size to prevent overloading Redis.

### 2. Scale Redis Infrastructure
- Consider deploying additional Redis instances or using Redis Cluster to distribute load.
- Implement auto-scaling policies for Redis instances during peak demand periods.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli INFO clients | grep connected_clients
# Monitor the number of connected clients.
```

### Alert Thresholds
- Alert when connected_clients exceeds 80% of maxclients.
- Set alerts for latency spikes and rejected connections.

## Production Checklist
- [ ] Verify maxclients is set appropriately for expected peak loads.
- [ ] Ensure application connection pools are optimized.
- [ ] Implement monitoring for connected clients and latency.
- [ ] Plan for scaling Redis infrastructure during peak periods.

# Redis Connection Limit Exceeded Troubleshooting

**Category**: operational_runbook  
**Severity**: critical  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Applications receiving "ERR max number of clients reached" errors
- Users experiencing checkout timeouts
- 'Connection refused' errors in application logs
- Spike in Redis connections from 200 to 4,500

## Root Cause Analysis

### 1. Analyze Current Connections
```bash
redis-cli CLIENT LIST
# Look for a high number of connections from specific IPs or clients. Identify patterns or anomalies in the connection list.
```

### 2. Check Current Max Clients Setting
```bash
redis-cli CONFIG GET maxclients
# Verify if the current maxclients setting is lower than the number of incoming connections.
```

## Immediate Remediation

### Option 1: Increase Max Clients Temporarily
```bash
redis-cli CONFIG SET maxclients 5000
# Temporarily increase the maxclients setting to accommodate the spike. Monitor closely as this may increase memory usage.
```

### Option 2: Immediate Connection Cleanup
1. Identify idle connections:
   ```bash
   redis-cli CLIENT LIST | grep -v 'idle=0' | awk '{print $1}' | cut -d= -f2
   ```
2. Kill idle connections:
   ```bash
   for client_id in $(redis-cli CLIENT LIST | grep -v 'idle=0' | awk '{print $1}' | cut -d= -f2); do
       redis-cli CLIENT KILL $client_id
   done
   ```
   - **Warning**: This will disconnect idle clients, which may affect users if not done carefully.

## Long-term Prevention

### 1. Optimize Connection Pooling
- Ensure application connection pools are configured to reuse connections efficiently.
- Set a reasonable maximum pool size to prevent excessive connections.

### 2. Implement Client Timeout Configuration
```bash
redis-cli CONFIG SET timeout 300
# Set a timeout to automatically close idle connections after 300 seconds.
```

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli INFO clients | grep connected_clients
# Monitor the number of connected clients.
```

### Alert Thresholds
- Alert when connected_clients > 80% of maxclients
- Alert on "ERR max number of clients reached" errors in logs

## Production Checklist
- [ ] Verify maxclients setting is appropriate for expected traffic
- [ ] Ensure connection pooling is optimized in application configurations
- [ ] Set up alerts for high connection counts and errors
- [ ] Review and adjust client timeout settings as needed

Focus on practical, production-ready guidance with specific commands, thresholds, and procedures.
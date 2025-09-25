# Redis Lua Script Timeout Blocking Server

**Category**: shared  
**Severity**: critical  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Redis server appears frozen and unresponsive.
- Clients experience connection timeouts.
- Accumulating client requests in the Redis queue.
- Slow command responses or no response at all.

## Root Cause Analysis

### 1. Check for Long-Running Lua Scripts
```bash
redis-cli --eval myscript.lua
# If the script execution exceeds 5 seconds, it will block the server.
```

### 2. Identify Blocked Clients
```bash
redis-cli CLIENT LIST
# Look for clients with high "age" and "idle" times, indicating they are waiting for a response.
```

## Immediate Remediation

### Option 1: Kill the Running Script
```bash
redis-cli SCRIPT KILL
# This command will terminate the currently running Lua script. Use with caution as it may leave the database in an inconsistent state.
```

### Option 2: Restart Redis Server
1. Gracefully stop the Redis server:
   ```bash
   redis-cli SHUTDOWN NOSAVE
   # This will stop the server without saving the current state, useful if the state is inconsistent.
   ```
2. Start the Redis server:
   ```bash
   redis-server /path/to/redis.conf
   # Ensure the server is started with the correct configuration file.
   ```

## Long-term Prevention

### 1. Optimize Lua Scripts
- Break down complex scripts into smaller, manageable parts.
- Use Redis commands directly where possible instead of Lua logic.
- Avoid loops and recursive calls within Lua scripts.

### 2. Adjust Script Timeout Configuration
- Increase the script timeout if necessary by modifying the Redis configuration:
  ```bash
  CONFIG SET lua-time-limit 10000
  # This sets the Lua script execution timeout to 10 seconds.
  ```

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli INFO stats
# Monitor "total_commands_processed" and "instantaneous_ops_per_sec" for anomalies.
```

### Alert Thresholds
- Alert if "instantaneous_ops_per_sec" drops significantly.
- Alert if "blocked_clients" exceeds a threshold (e.g., > 10).

## Production Checklist
- [ ] Ensure all Lua scripts are optimized and tested for performance.
- [ ] Configure appropriate script timeout settings in Redis.
- [ ] Implement monitoring for key Redis metrics and set up alerts.
- [ ] Document all Lua scripts and their expected execution times.
- [ ] Regularly review and update Redis configuration settings.
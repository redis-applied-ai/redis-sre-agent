# Redis Connection Timeouts and Network Issues

**Category**: connection_troubleshooting  
**Severity**: warning  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Applications experiencing connection timeouts
- Intermittent "Connection refused" errors
- Slow Redis command response times
- Network-related Redis errors

## Diagnostic Commands

### 1. Check Redis Connectivity
```bash
redis-cli ping
# Expected: PONG
# If fails: Redis down or network issues
```

### 2. Test Network Latency
```bash
redis-cli --latency -h <redis-host> -p <redis-port>
# Monitor for latency spikes >10ms
```

### 3. Check TCP Connection State
```bash
netstat -an | grep :6379
# Look for TIME_WAIT, CLOSE_WAIT states
```

### 4. Redis Server Status
```bash
redis-cli INFO server
# Check: uptime_in_seconds, process_id
```

## Common Causes & Solutions

### 1. Network Congestion
**Symptoms**: High latency, packet loss
**Solutions**:
- Check network utilization between client/server
- Verify Redis is on dedicated network segment
- Use Redis Cluster for geographic distribution

### 2. TCP Keep-Alive Issues  
**Symptoms**: Connections dropping after idle period
**Solutions**:
```bash
# Client-side TCP keep-alive
redis-cli CONFIG SET tcp-keepalive 60
```

### 3. Firewall/Security Group Rules
**Symptoms**: Connection refused, timeouts
**Solutions**:
- Verify port 6379 (or custom port) is open
- Check iptables/firewall rules
- Test with telnet: `telnet <redis-host> 6379`

### 4. Redis Server Overload
**Symptoms**: Slow responses, command queuing
**Solutions**:
```bash
redis-cli INFO commandstats
# Look for slow commands: calls, usec, usec_per_call
redis-cli SLOWLOG GET 10
# Identify performance bottlenecks
```

## Application-Side Fixes

### 1. Connection Pool Configuration
```python
# Python redis-py example
import redis
pool = redis.ConnectionPool(
    host='redis-host',
    port=6379,
    db=0,
    max_connections=20,          # Limit pool size
    socket_connect_timeout=5,    # Connection timeout
    socket_timeout=5,            # Command timeout
    retry_on_timeout=True,       # Retry failed commands
    health_check_interval=30     # Periodic health checks
)
```

### 2. Timeout Handling
```python
try:
    result = redis_client.get(key)
except redis.TimeoutError:
    # Implement retry logic with backoff
    # Log timeout for monitoring
    # Consider degraded service mode
```

### 3. Circuit Breaker Pattern
- Implement circuit breakers to prevent cascade failures
- Add health checks before Redis operations
- Use fallback mechanisms during outages

## Monitoring & Alerting

### 1. Key Metrics to Track
```bash
redis-cli INFO clients | grep connected_clients
redis-cli INFO stats | grep rejected_connections
redis-cli --latency-history -i 1
```

### 2. Alert Thresholds
- Connection count >80% of maxclients
- Average latency >10ms
- Rejected connections >0
- Client connection errors in application logs

## Emergency Response

### 1. Immediate Actions
1. Check Redis process status: `ps aux | grep redis`
2. Verify Redis responds: `redis-cli ping`  
3. Check system resources: CPU, memory, network
4. Review recent configuration changes

### 2. Temporary Mitigations
- Restart Redis server (if safe)
- Increase connection limits temporarily
- Route traffic to backup Redis instance
- Enable application circuit breakers
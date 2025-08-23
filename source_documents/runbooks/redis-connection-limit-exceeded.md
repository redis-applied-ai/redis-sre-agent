# Redis Connection Limit Exceeded (ERR max number of clients reached)

**Category**: connection_troubleshooting  
**Severity**: critical  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Applications receiving "ERR max number of clients reached" errors
- New connections failing while existing connections work
- High connection count in Redis INFO stats
- Application connection pool timeouts

## Root Cause Analysis

### 1. Check Current Connection Count
```bash
redis-cli INFO clients
# Look for: connected_clients, blocked_clients, tracking_clients
```

### 2. Identify Connection Sources  
```bash
redis-cli CLIENT LIST
# Analyze: addr (source), age (connection duration), idle (inactive time)
```

### 3. Check maxclients Configuration
```bash
redis-cli CONFIG GET maxclients
# Default is usually 10000, but may be lower
```

## Immediate Remediation

### Option 1: Increase maxclients (Temporary)
```bash
redis-cli CONFIG SET maxclients 20000
# Requires restart for permanent: maxclients 20000 in redis.conf
```

### Option 2: Kill Idle Connections
```bash
redis-cli CLIENT LIST | grep idle:3600
# Kill connections idle >1 hour
redis-cli CLIENT KILL TYPE normal SKIPME yes ADDR <client-address>
```

### Option 3: Application-Side Connection Pooling
- Reduce application connection pool sizes
- Implement connection sharing/multiplexing
- Add connection lifecycle management

## Long-term Prevention

### 1. Connection Pool Optimization
- Set reasonable pool sizes per application instance
- Implement connection reuse patterns
- Monitor pool utilization metrics

### 2. Connection Monitoring
```bash
# Set up alerts for high connection counts
redis-cli INFO clients | grep connected_clients
# Alert when >80% of maxclients
```

### 3. Client Timeout Configuration
```bash
redis-cli CONFIG SET timeout 300
# Close idle connections after 5 minutes
```

### 4. Application Best Practices
- Use connection pooling libraries (Jedis, redis-py with connection pool)
- Implement proper connection cleanup in exception handlers  
- Avoid creating connections in tight loops
- Use Redis Sentinel/Cluster for connection distribution

## Production Checklist
- [ ] Current connection count vs maxclients limit
- [ ] Identify top connection consumers via CLIENT LIST
- [ ] Check for connection leaks in applications
- [ ] Review connection pool configurations
- [ ] Set up connection monitoring alerts
- [ ] Test connection cleanup procedures
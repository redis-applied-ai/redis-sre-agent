# Redis Connection Pool Exhaustion and Leak Detection

**Category**: shared  
**Severity**: warning  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Applications hanging on Redis operations
- "Pool exhausted" or "Unable to get connection" errors
- High number of connections but low Redis throughput
- Memory usage growing in application connection pools

## Detection & Analysis

### 1. Application-Side Pool Status
```python
# Check pool statistics (redis-py example)
pool = redis_client.connection_pool
print(f"Created connections: {pool._created_connections}")
print(f"Available connections: {len(pool._available_connections)}")
print(f"In-use connections: {len(pool._in_use_connections)}")
```

### 2. Redis Server Connection Analysis
```bash
redis-cli CLIENT LIST
# Analyze connection patterns:
# - age: How long connections have been open
# - idle: Time since last command
# - db: Which database connections are using
```

### 3. Operating System Level
```bash
# Check file descriptor usage
lsof -p <app-process-id> | grep redis
# Count Redis connections per process
netstat -an | grep :6379 | wc -l
```

## Common Pool Issues

### 1. Connection Leaks
**Cause**: Connections not properly returned to pool
**Detection**:
```python
# Monitor pool size over time
import time
while True:
    pool_size = len(pool._in_use_connections)
    print(f"In-use connections: {pool_size}")
    time.sleep(30)
```

**Solutions**:
- Always use connection context managers
- Implement proper exception handling
- Add connection lifecycle logging

### 2. Pool Size Misconfiguration  
**Cause**: Pool too small for application concurrency
**Solutions**:
```python
# Calculate appropriate pool size
concurrent_threads = 100
pool_size = min(concurrent_threads * 1.2, 50)  # 20% buffer, cap at 50
```

### 3. Blocking Operations
**Cause**: Long-running Redis commands blocking pool
**Detection**:
```bash
redis-cli CLIENT LIST | grep "cmd=blpop\|cmd=brpop\|cmd=bzpopmin"
```

**Solutions**:
- Use separate pools for blocking vs non-blocking operations
- Set appropriate timeouts for blocking commands
- Consider Redis Streams for queue-like operations

## Prevention Strategies

### 1. Connection Pool Best Practices
```python
# Robust pool configuration
pool = redis.ConnectionPool(
    host='redis-host',
    port=6379,
    max_connections=20,           # Size based on concurrency needs
    socket_connect_timeout=2,     # Fast failure for connection issues
    socket_timeout=10,            # Command timeout
    retry_on_timeout=True,        # Retry transient failures
    health_check_interval=30,     # Periodic connection validation
    connection_class=redis.Connection  # Use appropriate connection type
)
```

### 2. Application Code Patterns
```python
# Always use context managers or try/finally
def safe_redis_operation():
    connection = None
    try:
        connection = pool.get_connection('GET')
        # Perform Redis operations
        return connection.send_command('GET', 'key')
    finally:
        if connection:
            pool.release(connection)

# Or use high-level client (recommended)
client = redis.Redis(connection_pool=pool)
result = client.get('key')  # Automatically handles connection lifecycle
```

### 3. Monitoring & Alerting
```python
# Pool health monitoring
def check_pool_health():
    pool = redis_client.connection_pool
    total_connections = pool._created_connections
    available = len(pool._available_connections) 
    in_use = len(pool._in_use_connections)
    
    utilization = in_use / pool.max_connections
    
    if utilization > 0.8:  # 80% pool utilization
        logger.warning(f"High pool utilization: {utilization:.2%}")
    
    return {
        'total': total_connections,
        'available': available,
        'in_use': in_use,
        'utilization': utilization
    }
```

## Debugging Connection Leaks

### 1. Application Logging
```python
import logging
import functools

def log_redis_connections(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        pool = redis_client.connection_pool
        before = len(pool._in_use_connections)
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            after = len(pool._in_use_connections)
            if after > before:
                logger.warning(f"Connection leak in {func.__name__}: {before} -> {after}")
    return wrapper
```

### 2. Redis Server Analysis
```bash
# Monitor connection creation/destruction patterns
redis-cli --csv --stat | grep connected_clients
# Look for steadily increasing connection counts

# Analyze client connection duration
redis-cli CLIENT LIST | awk '{print $3}' | sort | uniq -c
```

### 3. Memory Leak Correlation
```python
import psutil
import time

def monitor_memory_and_connections():
    process = psutil.Process()
    while True:
        memory_mb = process.memory_info().rss / 1024 / 1024
        pool_size = len(redis_client.connection_pool._in_use_connections)
        print(f"Memory: {memory_mb:.1f}MB, Pool size: {pool_size}")
        time.sleep(60)
```

## Production Troubleshooting Checklist
- [ ] Check application connection pool metrics
- [ ] Analyze Redis CLIENT LIST for connection patterns  
- [ ] Monitor file descriptor usage in applications
- [ ] Review recent code changes affecting Redis usage
- [ ] Check for blocking operations tying up connections
- [ ] Validate pool configuration vs application concurrency
- [ ] Test connection cleanup in exception scenarios
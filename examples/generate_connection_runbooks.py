#!/usr/bin/env python3
"""
Generate Redis connection troubleshooting runbooks based on real production issues.
"""

import asyncio
import logging

from dotenv import load_dotenv

from redis_sre_agent.tools.sre_functions import ingest_sre_document

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Real Redis connection issues and troubleshooting procedures
CONNECTION_RUNBOOKS = [
    {
        "title": "Redis Connection Limit Exceeded (ERR max number of clients reached)",
        "category": "connection_troubleshooting",
        "severity": "critical",
        "content": """
# Redis Connection Limit Exceeded Troubleshooting

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
""",
    },
    {
        "title": "Redis Connection Timeouts and Network Issues",
        "category": "connection_troubleshooting",
        "severity": "warning",
        "content": """
# Redis Connection Timeout Troubleshooting

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
""",
    },
    {
        "title": "Redis Connection Pool Exhaustion and Leak Detection",
        "category": "connection_troubleshooting",
        "severity": "warning",
        "content": r"""
# Redis Connection Pool Exhaustion & Leak Detection

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
""",
    },
]


async def generate_and_ingest_runbooks():
    """Generate and ingest Redis connection troubleshooting runbooks."""

    logger.info("🚀 Generating Redis Connection Troubleshooting Runbooks")
    logger.info("=" * 70)

    ingestion_results = []

    for i, runbook in enumerate(CONNECTION_RUNBOOKS, 1):
        logger.info(f"\n📝 Ingesting runbook {i}: {runbook['title']}")

        try:
            # Use the SRE document ingestion function
            result = await ingest_sre_document(
                title=runbook["title"],
                content=runbook["content"],
                source=f"Generated Redis Connection Runbook #{i}",
                category=runbook["category"],
                severity=runbook["severity"],
            )

            ingestion_results.append(
                {
                    "title": runbook["title"],
                    "status": "success",
                    "document_id": result.get("document_id"),
                    "task_id": result.get("task_id"),
                }
            )

            logger.info(f"✅ Successfully ingested: {result.get('document_id')}")

        except Exception as e:
            logger.error(f"❌ Failed to ingest runbook: {e}")
            ingestion_results.append(
                {"title": runbook["title"], "status": "error", "error": str(e)}
            )

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("📊 Ingestion Summary")
    logger.info("=" * 70)

    successful = len([r for r in ingestion_results if r["status"] == "success"])
    failed = len([r for r in ingestion_results if r["status"] == "error"])

    logger.info(f"✅ Successfully ingested: {successful} runbooks")
    if failed > 0:
        logger.info(f"❌ Failed to ingest: {failed} runbooks")

    # Test the new runbooks
    logger.info("\n🔍 Testing Connection Query Results After Ingestion")
    logger.info("=" * 70)

    from redis_sre_agent.tools.sre_functions import search_runbook_knowledge

    test_queries = [
        "Redis connection limit exceeded too many clients",
        "Redis connection timeout network issues",
        "Redis connection pool exhaustion leak detection",
    ]

    for query in test_queries:
        logger.info(f"\n🔍 Testing: '{query}'")
        try:
            result = await search_runbook_knowledge(query, limit=3)
            logger.info(f"   Results found: {len(result.get('results', []))}")

            for i, doc in enumerate(result.get("results", [])[:2], 1):
                title = doc.get("title", "Unknown")
                category = doc.get("category", "Unknown")
                logger.info(f"     {i}. {title} ({category})")

        except Exception as e:
            logger.error(f"   ❌ Search failed: {e}")

    return ingestion_results


if __name__ == "__main__":
    asyncio.run(generate_and_ingest_runbooks())

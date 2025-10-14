# Searching for Metrics with the Prometheus Provider

This guide explains how to search for and discover available metrics using the Prometheus provider.

## Overview

The Prometheus provider includes a `search_metrics` tool that searches for metrics by pattern. This enables both programmatic searching and LLM-driven metric discovery.

## Quick Start

### Direct Usage

```python
from redis_sre_agent.tools.metrics.prometheus import (
    PrometheusConfig,
    PrometheusToolProvider,
)

config = PrometheusConfig(url="http://localhost:9090")

async with PrometheusToolProvider(config=config) as provider:
    # Search for Redis metrics
    result = await provider.search_metrics(pattern="redis")

    if result["status"] == "success":
        print(f"Found {result['count']} Redis metrics")
        print(result["metrics"][:10])  # First 10

    # Search for memory metrics
    result = await provider.search_metrics(pattern="memory")
    print(f"Found {result['count']} memory metrics")

    # List all metrics (empty pattern)
    result = await provider.search_metrics(pattern="")
    print(f"Total metrics: {result['count']}")
```

### Via ToolManager (How the LLM Uses It)

```python
from redis_sre_agent.tools.manager import ToolManager

async with ToolManager() as manager:
    # Find the search_metrics tool
    tools = manager.get_tools()
    search_tool = next(t for t in tools if "search_metrics" in t.name)

    # Search for Redis memory metrics
    result = await manager.resolve_tool_call(
        search_tool.name,
        {"pattern": "redis_memory"}
    )

    print(f"Found {result['count']} metrics")
    print(result["metrics"])
```

## Common Search Patterns

### 1. Search by Prefix

```python
# Redis metrics
result = await provider.search_metrics(pattern="redis_")

# Node/system metrics
result = await provider.search_metrics(pattern="node_")

# Prometheus internal metrics
result = await provider.search_metrics(pattern="prometheus_")
```

### 2. Search by Keyword

```python
# Memory-related metrics
result = await provider.search_metrics(pattern="memory")

# Network metrics
result = await provider.search_metrics(pattern="network")

# Connection metrics
result = await provider.search_metrics(pattern="connected")
```

### 3. Search by Specific Metric

```python
# Very specific search
result = await provider.search_metrics(pattern="redis_memory_used")
# Returns: redis_memory_used_bytes, redis_memory_used_dataset_bytes, etc.
```

### 4. List All Metrics

```python
# Empty pattern returns everything
result = await provider.search_metrics(pattern="")
# Returns: All 1,165+ metrics
```

## LLM Workflow

When an LLM uses the Prometheus provider, it follows this pattern:

### Step 1: Discovery

**User:** "How much memory is Redis using?"

**LLM Action:**
```python
# Search for Redis memory metrics
result = await manager.resolve_tool_call(
    "prometheus_search_metrics",
    {"pattern": "redis_memory"}
)
# Returns: 14 metrics including redis_memory_used_bytes
```

### Step 2: Querying

**LLM Action:**
```python
# Query the specific metric
result = await manager.resolve_tool_call(
    "prometheus_query",
    {"query": "redis_memory_used_bytes"}
)

value = int(result["data"][0]["value"][1])
mb = value / (1024 * 1024)
```

### Step 3: Response

**LLM Response:** "Redis is using 24.28 MB of memory"

## Example Scenarios

### Scenario 1: Simple Metric Lookup

**User:** "How many clients are connected to Redis?"

**LLM Workflow:**
1. Search: `search_metrics(pattern="redis_connected")`
2. Find: `redis_connected_clients`
3. Query: `prometheus_query(query="redis_connected_clients")`
4. Response: "There are 1 clients connected"

### Scenario 2: Calculated Metrics

**User:** "What's the Redis cache hit rate?"

**LLM Workflow:**
1. Search: `search_metrics(pattern="redis_keyspace")`
2. Find: `redis_keyspace_hits_total` and `redis_keyspace_misses_total`
3. Query with PromQL calculation:
   ```promql
   rate(redis_keyspace_hits_total[1m]) /
   (rate(redis_keyspace_hits_total[1m]) + rate(redis_keyspace_misses_total[1m]))
   ```
4. Response: "Redis hit rate is 95.3%"

### Scenario 3: Trend Analysis

**User:** "Show me memory usage over the last hour"

**LLM Workflow:**
1. Search: `search_metrics(pattern="redis_memory_used")`
2. Find: `redis_memory_used_bytes`
3. Use range query:
   ```python
   prometheus_query_range(
       query="redis_memory_used_bytes",
       start_time="1h",
       end_time="now",
       step="5m"
   )
   ```
4. Response: "Memory usage has been stable around 25 MB for the past hour"

### Scenario 4: Exploration

**User:** "What Redis metrics are available?"

**LLM Workflow:**
1. Search: `search_metrics(pattern="redis")`
2. Returns: 187 Redis metrics
3. Group by category (memory, clients, keyspace, etc.)
4. Response: "I found 187 Redis metrics including:
   - Memory: redis_memory_used_bytes, redis_memory_max_bytes
   - Clients: redis_connected_clients, redis_blocked_clients
   - Keyspace: redis_keyspace_hits_total, redis_keyspace_misses_total
   - Performance: redis_commands_processed_total, redis_instantaneous_ops_per_sec"

## Metric Naming Conventions

Understanding Prometheus naming helps with searching:

### Prefixes
- `redis_*` - Redis metrics (from redis_exporter)
- `node_*` - System/node metrics (from node_exporter)
- `prometheus_*` - Prometheus internal metrics
- `grafana_*` - Grafana metrics
- `go_*` - Go runtime metrics

### Suffixes
- `*_total` - Counters (always increasing, use with `rate()`)
- `*_bytes` - Byte measurements (gauges)
- `*_seconds` - Time measurements (gauges)
- `*_bucket` - Histogram buckets
- `*_count` - Histogram/summary counts
- `*_sum` - Histogram/summary sums

### Common Patterns
- `*_used_*` - Current usage
- `*_max_*` - Maximum/limit values
- `*_available_*` - Available capacity
- `*_connected_*` - Connection counts
- `*_processed_*` - Processing counters

## Performance Benefits

### Efficient Discovery

Instead of retrieving all 1,165+ metrics and filtering client-side:

```python
# OLD WAY (if we had list_metrics):
# 1. Get all metrics
all_metrics = await provider.list_metrics()  # Returns 1,165+ metrics
# 2. Filter in Python
redis_metrics = [m for m in all_metrics["metrics"] if "redis" in m]

# NEW WAY (with search_metrics):
# 1. Search directly
result = await provider.search_metrics(pattern="redis")  # Returns 187 metrics
```

**Benefits:**
- Less data transferred
- Faster response time
- Simpler LLM workflow
- Single tool call instead of two operations

## Example Scripts

See the `examples/` directory for complete working examples:

- `examples/search_metrics.py` - Various search patterns
- `examples/llm_metric_search_workflow.py` - Simulated LLM workflow
- `examples/test_metric_search.py` - Comparison tests

## API Reference

### `search_metrics(pattern="", label_filters=None)`

Search for metrics by name pattern.

**Parameters:**
- `pattern` (str, optional): Search pattern (case-insensitive substring match). Default: "" (all metrics)
- `label_filters` (dict, optional): Label filters to narrow results

**Returns:**
```python
{
    "status": "success",
    "pattern": "redis",
    "metrics": ["redis_memory_used_bytes", "redis_connected_clients", ...],
    "count": 187,
    "timestamp": "2025-10-14T12:00:00Z"
}
```

**Examples:**
```python
# Search for Redis metrics
result = await provider.search_metrics(pattern="redis")

# Search for memory metrics
result = await provider.search_metrics(pattern="memory")

# List all metrics
result = await provider.search_metrics(pattern="")

# Search with label filters (advanced)
result = await provider.search_metrics(
    pattern="redis",
    label_filters={"job": "redis", "instance": "localhost:6379"}
)
```

## See Also

- [Prometheus Provider README](../redis_sre_agent/tools/metrics/prometheus/README.md)
- [Prometheus Metric Types](https://prometheus.io/docs/concepts/metric_types/)
- [PromQL Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)

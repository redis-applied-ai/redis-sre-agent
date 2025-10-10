# Searching for Metrics with the Prometheus Provider

This guide explains how to search for and discover available metrics using the Prometheus provider.

## Overview

The Prometheus provider includes a `list_metrics` tool that returns all available metric names from Prometheus. This enables both programmatic searching and LLM-driven metric discovery.

## Quick Start

### Direct Usage

```python
from redis_sre_agent.tools.metrics.prometheus import (
    PrometheusConfig,
    PrometheusToolProvider,
)

config = PrometheusConfig(url="http://localhost:9090")

async with PrometheusToolProvider(config=config) as provider:
    # Get all metrics
    result = await provider.list_metrics()

    if result["status"] == "success":
        all_metrics = result["metrics"]
        print(f"Found {result['count']} metrics")

        # Search for Redis metrics
        redis_metrics = [m for m in all_metrics if "redis" in m]
        print(f"Redis metrics: {redis_metrics}")
```

### Via ToolManager (How the LLM Uses It)

```python
from redis_sre_agent.tools.manager import ToolManager

async with ToolManager() as manager:
    # Find the list_metrics tool
    tools = manager.get_tools()
    list_tool = next(t for t in tools if "list_metrics" in t.name)

    # Execute it
    result = await manager.resolve_tool_call(list_tool.name, {})

    # Filter results
    all_metrics = result["metrics"]
    memory_metrics = [m for m in all_metrics if "memory" in m]
```

## Common Search Patterns

### 1. Search by Prefix

Metrics are typically prefixed by their source:

```python
# Redis metrics
redis_metrics = [m for m in all_metrics if m.startswith("redis_")]

# Node/system metrics
node_metrics = [m for m in all_metrics if m.startswith("node_")]

# Prometheus internal metrics
prom_metrics = [m for m in all_metrics if m.startswith("prometheus_")]
```

### 2. Search by Keyword

```python
# Memory-related metrics
memory_metrics = [m for m in all_metrics if "memory" in m.lower()]

# Network metrics
network_metrics = [m for m in all_metrics if "network" in m.lower()]

# Connection metrics
connection_metrics = [m for m in all_metrics if "connection" in m or "client" in m]
```

### 3. Search by Suffix

Prometheus has naming conventions:

```python
# Counter metrics (always increasing)
counters = [m for m in all_metrics if m.endswith("_total")]

# Gauge metrics (can go up or down)
gauges = [m for m in all_metrics if m.endswith("_bytes") or m.endswith("_seconds")]

# Histogram buckets
histograms = [m for m in all_metrics if "_bucket" in m]
```

### 4. Search by Category

```python
# Group by prefix
from collections import defaultdict

categories = defaultdict(list)
for metric in all_metrics:
    prefix = metric.split("_")[0]
    categories[prefix].append(metric)

# Show categories
for prefix, metrics in sorted(categories.items()):
    print(f"{prefix}: {len(metrics)} metrics")
```

## LLM Workflow

When an LLM uses the Prometheus provider, it follows this pattern:

### Step 1: Discovery

**User:** "How much memory is Redis using?"

**LLM Action:**
```python
# Call list_metrics to get all available metrics
result = await manager.resolve_tool_call("prometheus_list_metrics", {})
all_metrics = result["metrics"]  # Returns 1,165+ metrics
```

### Step 2: Filtering

**LLM Thinking:** "I need Redis memory metrics..."

```python
# Filter for Redis + memory
redis_memory = [m for m in all_metrics
                if "redis" in m and "memory" in m]
# Results: ['redis_memory_used_bytes', 'redis_memory_max_bytes', ...]

# Pick the best match
best_match = "redis_memory_used_bytes"
```

### Step 3: Querying

**LLM Action:**
```python
# Query the metric
result = await manager.resolve_tool_call(
    "prometheus_query",
    {"query": "redis_memory_used_bytes"}
)

value = int(result["data"][0]["value"][1])
mb = value / (1024 * 1024)
```

### Step 4: Response

**LLM Response:** "Redis is using 24.28 MB of memory"

## Example Scenarios

### Scenario 1: Simple Metric Lookup

**User:** "How many clients are connected to Redis?"

**LLM Workflow:**
1. Search metrics for "redis" + "client" or "connection"
2. Find `redis_connected_clients`
3. Query: `prometheus_query(query="redis_connected_clients")`
4. Response: "There are 1 clients connected"

### Scenario 2: Calculated Metrics

**User:** "What's the Redis cache hit rate?"

**LLM Workflow:**
1. Search for "redis" + "keyspace"
2. Find `redis_keyspace_hits_total` and `redis_keyspace_misses_total`
3. Query with PromQL calculation:
   ```promql
   rate(redis_keyspace_hits_total[1m]) /
   (rate(redis_keyspace_hits_total[1m]) + rate(redis_keyspace_misses_total[1m]))
   ```
4. Response: "Redis hit rate is 95.3%"

### Scenario 3: Trend Analysis

**User:** "Show me memory usage over the last hour"

**LLM Workflow:**
1. Already knows `redis_memory_used_bytes` from previous search
2. Use range query:
   ```python
   prometheus_query_range(
       query="redis_memory_used_bytes",
       start_time="1h",
       end_time="now",
       step="5m"
   )
   ```
3. Response: "Memory usage has been stable around 25 MB for the past hour"

### Scenario 4: Exploration

**User:** "What Redis metrics are available?"

**LLM Workflow:**
1. Call `list_metrics()`
2. Filter for `redis_*`
3. Group by category (memory, clients, keyspace, etc.)
4. Response: "I found 185 Redis metrics including:
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

## Performance Tips

### 1. Cache the Metric List

The metric list doesn't change frequently:

```python
# Call once per conversation
result = await provider.list_metrics()
all_metrics = result["metrics"]

# Reuse for multiple searches
redis_metrics = [m for m in all_metrics if "redis" in m]
memory_metrics = [m for m in all_metrics if "memory" in m]
```

### 2. Use Specific Searches

Instead of listing all metrics every time:

```python
# If you know what you're looking for
if "redis_memory_used_bytes" in all_metrics:
    # Query directly
    result = await provider.query("redis_memory_used_bytes")
```

### 3. Combine Filters

```python
# Multiple criteria
redis_memory_gauges = [
    m for m in all_metrics
    if m.startswith("redis_")
    and "memory" in m
    and not m.endswith("_total")
]
```

## Example Scripts

See the `examples/` directory for complete working examples:

- `examples/search_metrics.py` - Various search patterns
- `examples/llm_metric_search_workflow.py` - Simulated LLM workflow
- `examples/test_redis_metrics.py` - Redis-specific metric queries

## API Reference

### `list_metrics()`

Returns all available metric names from Prometheus.

**Parameters:** None

**Returns:**
```python
{
    "status": "success",
    "metrics": ["metric1", "metric2", ...],
    "count": 1165,
    "timestamp": "2025-10-10T12:00:00Z"
}
```

**Example:**
```python
result = await provider.list_metrics()
all_metrics = result["metrics"]
```

## See Also

- [Prometheus Provider README](../redis_sre_agent/tools/metrics/prometheus/README.md)
- [Prometheus Metric Types](https://prometheus.io/docs/concepts/metric_types/)
- [PromQL Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)

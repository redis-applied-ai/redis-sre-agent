# Prometheus Metrics Provider

A tool provider for querying Prometheus metrics, built using the `prometheus-api-client` library.

## Features

- **Instant Queries**: Get current metric values
- **Range Queries**: Query metrics over time periods
- **Metric Discovery**: List all available metrics
- **Error Handling**: Graceful error responses
- **Instance Scoping**: Support for Redis instance-specific queries

## Installation

The provider is included with the Redis SRE Agent. The `prometheus-api-client` dependency is automatically installed.

## Configuration

```python
from redis_sre_agent.tools.metrics.prometheus import PrometheusConfig

config = PrometheusConfig(
    url="http://localhost:9090",  # Prometheus server URL
    disable_ssl=False              # Set to True to disable SSL verification
)
```

### Environment Variables

You can also configure via environment variables:

```bash
export PROMETHEUS_URL=http://prometheus.example.com:9090
export PROMETHEUS_DISABLE_SSL=false
```

## Usage

### Basic Usage

```python
from redis_sre_agent.tools.metrics.prometheus import (
    PrometheusConfig,
    PrometheusToolProvider,
)

config = PrometheusConfig(url="http://localhost:9090")

async with PrometheusToolProvider(config=config) as provider:
    # Query current memory usage
    result = await provider.query(
        query="node_memory_MemAvailable_bytes"
    )
    print(result)
```

### Range Queries

```python
# Query network throughput over the last hour
result = await provider.query_range(
    query="rate(node_network_transmit_bytes_total[5m])",
    start_time="1h",
    end_time="now",
    step="1m"
)
```

### List Available Metrics

```python
result = await provider.list_metrics()
print(f"Found {result['count']} metrics")
print(result['metrics'])
```

### With Redis Instance Context

```python
from redis_sre_agent.api.instances import RedisInstance

redis_instance = RedisInstance(
    id="prod-cache",
    name="Production Cache",
    connection_url="redis://localhost:6379",
    environment="production",
    usage="cache",
    description="Main production cache"
)

async with PrometheusToolProvider(
    config=config,
    redis_instance=redis_instance
) as provider:
    # Tools will be scoped to this Redis instance
    result = await provider.query(query="redis_connected_clients")
```

## Tools Provided

The provider exposes three tools to the LLM:

### 1. `prometheus_{hash}_query`

Query Prometheus metrics at a single point in time.

**Parameters:**
- `query` (string, required): PromQL query expression

**Example:**
```python
{
    "query": "node_memory_MemAvailable_bytes"
}
```

### 2. `prometheus_{hash}_query_range`

Query Prometheus metrics over a time range.

**Parameters:**
- `query` (string, required): PromQL query expression
- `start_time` (string, required): Start time (e.g., "1h", "2d", "7d")
- `end_time` (string, optional): End time (default: "now")
- `step` (string, optional): Query resolution step (default: "15s")

**Example:**
```python
{
    "query": "rate(node_cpu_seconds_total[5m])",
    "start_time": "1h",
    "end_time": "now",
    "step": "1m"
}
```

### 3. `prometheus_{hash}_list_metrics`

List all available metric names in Prometheus.

**Parameters:** None

## Response Format

All methods return a dictionary with the following structure:

### Success Response

```python
{
    "status": "success",
    "query": "up",
    "data": [...],  # Prometheus query result
    "timestamp": "2025-10-10T12:00:00Z"
}
```

### Error Response

```python
{
    "status": "error",
    "error": "Error message",
    "query": "invalid_query"
}
```

## Testing

The provider includes comprehensive integration tests using testcontainers:

```bash
# Run all Prometheus provider tests
uv run pytest tests/tools/metrics/prometheus/ -v

# Run a specific test
uv run pytest tests/tools/metrics/prometheus/test_prometheus_provider.py::test_query_prometheus_up_metric -v
```

Tests use a real Prometheus container to ensure accurate behavior.

## Example Queries

### Infrastructure Monitoring

```python
# Memory usage
await provider.query("node_memory_MemAvailable_bytes")

# CPU usage
await provider.query("rate(node_cpu_seconds_total[5m])")

# Disk I/O
await provider.query("rate(node_disk_io_time_seconds_total[5m])")

# Network throughput
await provider.query("rate(node_network_transmit_bytes_total[5m])")
```

### Redis-Specific Metrics

```python
# Connected clients
await provider.query("redis_connected_clients")

# Memory usage
await provider.query("redis_memory_used_bytes")

# Commands per second
await provider.query("rate(redis_commands_total[1m])")

# Keyspace hits/misses
await provider.query("rate(redis_keyspace_hits_total[1m])")
```

## Demo

Run the included demo to see the provider in action:

```bash
# Make sure Prometheus is running on localhost:9090
uv run python examples/prometheus_provider_demo.py
```

## Architecture

The provider follows the standard tool provider pattern:

1. **Config Class**: `PrometheusConfig` - Configuration model
2. **Provider Class**: `PrometheusToolProvider` - Implements `ToolProvider` ABC
3. **Client**: Uses `prometheus-api-client` library for HTTP API calls
4. **Tool Schemas**: Defines tools for LLM consumption
5. **Tool Routing**: Routes tool calls to appropriate methods

## Dependencies

- `prometheus-api-client`: Python client for Prometheus HTTP API
- `pydantic`: Configuration validation
- `testcontainers`: Integration testing (dev dependency)

## See Also

- [Prometheus Documentation](https://prometheus.io/docs/)
- [PromQL Query Language](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [prometheus-api-client Documentation](https://prometheus-api-client-python.readthedocs.io/)

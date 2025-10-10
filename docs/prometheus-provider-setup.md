# Prometheus Provider Setup Guide

This guide shows how to enable and use the Prometheus metrics provider with the Redis SRE Agent.

## Quick Start

### 1. Configure Environment Variables

Add to your `.env` file:

```bash
# Prometheus Configuration
PROMETHEUS_URL=http://localhost:9090
PROMETHEUS_DISABLE_SSL=false

# Enable Prometheus Provider
TOOL_PROVIDERS='["redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider"]'
```

### 2. Start Prometheus

If you don't have Prometheus running, you can start it with Docker:

```bash
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  prom/prometheus:latest
```

### 3. Verify Provider is Loaded

Start the agent and check the logs:

```bash
uv run python -m redis_sre_agent.api.app
```

You should see:

```
INFO - Loaded provider prometheus with 3 tools
INFO - ToolManager initialized with X tools from Y providers
```

## Available Tools

Once enabled, the agent has access to three Prometheus tools:

### 1. `prometheus_query`

Query current metric values.

**Example LLM usage:**
```
"What is the current memory usage?"
→ Uses: prometheus_query(query="node_memory_MemAvailable_bytes")
```

### 2. `prometheus_query_range`

Query metrics over a time period.

**Example LLM usage:**
```
"Show me CPU usage over the last hour"
→ Uses: prometheus_query_range(
    query="rate(node_cpu_seconds_total[5m])",
    start_time="1h",
    end_time="now"
)
```

### 3. `prometheus_list_metrics`

Discover available metrics.

**Example LLM usage:**
```
"What metrics are available?"
→ Uses: prometheus_list_metrics()
```

## Testing the Integration

### Manual Test

You can test the provider manually:

```bash
uv run python examples/prometheus_provider_demo.py
```

### Automated Tests

Run the full test suite:

```bash
# All Prometheus tests
uv run pytest tests/tools/metrics/prometheus/ -v

# Just integration tests
uv run pytest tests/tools/metrics/prometheus/test_prometheus_integration.py -v

# Just provider tests
uv run pytest tests/tools/metrics/prometheus/test_prometheus_provider.py -v
```

## Example Agent Conversations

### Scenario 1: Infrastructure Monitoring

**User:** "What's the current memory usage on the server?"

**Agent:**
1. Uses `prometheus_list_metrics()` to find memory-related metrics
2. Uses `prometheus_query(query="node_memory_MemAvailable_bytes")` to get current value
3. Responds: "The server has 8.2 GB of available memory out of 16 GB total."

### Scenario 2: Performance Investigation

**User:** "Has CPU usage been high in the last hour?"

**Agent:**
1. Uses `prometheus_query_range()` to get CPU metrics over the last hour
2. Analyzes the time-series data
3. Responds: "CPU usage has been consistently around 75% for the past hour, with a spike to 95% at 2:30 PM."

### Scenario 3: Redis Monitoring

**User:** "How many clients are connected to Redis?"

**Agent:**
1. Uses `prometheus_query(query="redis_connected_clients")`
2. Responds: "There are currently 42 clients connected to Redis."

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_URL` | `http://localhost:9090` | Prometheus server URL |
| `PROMETHEUS_DISABLE_SSL` | `false` | Disable SSL certificate verification |
| `TOOL_PROVIDERS` | `[]` | List of enabled tool providers (JSON array) |

### Programmatic Configuration

You can also configure the provider programmatically:

```python
from redis_sre_agent.tools.metrics.prometheus import (
    PrometheusConfig,
    PrometheusToolProvider,
)

config = PrometheusConfig(
    url="http://prometheus.example.com:9090",
    disable_ssl=False
)

async with PrometheusToolProvider(config=config) as provider:
    result = await provider.query(query="up")
    print(result)
```

## Common PromQL Queries

Here are some useful PromQL queries the agent can use:

### Infrastructure Metrics

```promql
# Memory
node_memory_MemAvailable_bytes
node_memory_MemTotal_bytes

# CPU
rate(node_cpu_seconds_total[5m])
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Disk
node_disk_io_time_seconds_total
node_filesystem_avail_bytes

# Network
rate(node_network_transmit_bytes_total[5m])
rate(node_network_receive_bytes_total[5m])
```

### Redis Metrics

```promql
# Connections
redis_connected_clients
redis_blocked_clients

# Memory
redis_memory_used_bytes
redis_memory_max_bytes

# Performance
rate(redis_commands_total[1m])
redis_instantaneous_ops_per_sec

# Keyspace
redis_keyspace_hits_total
redis_keyspace_misses_total
rate(redis_keyspace_hits_total[5m]) / (rate(redis_keyspace_hits_total[5m]) + rate(redis_keyspace_misses_total[5m]))
```

## Troubleshooting

### Provider Not Loading

**Symptom:** No Prometheus tools available

**Solutions:**
1. Check `TOOL_PROVIDERS` environment variable is set correctly
2. Verify the provider path is correct
3. Check logs for loading errors

### Connection Errors

**Symptom:** "Connection refused" or timeout errors

**Solutions:**
1. Verify Prometheus is running: `curl http://localhost:9090/api/v1/status/config`
2. Check `PROMETHEUS_URL` is correct
3. Ensure network connectivity

### No Metrics Available

**Symptom:** `list_metrics()` returns empty list

**Solutions:**
1. Verify Prometheus is scraping targets
2. Check Prometheus configuration
3. Wait a few seconds for initial scrape

### SSL Certificate Errors

**Symptom:** SSL verification errors

**Solutions:**
1. Set `PROMETHEUS_DISABLE_SSL=true` for testing
2. Add proper SSL certificates for production
3. Use HTTP instead of HTTPS for local development

## Production Considerations

### Security

1. **Authentication:** Prometheus provider doesn't currently support authentication. Use network-level security (VPN, firewall rules).
2. **SSL/TLS:** Enable SSL in production and provide proper certificates.
3. **Rate Limiting:** Consider rate limiting on the Prometheus server.

### Performance

1. **Query Complexity:** Complex PromQL queries can be expensive. Monitor query performance.
2. **Time Ranges:** Large time ranges return more data. Use appropriate `step` values.
3. **Caching:** Consider caching frequently-used metrics.

### Monitoring

1. **Provider Health:** Monitor provider initialization and query success rates.
2. **Query Latency:** Track how long Prometheus queries take.
3. **Error Rates:** Alert on high error rates from the provider.

## Next Steps

- **Add More Providers:** Follow the same pattern to add Grafana, Loki, or other providers
- **Custom Metrics:** Configure Prometheus to scrape your Redis instances
- **Dashboards:** Create Grafana dashboards that complement the agent's capabilities
- **Alerts:** Set up Prometheus alerts that the agent can query and investigate

## See Also

- [Prometheus Provider README](../redis_sre_agent/tools/metrics/prometheus/README.md)
- [PromQL Documentation](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Tool Provider Architecture](./tool-provider-architecture.md)

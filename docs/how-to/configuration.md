## Configuration

This guide explains how the Redis SRE Agent is configured, what the required and optional settings are, and how to override tool providers. For defaults, see [`redis_sre_agent/core/config.py`](https://github.com/redis-applied-ai/redis-sre-agent/blob/main/redis_sre_agent/core/config.py) and [`.env.example`](https://github.com/redis-applied-ai/redis-sre-agent/blob/main/.env.example).

### Sources and precedence

Configuration values are loaded from these sources (highest precedence first):

- Environment variables (recommended for prod)
- `.env` file (loaded automatically in dev if present)
- Code defaults in `redis_sre_agent/core/config.py`

### Required

- `OPENAI_API_KEY`: Your OpenAI API key

### Common optional settings

- `REDIS_URL`: Agent operational Redis (default: `redis://localhost:7843/0`)
- `PROMETHEUS_URL` / `GRAFANA_URL`: Optional app-level URLs for integrations
- `TOOLS_PROMETHEUS_URL` / `TOOLS_LOKI_URL`: Tool-specific endpoints
- `API_KEY`: API auth key (if you enable auth)
- `ALLOWED_HOSTS`: CORS origins (default: `["*"]`)

Example `.env` (local):

```bash
OPENAI_API_KEY=your_openai_key
REDIS_URL=redis://localhost:7843/0
# Optional tool endpoints
TOOLS_PROMETHEUS_URL=http://localhost:9090
TOOLS_LOKI_URL=http://localhost:3100
```

### Tool providers

Providers are loaded by the `ToolManager` based on:

- **Without an instance**: Knowledge base and basic utilities (date conversions, calculator)
- **With an instance**: All of the above plus the providers configured in `settings.tool_providers` (env: `TOOL_PROVIDERS`)
- **Conditional providers**: Additional providers based on instance type (Redis Enterprise admin, Redis Cloud)

Override provider list via environment (JSON list):

```bash
# Example: include built-in Prometheus + a custom provider
export TOOL_PROVIDERS='[
  "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider",
  "my_company.sre_tools.prometheus.PrometheusMetricsProvider"
]'
```

#### Per-instance configuration for providers

- Use `RedisInstance.extension_data` and `extension_secrets` to pass namespaced config to providers.
- See the [Tool Providers guide](tool-providers.md) for details.

### Advanced: Encryption of secrets

Secrets (e.g., connection URLs, admin passwords) are encrypted at rest using envelope encryption. See the advanced guide:

- [Advanced: Encryption of secrets](configuration/encryption.md)

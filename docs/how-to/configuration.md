## Configuration

This guide explains how the Redis SRE Agent is configured, what the required and optional settings are, and how to override tool providers. For defaults, see [`redis_sre_agent/core/config.py`](https://github.com/redis-applied-ai/redis-sre-agent/blob/main/redis_sre_agent/core/config.py) and [`.env.example`](https://github.com/redis-applied-ai/redis-sre-agent/blob/main/.env.example).

### Sources and precedence

Configuration values are loaded from these sources (highest precedence first):

1. Environment variables (recommended for prod)
2. `.env` file (loaded automatically in dev if present)
3. **YAML config file** (for complex nested configurations like MCP servers)
4. Code defaults in `redis_sre_agent/core/config.py`

### YAML configuration

For complex nested settings like MCP server configurations, you can use a YAML config file. This is particularly useful for configuring multiple MCP servers with tool descriptions.

**Config file discovery order:**

1. Path specified in `SRE_AGENT_CONFIG` environment variable
2. `config.yaml` in the current working directory
3. `config.yml` in the current working directory
4. `sre_agent_config.yaml` in the current working directory
5. `sre_agent_config.yml` in the current working directory

**Example `config.yaml`:**

```yaml
# Application settings
debug: false
log_level: INFO

# MCP (Model Context Protocol) servers configuration
mcp_servers:
  # Memory server for long-term agent memory
  redis-memory-server:
    command: uv
    args:
      - tool
      - run
      - --from
      - agent-memory-server
      - agent-memory
      - mcp
    env:
      REDIS_URL: redis://localhost:6399
    tools:
      search_long_term_memory:
        description: |
          Search saved memories about Redis instances. ALWAYS use this
          before troubleshooting to recall past issues and solutions.
          {original}

  # GitHub MCP server (remote) - uses GitHub's hosted MCP endpoint
  # Requires a GitHub Personal Access Token with appropriate permissions
  # Uses Streamable HTTP transport (default for URL-based connections)
  github:
    url: "https://api.githubcopilot.com/mcp/"
    headers:
      Authorization: "Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}"
    # transport: streamable_http  # default, can also be 'sse' for legacy servers
```

See `config.yaml.example` for a complete example with all available options.

**Using a custom config path:**

```bash
export SRE_AGENT_CONFIG=/path/to/my-config.yaml
```

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

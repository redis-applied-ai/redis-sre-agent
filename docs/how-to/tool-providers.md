## Tool Providers: Overview & Extensibility

The agent exposes capabilities to the LLM via a provider system managed by ToolManager.

This is an early release with an initial set of built-in providers. More providers for popular observability systems are coming. The tool system is fully extensible - you can write your own providers or add MCP servers.

### What loads
- **Without an instance**: Knowledge base and basic utilities (date conversions, calculator)
- **With an instance**: All of the above plus the providers configured in `settings.tool_providers` (Prometheus, Loki, Redis CLI, Host Telemetry)
- **Conditional providers**: Additional providers based on instance type (e.g., Redis Enterprise admin API, Redis Cloud API)
- **MCP servers**: External tools from configured MCP servers (see below)

### Built-in providers (v0.1)
- **Prometheus metrics**: `redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider`
  - Config: `TOOLS_PROMETHEUS_URL`, `TOOLS_PROMETHEUS_DISABLE_SSL`
- **Loki logs**: `redis_sre_agent.tools.logs.loki.provider.LokiToolProvider`
  - Config: `TOOLS_LOKI_URL`, `TOOLS_LOKI_TENANT_ID`, `TOOLS_LOKI_TIMEOUT`
- **Redis command diagnostics**: `redis_sre_agent.tools.diagnostics.redis_command.provider.RedisCommandToolProvider`
  - Runs Redis commands against target instances
- **Host telemetry**: `redis_sre_agent.tools.host_telemetry.provider.HostTelemetryToolProvider`
  - System-level metrics and diagnostics

More providers coming for popular observability and cloud platforms.

Configure providers (environment override)
```bash
# JSON list override for settings.tool_providers
export TOOL_PROVIDERS='[
  "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider",
  "my_company.sre_tools.prometheus.PrometheusMetricsProvider"
]'
```

Per-instance configuration
- Place namespaced keys in RedisInstance.extension_data / extension_secrets for provider-specific config
- Providers can declare instance_config_model and read from the namespace matching provider_name (default) or extension_namespace

## Create a custom provider

Implement a ToolProvider subclass that defines tool schemas and resolves calls.

### Minimal skeleton

```python
from typing import Any, Dict, List
from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.models import ToolDefinition, ToolCapability


class MyMetricsProvider(ToolProvider):
    @property
    def provider_name(self) -> str:
        return "my_metrics"

    def create_tool_schemas(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name=self._make_tool_name("query"),
                description="Query my metrics backend using a query string.",
                capability=ToolCapability.METRICS,
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            )
        ]

    async def query(self, query: str) -> Dict[str, Any]:
        # Implement your backend call
        return {"status": "success", "query": query, "data": []}
```

The base class `tools()` method automatically wires tool names to provider methods. When an LLM invokes `my_metrics_{hash}_query`, the framework calls `self.query(**args)` directly. No manual `resolve_tool_call()` implementation is required.

### Register your provider

- Install your package into the same environment as the agent (e.g., `pip install -e /path/to/pkg`)
- Add your dotted class path to TOOL_PROVIDERS (see example above)

### Design guidelines

- Use descriptive names and rich descriptions (the LLM relies on them)
- Return structured results: `{"status": "success"|"error", ...}`
- Use `_make_tool_name("operation")` to generate unique, instance-scoped tool names
- Implement `get_status_update` via `@status_update` decorator for better UX

### Reference

- [Base class and protocols](https://github.com/redis-applied-ai/redis-sre-agent/blob/main/redis_sre_agent/tools/protocols.py)
- [Manager lifecycle and routing](https://github.com/redis-applied-ai/redis-sre-agent/blob/main/redis_sre_agent/tools/manager.py)
- [Built-in Prometheus provider](https://github.com/redis-applied-ai/redis-sre-agent/blob/main/redis_sre_agent/tools/metrics/prometheus/provider.py)

---

## MCP Server Integration

Add external MCP servers to give the agent additional tools. The agent connects to configured MCP servers at startup and discovers available tools automatically.

### Configuration

Add MCP servers in `config.yaml`:

```yaml
mcp_servers:
  # Memory server (stdio transport - launches process)
  redis-memory-server:
    command: uv
    args: ["tool", "run", "--from", "agent-memory-server", "agent-memory", "mcp"]
    env:
      REDIS_URL: redis://localhost:6399
    tools:
      # Optional: customize tool descriptions for better LLM understanding
      search_long_term_memories:
        description: |
          Search memories for past incidents, resolutions, and context about
          this Redis instance. Use when investigating recurring issues.
          {original}

  # GitHub MCP server (HTTP transport - remote endpoint)
  github:
    url: "https://api.githubcopilot.com/mcp/"
    headers:
      Authorization: "Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}"

  # Local Docker MCP server
  github-local:
    command: docker
    args: ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: ${GITHUB_PERSONAL_ACCESS_TOKEN}
```

### Transport Types

- **stdio**: Launches a local process and communicates via stdin/stdout (default)
- **http/streamable_http**: Connects to a remote HTTP endpoint

### Tool Filtering

You can filter which MCP tools are exposed to the agent:

```yaml
mcp_servers:
  my-server:
    command: ...
    tools:
      # Only these tools will be available
      tool_name_1: {}
      tool_name_2:
        description: "Custom description for better LLM understanding"
```

If `tools` is not specified, all tools from the server are exposed.

### Excluding MCP Tool Categories

Use `exclude_mcp_categories` to exclude tools by capability:

```python
# In code
tool_manager = ToolManager(
    redis_instance=instance,
    exclude_mcp_categories=[ToolCapability.WRITE, ToolCapability.ADMIN]
)
```

See `config.yaml.example` for full MCP configuration examples.

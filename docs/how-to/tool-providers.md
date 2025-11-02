## Tool Providers: Overview & Extensibility

The agent exposes capabilities to the LLM via a provider system managed by ToolManager.

This is an early release with an initial set of built-in providers. More providers for popular observability systems are coming. The tool system is fully extensible - you can write your own providers to integrate with any system.

### What loads
- **Without an instance**: Knowledge base and basic utilities (date conversions, calculator)
- **With an instance**: All of the above plus the providers configured in `settings.tool_providers` (Prometheus, Loki, Redis CLI, Host Telemetry)
- **Conditional providers**: Additional providers based on instance type (e.g., Redis Enterprise admin API, Redis Cloud API)

### Built-in providers (v0.1)
- **Prometheus metrics**: `redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider`
  - Config: `TOOLS_PROMETHEUS_URL`, `TOOLS_PROMETHEUS_DISABLE_SSL`
- **Loki logs**: `redis_sre_agent.tools.logs.loki.provider.LokiToolProvider`
  - Config: `TOOLS_LOKI_URL`, `TOOLS_LOKI_TENANT_ID`, `TOOLS_LOKI_TIMEOUT`
- **Redis CLI diagnostics**: `redis_sre_agent.tools.diagnostics.redis_cli.provider.RedisCliToolProvider`
  - Runs Redis CLI commands against target instances
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

Minimal skeleton
```python
from typing import Any, Dict, List, Optional
from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

class MyMetricsProvider(ToolProvider):
    provider_name = "my_metrics"

    def create_tool_schemas(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name=self._make_tool_name("query"),
                description="Query my metrics backend using a query string.",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            )
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]):
        op = self.resolve_operation(tool_name)
        if op == "query":
            return await self.query(**args)
        raise ValueError(f"Unknown operation: {op}")

    async def query(self, query: str) -> Dict[str, Any]:
        # Implement your backend call
        return {"status": "success", "query": query, "data": []}
```

Register your provider
- Install your package into the same environment as the agent (e.g., pip install -e /path/to/pkg)
- Add your dotted class path to TOOL_PROVIDERS (see example above)

Design guidelines
- Use descriptive names and rich descriptions (the LLM relies on them)
- Return structured results: {"status": "success"|"error", ...}
- Use _make_tool_name("operation") to generate unique, instance-scoped tool names
- Implement get_status_update via @status_update decorator for better UX

Reference
- Base class and protocols: redis_sre_agent/tools/protocols.py
- Manager lifecycle and routing: redis_sre_agent/tools/manager.py
- Built-in Prometheus provider: redis_sre_agent/tools/metrics/prometheus/provider.py

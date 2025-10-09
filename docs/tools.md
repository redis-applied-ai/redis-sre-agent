# Tool Provider System

The Redis SRE Agent uses a flexible tool provider system that allows you to extend the agent with custom capabilities. Tools are automatically discovered and made available to the LLM based on your configuration.

## Quick Start

### Using Built-in Tools

The agent comes with a knowledge base tool enabled by default. To use it, simply start the agent:

```bash
# The knowledge base tool is automatically available
python -m redis_sre_agent.api.main
```

When you provide a `RedisInstance` in your query, instance-specific tools will also be loaded automatically. These are tools that are specific to the provided Redis instance, such as querying metrics or logs, or connecting to the instance to run INFO commands.

### Configuring Custom Tools

Add custom tool providers in `redis_sre_agent/config.py`:

```python
class Settings(BaseSettings):
    # ... other settings ...

    # Add your custom tool providers (dotted import paths)
    custom_tool_providers: List[str] = [
        "my_company.sre_tools.PrometheusMetricsProvider",
        "my_company.sre_tools.DatadogLogsProvider",
    ]
```

**Important:** Your custom tool providers must be installed in the same Python environment as the SRE agent.

## Creating Custom Tools

### Example: Custom Metrics Provider

Let's create a Prometheus metrics provider that the agent can use to query metrics.

**Step 1: Create your provider class**

Create a file `my_company/sre_tools/prometheus.py`:

```python
from typing import Any, Dict, List, Optional
from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

class PrometheusMetricsProvider(ToolProvider):
    """Provides Prometheus metrics querying capabilities."""

    provider_name = "prometheus"

    def __init__(self, redis_instance: Optional[RedisInstance] = None):
        super().__init__(redis_instance)
        # Initialize your Prometheus client
        self.prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
        self.client = PrometheusConnect(url=self.prometheus_url)

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Define the tools this provider offers."""
        return [
            ToolDefinition(
                name=self._make_tool_name("query_metric"),
                description=(
                    "Query Prometheus metrics for the Redis instance. "
                    "Use this to get current metric values, time-series data, "
                    "or analyze trends. Supports PromQL queries."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "PromQL query (e.g., 'redis_memory_used_bytes')"
                        },
                        "time_range": {
                            "type": "string",
                            "description": "Time range like '1h', '24h', '7d'",
                            "default": "1h"
                        }
                    },
                    "required": ["query"]
                }
            )
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute the tool call."""
        # Parse operation from tool_name
        operation = self._parse_operation(tool_name)

        if operation == "query_metric":
            return await self.query_metric(**args)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    async def query_metric(self, query: str, time_range: str = "1h") -> Dict[str, Any]:
        """Query Prometheus for metrics."""
        try:
            # Your implementation here
            result = self.client.custom_query(query)

            return {
                "status": "success",
                "query": query,
                "time_range": time_range,
                "data": result,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "query": query
            }
```

**Step 2: Install your package**

```bash
# Install your custom tools package in the same environment
pip install -e /path/to/my_company/sre_tools
```

**Step 3: Configure the agent**

Add to `config.py`:

```python
custom_tool_providers: List[str] = [
    "my_company.sre_tools.prometheus.PrometheusMetricsProvider",
]
```

**Step 4: Set environment variables**

```bash
export PROMETHEUS_URL=http://prometheus.mycompany.com:9090
```

That's it! The agent will now automatically discover and use your Prometheus metrics tool.


### Key Points for Custom Tools

1. **Inherit from `ToolProvider`** - This gives you the base functionality
2. **Set `provider_name`** - A unique identifier for your provider
3. **Implement `create_tool_schemas()`** - Define what tools you offer
4. **Implement `resolve_tool_call()`** - Handle tool execution
5. **Use `_make_tool_name()`** - Creates unique tool names scoped to instances
6. **Write good descriptions** - The LLM uses these to decide when to call your tool
7. **Return structured data** - Use dictionaries with clear status/error fields

## Best Practices for Designing Tool Providers

### 1. Use Descriptive Tool Names
```python
# Good: Clear operation name
ToolDefinition(
    name=self._make_tool_name("search_knowledge_base"),
    description="Search the SRE knowledge base for solutions"
)

# Bad: Vague name
ToolDefinition(
    name=self._make_tool_name("search"),  # Search what?
    description="Search"
)
```

### 2. Provide Rich Docstrings for LLMs
```python
# Good: Detailed guidance for LLM
async def search(self, query: str, category: Optional[str] = None):
    """Search the SRE knowledge base for relevant information.

    Use this tool to find solutions to problems, understand Redis features,
    or get guidance on SRE best practices. The knowledge base contains
    runbooks, Redis documentation, troubleshooting guides, and procedures.

    Args:
        query: Search query describing what you're looking for
        category: Optional filter (incident, maintenance, monitoring, etc.)
    """

# Bad: Minimal docs
async def search(self, query: str):
    """Search."""
```

### 3. Handle Errors
```python
async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
    try:
        # Parse and route
        operation = self._parse_operation(tool_name)
        return await self._execute(operation, args)
    except ValueError as e:
        # Return error to LLM, don't crash
        return {"error": str(e), "status": "failed"}
    except Exception as e:
        logger.exception(f"Tool execution failed: {tool_name}")
        return {"error": "Internal error", "status": "failed"}
```

## Architecture Reference

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      LangGraph Agent                        │
│                                                             │
│  process_query(query, redis_instance)                      │
│    │                                                        │
│    ├─► Create ToolManager(redis_instance)                  │
│    ├─► Get tool schemas: mgr.get_tools()                   │
│    ├─► Build workflow with tools                           │
│    └─► Execute: mgr.resolve_tool_call(name, args)          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Tool Manager                          │
│                                                             │
│  - Load providers (knowledge base, metrics, etc.)          │
│  - Build routing table: {tool_name: provider_instance}     │
│  - Async context manager for lifecycle                     │
│  - Route tool calls to correct provider                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Tool Providers (ABC)                     │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │ Knowledge Base   │  │ Redis Metrics    │               │
│  │ Provider         │  │ Provider         │  ...          │
│  │                  │  │                  │               │
│  │ - search         │  │ - get_info       │               │
│  │ - ingest         │  │ - get_slowlog    │               │
│  └──────────────────┘  └──────────────────┘               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Helper Functions                         │
│                                                             │
│  Core business logic (core/knowledge_helpers.py, etc.)     │
│  - Called by both tasks (background) and tools (LLM)       │
│  - Single source of truth for implementation               │
└─────────────────────────────────────────────────────────────┘
```

# Tool Provider System

The Redis SRE Agent uses a flexible tool provider system that allows you to extend the agent with custom capabilities. Tools are automatically discovered and made available to the LLM based on your configuration.

## Quick Start

### Using Built-in Tools

The agent comes with a knowledge base tool enabled by default. To use it, simply start the agent:

```bash
# The knowledge base tool is automatically available
python -m redis_sre_agent.api.main
```

When you provide a `RedisInstance` in your query, instance-specific tools will also be loaded automatically.

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

### Example: Custom Logs Provider

Here's another example for a logs provider:

```python
from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

class DatadogLogsProvider(ToolProvider):
    """Provides Datadog log search capabilities."""

    provider_name = "datadog_logs"

    def __init__(self, redis_instance: Optional[RedisInstance] = None):
        super().__init__(redis_instance)
        self.api_key = os.getenv("DATADOG_API_KEY")
        self.app_key = os.getenv("DATADOG_APP_KEY")
        # Initialize Datadog client

    def create_tool_schemas(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name=self._make_tool_name("search_logs"),
                description=(
                    "Search Datadog logs for the Redis instance. "
                    "Use this to find errors, warnings, or specific events. "
                    "Supports Datadog log query syntax."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Datadog log query (e.g., 'service:redis status:error')"
                        },
                        "time_range": {
                            "type": "string",
                            "description": "Time range like '1h', '24h'",
                            "default": "1h"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of log entries to return",
                            "default": 100
                        }
                    },
                    "required": ["query"]
                }
            )
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        operation = self._parse_operation(tool_name)

        if operation == "search_logs":
            return await self.search_logs(**args)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    async def search_logs(
        self,
        query: str,
        time_range: str = "1h",
        limit: int = 100
    ) -> Dict[str, Any]:
        """Search Datadog logs."""
        # Your implementation using Datadog API
        # ...

        return {
            "status": "success",
            "query": query,
            "logs": logs_data,
            "total_count": len(logs_data)
        }
```

### Key Points for Custom Tools

1. **Inherit from `ToolProvider`** - This gives you the base functionality
2. **Set `provider_name`** - A unique identifier for your provider
3. **Implement `create_tool_schemas()`** - Define what tools you offer
4. **Implement `resolve_tool_call()`** - Handle tool execution
5. **Use `_make_tool_name()`** - Creates unique tool names scoped to instances
6. **Write good descriptions** - The LLM uses these to decide when to call your tool
7. **Return structured data** - Use dictionaries with clear status/error fields

## Core Components

### 1. ToolProvider (ABC)

Base class for all tool providers:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from redis_sre_agent.tools.tool_definition import ToolDefinition

class ToolProvider(ABC):
    """Abstract base class for tool providers."""

    provider_name: str = "base_provider"  # Override in subclass

    def __init__(self, redis_instance: Optional[RedisInstance] = None):
        """Initialize provider with optional Redis instance for scoping."""
        self.redis_instance = redis_instance
        self._instance_hash = self._compute_instance_hash()

    @abstractmethod
    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Return list of tool definitions this provider offers."""
        pass

    @abstractmethod
    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a tool call and return the result."""
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass

    def _make_tool_name(self, operation: str) -> str:
        """Create unique tool name: {provider}_{hash}_{operation}"""
        return f"{self.provider_name}_{self._instance_hash}_{operation}"
```

### 2. ToolDefinition

Pure schema model for OpenAI function calling:

```python
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class ToolDefinition(BaseModel):
    """Schema definition for a tool (no execution logic)."""

    name: str = Field(..., description="Unique tool name")
    description: str = Field(..., description="What the tool does")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for parameters"
    )

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
```

### 3. ToolManager

Centralized lifecycle and routing:

```python
from redis_sre_agent.tools.manager import ToolManager

class ToolManager:
    """Manages tool provider lifecycle and routing."""

    def __init__(self, redis_instance: Optional[RedisInstance] = None):
        self.redis_instance = redis_instance
        self.providers: List[ToolProvider] = []
        self.routing_table: Dict[str, ToolProvider] = {}

    async def __aenter__(self):
        """Load and initialize all providers."""
        # Always load knowledge base provider
        kb_provider = KnowledgeBaseToolProvider()
        await kb_provider.__aenter__()
        self.providers.append(kb_provider)

        # Build routing table
        for provider in self.providers:
            schemas = provider.create_tool_schemas()
            for schema in schemas:
                self.routing_table[schema.name] = provider

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup all providers."""
        for provider in self.providers:
            await provider.__aexit__(exc_type, exc_val, exc_tb)

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get all tool schemas for LLM."""
        tools = []
        for provider in self.providers:
            schemas = provider.create_tool_schemas()
            tools.extend([s.to_openai_schema() for s in schemas])
        return tools

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Route tool call to appropriate provider."""
        provider = self.routing_table.get(tool_name)
        if not provider:
            raise ValueError(f"Unknown tool: {tool_name}")
        return await provider.resolve_tool_call(tool_name, args)
```

## Implemented Providers

### Knowledge Base Provider

Currently the only implemented provider. Provides access to the SRE knowledge base:

```python
from redis_sre_agent.tools.knowledge.knowledge_base import KnowledgeBaseToolProvider

class KnowledgeBaseToolProvider(ToolProvider):
    provider_name = "knowledge"

    def create_tool_schemas(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name=self._make_tool_name("search"),
                description="Search the SRE knowledge base",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "category": {"type": "string"},
                        "limit": {"type": "integer", "default": 5}
                    },
                    "required": ["query"]
                }
            ),
            ToolDefinition(
                name=self._make_tool_name("ingest"),
                description="Ingest a document into the knowledge base",
                parameters={...}
            )
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        # Parse operation from tool_name
        parts = tool_name.split("_")
        operation = "_".join(parts[2:])  # After provider_hash

        if operation == "search":
            return await self.search(**args)
        elif operation == "ingest":
            return await self.ingest(**args)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    async def search(self, query: str, category: Optional[str] = None, limit: int = 5):
        # Call helper function
        from redis_sre_agent.core.knowledge_helpers import search_knowledge_base_helper
        return await search_knowledge_base_helper(query, category, limit)

    async def ingest(self, title: str, content: str, source: str, ...):
        # Call helper function
        from redis_sre_agent.core.knowledge_helpers import ingest_sre_document_helper
        return await ingest_sre_document_helper(title, content, source, ...)
```

## Agent Integration

The agent uses ToolManager per-query:

```python
from redis_sre_agent.tools.manager import ToolManager

class SRELangGraphAgent:
    async def process_query(
        self,
        query: str,
        redis_instance: Optional[RedisInstance] = None,
        ...
    ):
        # Create ToolManager for this query
        async with ToolManager(redis_instance=redis_instance) as tool_manager:
            # Get tool schemas for LLM
            tools = tool_manager.get_tools()

            # Bind tools to LLM
            llm_with_tools = self.llm.bind_tools(tools)

            # Build workflow with tool execution node
            workflow = self._build_workflow(llm_with_tools, tool_manager)

            # Execute
            result = await workflow.ainvoke(...)

        return result

    def _build_workflow(self, llm, tool_manager):
        workflow = StateGraph(AgentState)

        # Agent node
        workflow.add_node("agent", lambda state: self._agent_node(state, llm))

        # Tool execution node
        async def tool_node(state):
            messages = state["messages"]
            last_message = messages[-1]

            # Execute tool calls
            tool_results = []
            for tool_call in last_message.tool_calls:
                result = await tool_manager.resolve_tool_call(
                    tool_call["name"],
                    tool_call["args"]
                )
                tool_results.append(ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call["id"]
                ))

            return {"messages": tool_results}

        workflow.add_node("tools", tool_node)

        # Routing logic
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges("agent", self._should_continue)
        workflow.add_edge("tools", "agent")

        return workflow.compile()
```

## Creating Custom Providers

### Step 1: Create Helper Functions

Put core business logic in helper functions (e.g., `core/my_helpers.py`):

```python
async def get_redis_info_helper(redis_url: str, section: Optional[str] = None) -> Dict[str, Any]:
    """Get Redis INFO command output (core implementation)."""
    import redis.asyncio as redis

    client = redis.from_url(redis_url)
    try:
        if section:
            info = await client.info(section)
        else:
            info = await client.info()
        return {"status": "success", "info": info}
    finally:
        await client.close()
```

### Step 2: Create Background Task (Optional)

If you need background execution via Docket, wrap the helper in a task:

```python
from redis_sre_agent.core.tasks import sre_task
from docket import Retry
from datetime import timedelta

@sre_task
async def get_redis_info(
    redis_url: str,
    section: Optional[str] = None,
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """Get Redis INFO (background task wrapper)."""
    try:
        return await get_redis_info_helper(redis_url, section)
    except Exception as e:
        logger.error(f"Redis INFO failed (attempt {retry.attempt}): {e}")
        raise
```

### Step 3: Create Tool Provider

Implement the ToolProvider ABC:

```python
from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition
from typing import Any, Dict, List, Optional

class RedisMetricsToolProvider(ToolProvider):
    """Provides Redis metrics tools."""

    provider_name = "redis_metrics"

    def __init__(self, redis_instance: Optional[RedisInstance] = None):
        super().__init__(redis_instance)
        self.redis_url = redis_instance.url if redis_instance else None

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Define available tools."""
        return [
            ToolDefinition(
                name=self._make_tool_name("get_info"),
                description="Get Redis INFO command output for diagnostics",
                parameters={
                    "type": "object",
                    "properties": {
                        "section": {
                            "type": "string",
                            "description": "INFO section (memory, stats, replication, etc.)",
                            "enum": ["memory", "stats", "replication", "cpu", "all"]
                        }
                    }
                }
            ),
            ToolDefinition(
                name=self._make_tool_name("get_slowlog"),
                description="Get Redis SLOWLOG for performance analysis",
                parameters={
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of slowlog entries to retrieve",
                            "default": 10
                        }
                    }
                }
            )
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Route tool calls to appropriate methods."""
        # Parse operation from tool_name
        parts = tool_name.split("_")
        operation = "_".join(parts[2:])  # After provider_hash

        if operation == "get_info":
            return await self.get_info(**args)
        elif operation == "get_slowlog":
            return await self.get_slowlog(**args)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    async def get_info(self, section: Optional[str] = None) -> Dict[str, Any]:
        """Get Redis INFO (calls helper)."""
        from my_module.helpers import get_redis_info_helper
        return await get_redis_info_helper(self.redis_url, section)

    async def get_slowlog(self, count: int = 10) -> Dict[str, Any]:
        """Get Redis SLOWLOG (calls helper)."""
        from my_module.helpers import get_redis_slowlog_helper
        return await get_redis_slowlog_helper(self.redis_url, count)
```

### Step 4: Register Provider in ToolManager

Update `tools/manager.py` to load your provider:

```python
class ToolManager:
    async def __aenter__(self):
        # Load knowledge base (always enabled)
        kb_provider = KnowledgeBaseToolProvider()
        await kb_provider.__aenter__()
        self.providers.append(kb_provider)

        # Load Redis metrics if instance provided
        if self.redis_instance:
            redis_provider = RedisMetricsToolProvider(self.redis_instance)
            await redis_provider.__aenter__()
            self.providers.append(redis_provider)

        # Build routing table
        for provider in self.providers:
            schemas = provider.create_tool_schemas()
            for schema in schemas:
                self.routing_table[schema.name] = provider

        return self
```

## Helper/Task/Tool Pattern

The system uses a three-layer pattern for code organization:

```
┌─────────────────────────────────────────────────────────────┐
│                    1. Helper Functions                      │
│                  (core/knowledge_helpers.py)                │
│                                                             │
│  - Core business logic implementation                       │
│  - Pure async functions                                     │
│  - No retry logic, no LLM-specific docs                     │
│  - Single source of truth                                   │
│                                                             │
│  Example: search_knowledge_base_helper(query, category)    │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Called by both
                              │
                ┌─────────────┴─────────────┐
                │                           │
                ▼                           ▼
┌───────────────────────────┐   ┌───────────────────────────┐
│   2. Background Tasks     │   │   3. Tool Providers       │
│     (core/tasks.py)       │   │  (tools/*/provider.py)    │
│                           │   │                           │
│  - Docket task wrappers   │   │  - ToolProvider ABC impl  │
│  - Add retry logic        │   │  - LLM-friendly docstrings│
│  - Task tracking          │   │  - No retry parameter     │
│  - @sre_task decorator    │   │  - Tool schema generation │
│                           │   │                           │
│  For: Background jobs     │   │  For: LLM tool calls      │
└───────────────────────────┘   └───────────────────────────┘
```

### Example: Knowledge Base Search

**1. Helper (core/knowledge_helpers.py):**
```python
async def search_knowledge_base_helper(
    query: str,
    category: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """Core implementation of knowledge base search."""
    # Actual search logic here
    index = get_knowledge_index()
    vectorizer = get_vectorizer()
    # ... perform search ...
    return {"results": results, "count": len(results)}
```

**2. Task (core/tasks.py):**
```python
@sre_task
async def search_knowledge_base(
    query: str,
    category: Optional[str] = None,
    limit: int = 5,
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """Background task wrapper with retry logic."""
    try:
        return await search_knowledge_base_helper(query, category, limit)
    except Exception as e:
        logger.error(f"Search failed (attempt {retry.attempt}): {e}")
        raise
```

**3. Tool Provider (tools/knowledge/knowledge_base.py):**
```python
class KnowledgeBaseToolProvider(ToolProvider):
    async def search(self, query: str, category: Optional[str] = None, limit: int = 5):
        """LLM-callable tool (calls helper directly)."""
        from redis_sre_agent.core.knowledge_helpers import search_knowledge_base_helper
        return await search_knowledge_base_helper(query, category, limit)
```

## Benefits

1. **ABC-based Architecture**
   - Clear contracts with type safety
   - Default implementations reduce boilerplate
   - Easy to understand and extend

2. **Instance Scoping**
   - Tools can be scoped to specific Redis instances
   - Unique tool names prevent collisions
   - Format: `{provider}_{instance_hash}_{operation}`

3. **Per-Query Lifecycle**
   - Tools loaded dynamically based on context
   - Proper resource management via async context managers
   - No global state

4. **Centralized Routing**
   - ToolManager handles all tool execution
   - Single point for logging, monitoring, error handling
   - Easy to add middleware (auth, rate limiting, etc.)

5. **No Function Storage**
   - Tool definitions are pure schemas
   - Execution via routing, not stored closures
   - Easier to serialize, cache, and inspect

6. **Clean Separation**
   - Helpers: business logic
   - Tasks: background execution with retry
   - Tools: LLM interface with enhanced docs
   - No duplication of implementation

## Best Practices

### 1. Keep Helpers Pure
```python
# Good: Pure function, no side effects
async def get_metric_helper(url: str, metric: str) -> float:
    client = create_client(url)
    return await client.get(metric)

# Bad: Side effects, global state
async def get_metric_helper(metric: str):
    global_client.get(metric)  # Don't do this
```

### 2. Use Descriptive Tool Names
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

### 3. Provide Rich Docstrings for LLM
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

### 4. Handle Errors Gracefully
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

## Future Providers

Planned providers following this pattern:

- **Redis Direct Metrics** - INFO, SLOWLOG, CLIENT LIST
- **Redis OSS Diagnostics** - Memory analysis, key analysis
- **Prometheus** - Time-series metrics queries
- **GitHub Tickets** - Issue creation and search
- **CloudWatch Logs** - Log search and analysis
- **Redis Enterprise** - Cluster management APIs

Each will follow the same ABC-based pattern established here.

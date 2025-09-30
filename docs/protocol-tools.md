# Protocol-Based SRE Tools System

The Redis SRE Agent now supports a **Protocol-based tool system** that allows users to implement their own tools while maintaining compatibility with the agent core. This system provides extensible interfaces for metrics, logs, tickets, repositories, and traces.

## Overview

Instead of hardcoded tools, the agent now uses **Protocol interfaces** that define contracts for different SRE capabilities. Users can:

1. **Use predefined providers** for common systems (Redis CLI, Prometheus, GitHub, AWS)
2. **Create custom providers** that implement the Protocol interfaces
3. **Mix and match providers** based on their infrastructure setup
4. **Dynamically register/unregister** providers at runtime

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   LangGraph     │    │   Tool Registry  │    │   Protocol      │
│     Agent       │◄──►│                  │◄──►│  Interfaces     │
│                 │    │  - Discovery     │    │                 │
│  - Tool Calls   │    │  - Registration  │    │ - MetricsProvider│
│  - Dynamic      │    │  - Health Checks │    │ - LogsProvider   │
│    Discovery    │    │                  │    │ - TicketsProvider│
└─────────────────┘    └──────────────────┘    │ - ReposProvider  │
                                               │ - TracesProvider │
                                               └─────────────────┘
                                                        ▲
                                                        │
                                               ┌─────────────────┐
                                               │   Concrete      │
                                               │  Implementations│
                                               │                 │
                                               │ - Redis CLI     │
                                               │ - Prometheus    │
                                               │ - GitHub        │
                                               │ - AWS CloudWatch│
                                               │ - Custom Tools  │
                                               └─────────────────┘
```

## Protocol Interfaces

### 1. MetricsProvider

For instance metrics (Redis INFO, Prometheus, custom monitoring):

```python
from redis_sre_agent.tools.protocols import MetricsProvider, MetricDefinition, MetricValue

class MyMetricsProvider:
    @property
    def provider_name(self) -> str:
        return "My Custom Metrics"

    @property
    def supports_time_queries(self) -> bool:
        return True  # or False for current-value-only providers

    async def list_metrics(self) -> List[MetricDefinition]:
        # Return available metrics with descriptions
        pass

    async def get_current_value(self, metric_name: str, labels=None) -> Optional[MetricValue]:
        # Return current metric value
        pass

    async def query_time_range(self, metric_name: str, time_range, labels=None, step=None):
        # Return historical values (if supported)
        pass
```

**Included Implementations:**
- **Redis CLI**: Direct connection to Redis instances (current values only)
- **Prometheus**: Time-series metrics with full historical support

### 2. LogsProvider

For log analysis (CloudWatch, Elasticsearch, Splunk):

```python
from redis_sre_agent.tools.protocols import LogsProvider, LogEntry

class MyLogsProvider:
    async def search_logs(self, query: str, time_range, log_groups=None, level_filter=None, limit=100):
        # Search logs and return LogEntry objects
        pass

    async def get_log_groups(self) -> List[str]:
        # Return available log groups/streams
        pass
```

**Included Implementations:**
- **AWS CloudWatch Logs**: Full CloudWatch Insights support

### 3. TicketsProvider

For incident management (GitHub Issues, Jira, ServiceNow):

```python
from redis_sre_agent.tools.protocols import TicketsProvider, Ticket

class MyTicketsProvider:
    async def create_ticket(self, title: str, description: str, labels=None, assignee=None, priority=None):
        # Create and return Ticket object
        pass

    async def update_ticket(self, ticket_id: str, **updates):
        # Update existing ticket
        pass

    async def search_tickets(self, query=None, status=None, assignee=None, labels=None, limit=50):
        # Search and return list of Ticket objects
        pass
```

**Included Implementations:**
- **GitHub Issues**: Full GitHub Issues API support

### 4. ReposProvider

For code analysis (GitHub, GitLab, Bitbucket):

```python
from redis_sre_agent.tools.protocols import ReposProvider, Repository

class MyReposProvider:
    async def list_repositories(self, organization=None) -> List[Repository]:
        # Return available repositories
        pass

    async def search_code(self, query: str, repositories=None, file_extensions=None, limit=50):
        # Search code across repositories
        pass

    async def get_file_content(self, repository: str, file_path: str, branch="main") -> str:
        # Get specific file content
        pass
```

**Included Implementations:**
- **GitHub Repositories**: Full GitHub API support with code search

### 5. TracesProvider

For distributed tracing (AWS X-Ray, Jaeger, Zipkin):

```python
from redis_sre_agent.tools.protocols import TracesProvider, TraceSpan

class MyTracesProvider:
    async def search_traces(self, service_name=None, operation_name=None, time_range=None, min_duration_ms=None):
        # Search and return TraceSpan objects
        pass

    async def get_trace_details(self, trace_id: str):
        # Get detailed trace information
        pass

    async def get_service_map(self, time_range=None):
        # Get service dependency map
        pass
```

**Included Implementations:**
- **AWS X-Ray**: Full X-Ray API support

## Usage Examples

### Basic Setup

```python
from redis_sre_agent.tools.registry import get_global_registry, auto_register_default_providers

# Auto-register providers based on environment variables
config = {
    "redis_url": "redis://localhost:6379/0",
    "prometheus_url": "http://localhost:9090",
    "github_token": "ghp_...",
    "aws_region": "us-east-1"
}

auto_register_default_providers(config)

# Check what's registered
registry = get_global_registry()
print(f"Registered providers: {registry.list_providers()}")
```

### Manual Provider Registration

```python
from redis_sre_agent.tools.providers import create_redis_provider, create_github_provider
from redis_sre_agent.tools.registry import get_global_registry

registry = get_global_registry()

# Register Redis provider
redis_provider = create_redis_provider("redis://prod-redis:6379/0")
registry.register_provider("production-redis", redis_provider)

# Register GitHub provider
github_provider = create_github_provider(
    token="ghp_...",
    organization="my-org",
    default_repo="my-org/redis-app"
)
registry.register_provider("github", github_provider)
```

### Using the Tools

The agent automatically discovers and uses registered providers:

```python
# Query metrics from all available providers
result = await query_instance_metrics("used_memory")

# Query specific provider
result = await query_instance_metrics("used_memory", provider_name="production-redis")

# Search logs across all log providers
logs = await search_logs("redis connection error", time_range_hours=2)

# Create incident ticket
ticket = await create_incident_ticket(
    title="Redis Memory Usage Critical",
    description="Memory usage exceeded 90% threshold",
    labels=["redis", "production", "memory"],
    priority="high"
)
```

## Predefined Provider Combinations

### AWS Provider
Combines CloudWatch Logs + X-Ray traces:
```python
from redis_sre_agent.tools.providers import create_aws_provider

aws_provider = create_aws_provider(
    region_name="us-east-1",
    aws_access_key_id="AKIA...",
    aws_secret_access_key="..."
)
registry.register_provider("aws", aws_provider)
```

### GitHub Provider
Combines GitHub Issues + Repositories:
```python
from redis_sre_agent.tools.providers import create_github_provider

github_provider = create_github_provider(
    token="ghp_...",
    organization="my-company",
    default_repo="my-company/redis-service"
)
registry.register_provider("github", github_provider)
```

### Redis Provider
Combines Redis CLI + Prometheus metrics:
```python
from redis_sre_agent.tools.providers import create_redis_provider

redis_provider = create_redis_provider(
    redis_url="redis://localhost:6379/0",
    prometheus_url="http://localhost:9090"  # Optional
)
registry.register_provider("redis", redis_provider)
```

## Creating Custom Providers

### Simple Custom Metrics Provider

```python
from redis_sre_agent.tools.protocols import MetricsProvider, MetricDefinition, MetricValue, ToolCapability

class DatabaseMetricsProvider:
    @property
    def provider_name(self) -> str:
        return "Database Metrics"

    @property
    def supports_time_queries(self) -> bool:
        return False

    async def list_metrics(self):
        return [
            MetricDefinition("db_connections", "Active database connections", "count", "gauge"),
            MetricDefinition("db_query_time", "Average query time", "milliseconds", "gauge")
        ]

    async def get_current_value(self, metric_name: str, labels=None):
        # Connect to your database and get metrics
        if metric_name == "db_connections":
            return MetricValue(42)  # Your actual logic here
        return None

    async def query_time_range(self, metric_name: str, time_range, labels=None, step=None):
        raise NotImplementedError("Time queries not supported")

    async def health_check(self):
        return {"status": "healthy", "provider": self.provider_name}

# Wrap in SREToolProvider
class DatabaseProvider:
    @property
    def provider_name(self) -> str:
        return "Database SRE Provider"

    @property
    def capabilities(self):
        return [ToolCapability.METRICS]

    async def get_metrics_provider(self):
        return DatabaseMetricsProvider()

    # Other providers return None
    async def get_logs_provider(self): return None
    async def get_tickets_provider(self): return None
    async def get_repos_provider(self): return None
    async def get_traces_provider(self): return None
    async def initialize(self, config): pass
    async def health_check(self): return {"status": "healthy"}

# Register it
registry.register_provider("database", DatabaseProvider())
```

## Agent Integration

The agent automatically uses the Protocol system. Update your agent initialization:

```python
from redis_sre_agent.tools.registry import auto_register_default_providers
from redis_sre_agent.tools.protocol_agent_tools import get_protocol_based_tools, PROTOCOL_TOOL_FUNCTIONS

# Register providers
auto_register_default_providers(config)

# Agent uses protocol-based tools
tool_definitions = get_protocol_based_tools()
tool_functions = PROTOCOL_TOOL_FUNCTIONS
```

## Benefits

1. **Extensibility**: Add new monitoring systems without changing agent code
2. **Flexibility**: Mix providers based on your infrastructure
3. **Maintainability**: Clear separation between agent logic and external integrations
4. **Testability**: Easy to mock providers for testing
5. **Discoverability**: Agent automatically finds and uses available capabilities

## Migration from Hardcoded Tools

The old hardcoded tools (`analyze_system_metrics`, `check_service_health`, etc.) are replaced by:

- `query_instance_metrics` - Queries any registered metrics provider
- `list_available_metrics` - Discovers available metrics across providers
- `search_logs` - Searches across any registered log provider
- `create_incident_ticket` - Creates tickets in any registered ticket system
- `search_related_repositories` - Searches code across registered repo providers
- `get_provider_status` - Shows health and status of all providers

The agent maintains the same conversational interface while gaining much more flexibility in backend integrations.

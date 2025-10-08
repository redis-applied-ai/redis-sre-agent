"""Protocol interfaces for extensible SRE tools.

This module defines Protocol interfaces that allow users to implement their own
tools while maintaining compatibility with the agent core. The agent can discover
and register any tool that implements these protocols.
"""

from abc import abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Union


class ToolCapability(Enum):
    """Capabilities that tools can provide."""

    METRICS = "metrics"
    LOGS = "logs"
    TICKETS = "tickets"
    REPOS = "repos"
    TRACES = "traces"
    DIAGNOSTICS = "diagnostics"  # For deep instance diagnostics (Redis INFO, key sampling, etc.)


class MetricValue:
    """Represents a metric value with timestamp."""

    def __init__(
        self,
        value: Union[int, float],
        timestamp: Optional[datetime] = None,
        labels: Optional[Dict[str, str]] = None,
    ):
        self.value = value
        self.timestamp = timestamp or datetime.now()
        self.labels = labels or {}


class MetricDefinition:
    """Defines a metric with metadata."""

    def __init__(self, name: str, description: str, unit: str, metric_type: str = "gauge"):
        self.name = name
        self.description = description
        self.unit = unit
        self.metric_type = metric_type  # gauge, counter, histogram, etc.


class TimeRange:
    """Represents a time range for queries."""

    def __init__(self, start: datetime, end: datetime):
        self.start = start
        self.end = end


class MetricsProvider(Protocol):
    """Protocol for instance metrics providers.

    Implementations can include:
    - Redis CLI (INFO commands, limited to current values)
    - Redis Cloud Management API (full time-series support)
    - Prometheus (full time-series support)
    - Custom monitoring systems
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the metrics provider."""
        ...

    @property
    @abstractmethod
    def supports_time_queries(self) -> bool:
        """Whether this provider supports time-bound queries."""
        ...

    @abstractmethod
    async def list_metrics(self) -> List[MetricDefinition]:
        """List all available metrics with descriptions.

        Returns:
            List of metric definitions with names, descriptions, and units
        """
        ...

    @abstractmethod
    async def get_current_value(
        self, metric_name: str, labels: Optional[Dict[str, str]] = None
    ) -> Optional[MetricValue]:
        """Get the current value of a metric.

        Args:
            metric_name: Name of the metric to query
            labels: Optional label filters

        Returns:
            Current metric value or None if not found
        """
        ...

    @abstractmethod
    async def query_time_range(
        self,
        metric_name: str,
        time_range: TimeRange,
        labels: Optional[Dict[str, str]] = None,
        step: Optional[str] = None,
    ) -> List[MetricValue]:
        """Query metric values over a time range.

        Args:
            metric_name: Name of the metric to query
            time_range: Time range for the query
            labels: Optional label filters
            step: Optional step size (e.g., "1m", "5m")

        Returns:
            List of metric values over time

        Raises:
            NotImplementedError: If provider doesn't support time queries
        """
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check if the metrics provider is healthy and accessible.

        Returns:
            Health status information
        """
        ...


class LogEntry:
    """Represents a log entry."""

    def __init__(
        self,
        timestamp: datetime,
        level: str,
        message: str,
        source: str,
        labels: Optional[Dict[str, str]] = None,
    ):
        self.timestamp = timestamp
        self.level = level
        self.message = message
        self.source = source
        self.labels = labels or {}


class LogsProvider(Protocol):
    """Protocol for logs providers.

    Implementations can include:
    - AWS CloudWatch Logs
    - Elasticsearch/OpenSearch
    - Splunk
    - Local file systems
    - Kubernetes logs
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the logs provider."""
        ...

    @abstractmethod
    async def search_logs(
        self,
        query: str,
        time_range: TimeRange,
        log_groups: Optional[List[str]] = None,
        level_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[LogEntry]:
        """Search logs with filters.

        Args:
            query: Search query (syntax depends on provider)
            time_range: Time range for the search
            log_groups: Optional list of log groups/streams to search
            level_filter: Optional log level filter (ERROR, WARN, INFO, etc.)
            limit: Maximum number of results

        Returns:
            List of matching log entries
        """
        ...

    @abstractmethod
    async def get_log_groups(self) -> List[str]:
        """Get available log groups/streams.

        Returns:
            List of available log group names
        """
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check if the logs provider is healthy and accessible."""
        ...


class Ticket:
    """Represents a ticket/issue."""

    def __init__(
        self,
        id: str,
        title: str,
        description: str,
        status: str,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ):
        self.id = id
        self.title = title
        self.description = description
        self.status = status
        self.assignee = assignee
        self.labels = labels or []


class TicketsProvider(Protocol):
    """Protocol for tickets/issues providers.

    Implementations can include:
    - GitHub Issues
    - Jira
    - Linear
    - ServiceNow
    - PagerDuty incidents
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the tickets provider."""
        ...

    @abstractmethod
    async def create_ticket(
        self,
        title: str,
        description: str,
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> Ticket:
        """Create a new ticket.

        Args:
            title: Ticket title
            description: Ticket description
            labels: Optional labels/tags
            assignee: Optional assignee
            priority: Optional priority level

        Returns:
            Created ticket information
        """
        ...

    @abstractmethod
    async def update_ticket(self, ticket_id: str, **updates) -> Ticket:
        """Update an existing ticket.

        Args:
            ticket_id: ID of the ticket to update
            **updates: Fields to update (status, assignee, etc.)

        Returns:
            Updated ticket information
        """
        ...

    @abstractmethod
    async def search_tickets(
        self,
        query: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Ticket]:
        """Search for tickets with filters.

        Args:
            query: Text search query
            status: Status filter
            assignee: Assignee filter
            labels: Labels filter
            limit: Maximum number of results

        Returns:
            List of matching tickets
        """
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check if the tickets provider is healthy and accessible."""
        ...


class Repository:
    """Represents a code repository."""

    def __init__(
        self,
        name: str,
        url: str,
        default_branch: str = "main",
        languages: Optional[List[str]] = None,
    ):
        self.name = name
        self.url = url
        self.default_branch = default_branch
        self.languages = languages or []


class ReposProvider(Protocol):
    """Protocol for repository providers.

    Implementations can include:
    - GitHub
    - GitLab
    - Bitbucket
    - Azure DevOps
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the repository provider."""
        ...

    @abstractmethod
    async def list_repositories(self, organization: Optional[str] = None) -> List[Repository]:
        """List available repositories.

        Args:
            organization: Optional organization filter

        Returns:
            List of repositories
        """
        ...

    @abstractmethod
    async def search_code(
        self,
        query: str,
        repositories: Optional[List[str]] = None,
        file_extensions: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Search code across repositories.

        Args:
            query: Code search query
            repositories: Optional list of repository names to search
            file_extensions: Optional file extension filters
            limit: Maximum number of results

        Returns:
            List of code search results with file paths and snippets
        """
        ...

    @abstractmethod
    async def get_file_content(self, repository: str, file_path: str, branch: str = "main") -> str:
        """Get content of a specific file.

        Args:
            repository: Repository name
            file_path: Path to the file
            branch: Branch name

        Returns:
            File content as string
        """
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check if the repository provider is healthy and accessible."""
        ...


class TraceSpan:
    """Represents a trace span."""

    def __init__(
        self,
        trace_id: str,
        span_id: str,
        operation_name: str,
        start_time: datetime,
        duration_ms: float,
        tags: Optional[Dict[str, str]] = None,
    ):
        self.trace_id = trace_id
        self.span_id = span_id
        self.operation_name = operation_name
        self.start_time = start_time
        self.duration_ms = duration_ms
        self.tags = tags or {}


class TracesProvider(Protocol):
    """Protocol for distributed tracing providers.

    Implementations can include:
    - AWS X-Ray
    - Jaeger
    - Zipkin
    - Datadog APM
    - New Relic
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the traces provider."""
        ...

    @abstractmethod
    async def search_traces(
        self,
        service_name: Optional[str] = None,
        operation_name: Optional[str] = None,
        time_range: Optional[TimeRange] = None,
        min_duration_ms: Optional[float] = None,
        tags: Optional[Dict[str, str]] = None,
        limit: int = 100,
    ) -> List[TraceSpan]:
        """Search for traces with filters.

        Args:
            service_name: Optional service name filter
            operation_name: Optional operation name filter
            time_range: Optional time range filter
            min_duration_ms: Optional minimum duration filter
            tags: Optional tag filters
            limit: Maximum number of results

        Returns:
            List of matching trace spans
        """
        ...

    @abstractmethod
    async def get_trace_details(self, trace_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific trace.

        Args:
            trace_id: ID of the trace to retrieve

        Returns:
            Detailed trace information including all spans
        """
        ...

    @abstractmethod
    async def get_service_map(self, time_range: Optional[TimeRange] = None) -> Dict[str, Any]:
        """Get service dependency map.

        Args:
            time_range: Optional time range for the map

        Returns:
            Service dependency information
        """
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check if the traces provider is healthy and accessible."""
        ...


class SREToolProvider(Protocol):
    """Base protocol for all SRE tool providers.

    This is the main interface that the agent uses to discover and interact
    with tool providers. Each provider can implement multiple capabilities.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the provider."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> List[ToolCapability]:
        """List of capabilities this provider supports."""
        ...

    @abstractmethod
    async def get_metrics_provider(self) -> Optional[MetricsProvider]:
        """Get the metrics provider if supported."""
        ...

    @abstractmethod
    async def get_logs_provider(self) -> Optional[LogsProvider]:
        """Get the logs provider if supported."""
        ...

    @abstractmethod
    async def get_tickets_provider(self) -> Optional[TicketsProvider]:
        """Get the tickets provider if supported."""
        ...

    @abstractmethod
    async def get_repos_provider(self) -> Optional[ReposProvider]:
        """Get the repository provider if supported."""
        ...

    @abstractmethod
    async def get_traces_provider(self) -> Optional[TracesProvider]:
        """Get the traces provider if supported."""
        ...

    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize the provider with configuration."""
        ...

    @abstractmethod
    async def get_diagnostics_provider(self) -> Optional["DiagnosticsProvider"]:
        """Get the diagnostics provider if supported."""
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Overall health check for the provider."""
        ...


class DiagnosticsProvider(Protocol):
    """Protocol for deep instance diagnostics providers.

    This protocol is for tools that provide deep diagnostic capabilities
    beyond simple metrics - things like Redis INFO sections, key sampling,
    configuration analysis, slow query logs, etc.

    Implementations can include:
    - Redis direct connection (INFO, SCAN, SLOWLOG, CONFIG GET)
    - SSH-based diagnostics (filesystem, logs, process info)
    - Container exec diagnostics (docker exec, kubectl exec)
    - Cloud provider APIs (AWS RDS diagnostics, Azure Redis insights)
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the diagnostics provider."""
        ...

    @abstractmethod
    async def get_diagnostics(
        self,
        sections: Optional[List[str]] = None,
        include_raw_data: bool = True,
    ) -> Dict[str, Any]:
        """Get comprehensive diagnostic information.

        Args:
            sections: Optional list of diagnostic sections to capture.
                     Common sections: memory, performance, clients, slowlog,
                     configuration, keyspace, replication, persistence, cpu
            include_raw_data: Whether to include raw diagnostic output

        Returns:
            Dictionary with diagnostic data organized by section
        """
        ...

    @abstractmethod
    async def sample_keys(
        self,
        pattern: str = "*",
        count: int = 100,
        database: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Sample keys from the instance.

        Args:
            pattern: Key pattern to match (e.g., 'user:*', 'session:*')
            count: Maximum number of keys to sample
            database: Optional database number (for multi-database systems)

        Returns:
            Dictionary with sampled keys and pattern analysis
        """
        ...

    @abstractmethod
    async def get_configuration(self) -> Dict[str, Any]:
        """Get instance configuration.

        Returns:
            Dictionary with configuration parameters
        """
        ...

    @abstractmethod
    async def get_slow_queries(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get slow query log entries.

        Args:
            limit: Maximum number of slow queries to return

        Returns:
            List of slow query entries with timing and command info
        """
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check if the diagnostics provider is healthy and accessible."""
        ...

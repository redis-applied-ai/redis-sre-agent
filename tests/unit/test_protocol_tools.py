"""Tests for Protocol-based SRE tools system."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from redis_sre_agent.tools.dynamic_tools import (
    create_incident_ticket,
    list_available_metrics,
    query_instance_metrics,
    search_logs,
    search_related_repositories,
)
from redis_sre_agent.tools.protocols import (
    LogEntry,
    MetricDefinition,
    MetricValue,
    Repository,
    Ticket,
    ToolCapability,
)
from redis_sre_agent.tools.registry import SREToolRegistry


class MockMetricsProvider:
    """Mock metrics provider for testing."""

    def __init__(self, name: str = "Mock Metrics", supports_time: bool = True):
        self._name = name
        self._supports_time = supports_time

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def supports_time_queries(self) -> bool:
        return self._supports_time

    async def list_metrics(self):
        return [
            MetricDefinition("test_metric", "Test metric", "count", "gauge"),
            MetricDefinition("memory_usage", "Memory usage", "bytes", "gauge"),
        ]

    async def get_current_value(self, metric_name: str, labels=None):
        if metric_name == "test_metric":
            return MetricValue(42, labels=labels)
        elif metric_name == "memory_usage":
            return MetricValue(1024, labels=labels)
        return None

    async def query_time_range(self, metric_name: str, time_range, labels=None, step=None):
        if not self._supports_time:
            raise NotImplementedError("Time queries not supported")

        # Return mock time series data
        values = []
        start_time = time_range.start
        for i in range(5):
            timestamp = start_time + timedelta(minutes=i * 15)
            values.append(MetricValue(42 + i, timestamp, labels))
        return values

    async def health_check(self):
        return {"status": "healthy", "provider": self.provider_name}


class MockLogsProvider:
    """Mock logs provider for testing."""

    @property
    def provider_name(self) -> str:
        return "Mock Logs"

    async def search_logs(self, query: str, time_range, log_groups=None, level_filter=None, limit=100):
        # Return mock log entries
        entries = []
        for i in range(min(3, limit)):
            entry = LogEntry(
                timestamp=datetime.now() - timedelta(minutes=i * 10),
                level="INFO",
                message=f"Mock log entry {i} matching '{query}'",
                source=f"mock-service-{i}",
                labels={"service": "mock", "environment": "test"}
            )
            entries.append(entry)
        return entries

    async def get_log_groups(self):
        return ["mock-service-1", "mock-service-2", "mock-app"]

    async def health_check(self):
        return {"status": "healthy", "provider": self.provider_name}


class MockTicketsProvider:
    """Mock tickets provider for testing."""

    @property
    def provider_name(self) -> str:
        return "Mock Tickets"

    async def create_ticket(self, title: str, description: str, labels=None, assignee=None, priority=None):
        return Ticket(
            id="MOCK-123",
            title=title,
            description=description,
            status="open",
            assignee=assignee,
            labels=labels or []
        )

    async def update_ticket(self, ticket_id: str, **updates):
        return Ticket(
            id=ticket_id,
            title=updates.get("title", "Updated ticket"),
            description=updates.get("description", "Updated description"),
            status=updates.get("status", "open"),
            assignee=updates.get("assignee"),
            labels=updates.get("labels", [])
        )

    async def search_tickets(self, query=None, status=None, assignee=None, labels=None, limit=50):
        return [
            Ticket("MOCK-1", "Test ticket 1", "Description 1", "open", labels=["test"]),
            Ticket("MOCK-2", "Test ticket 2", "Description 2", "closed", labels=["test"])
        ]

    async def health_check(self):
        return {"status": "healthy", "provider": self.provider_name}


class MockReposProvider:
    """Mock repository provider for testing."""

    @property
    def provider_name(self) -> str:
        return "Mock Repos"

    async def list_repositories(self, organization=None):
        return [
            Repository("test/repo1", "https://github.com/test/repo1", "main", ["Python"]),
            Repository("test/repo2", "https://github.com/test/repo2", "main", ["JavaScript"])
        ]

    async def search_code(self, query: str, repositories=None, file_extensions=None, limit=50):
        return [
            {
                "repository": "test/repo1",
                "file_path": "src/main.py",
                "file_name": "main.py",
                "url": "https://github.com/test/repo1/blob/main/src/main.py",
                "score": 0.95,
                "snippet": f"Code snippet containing '{query}'"
            }
        ]

    async def get_file_content(self, repository: str, file_path: str, branch="main"):
        return f"# Content of {file_path} in {repository}\nprint('Hello, world!')"

    async def health_check(self):
        return {"status": "healthy", "provider": self.provider_name}


class MockSREProvider:
    """Mock comprehensive SRE provider for testing."""

    def __init__(self, capabilities=None):
        self._capabilities = capabilities or [ToolCapability.METRICS, ToolCapability.LOGS]
        self._metrics_provider = MockMetricsProvider()
        self._logs_provider = MockLogsProvider()
        self._tickets_provider = MockTicketsProvider()
        self._repos_provider = MockReposProvider()

    @property
    def provider_name(self) -> str:
        return "Mock SRE Provider"

    @property
    def capabilities(self):
        return self._capabilities

    async def get_metrics_provider(self):
        return self._metrics_provider if ToolCapability.METRICS in self._capabilities else None

    async def get_logs_provider(self):
        return self._logs_provider if ToolCapability.LOGS in self._capabilities else None

    async def get_tickets_provider(self):
        return self._tickets_provider if ToolCapability.TICKETS in self._capabilities else None

    async def get_repos_provider(self):
        return self._repos_provider if ToolCapability.REPOS in self._capabilities else None

    async def get_traces_provider(self):
        return None  # Not implemented in mock

    async def initialize(self, config):
        pass

    async def health_check(self):
        return {"status": "healthy", "provider": self.provider_name}


class TestSREToolRegistry:
    """Test the SRE tool registry."""

    def test_registry_initialization(self):
        """Test registry initializes correctly."""
        registry = SREToolRegistry()

        assert len(registry.list_providers()) == 0
        assert len(registry.get_providers_by_capability(ToolCapability.METRICS)) == 0

    def test_provider_registration(self):
        """Test provider registration and discovery."""
        registry = SREToolRegistry()
        provider = MockSREProvider()

        registry.register_provider("test", provider)

        assert "test" in registry.list_providers()
        assert len(registry.get_providers_by_capability(ToolCapability.METRICS)) == 1
        assert len(registry.get_providers_by_capability(ToolCapability.LOGS)) == 1
        assert len(registry.get_providers_by_capability(ToolCapability.TICKETS)) == 0

    def test_provider_unregistration(self):
        """Test provider unregistration."""
        registry = SREToolRegistry()
        provider = MockSREProvider()

        registry.register_provider("test", provider)
        assert "test" in registry.list_providers()

        result = registry.unregister_provider("test")
        assert result is True
        assert "test" not in registry.list_providers()

        # Test unregistering non-existent provider
        result = registry.unregister_provider("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_providers_by_capability(self):
        """Test getting providers by capability."""
        registry = SREToolRegistry()

        # Register providers with different capabilities
        metrics_provider = MockSREProvider([ToolCapability.METRICS])
        logs_provider = MockSREProvider([ToolCapability.LOGS])
        full_provider = MockSREProvider([ToolCapability.METRICS, ToolCapability.LOGS, ToolCapability.TICKETS])

        registry.register_provider("metrics", metrics_provider)
        registry.register_provider("logs", logs_provider)
        registry.register_provider("full", full_provider)

        # Test capability-based discovery
        metrics_providers = await registry.get_metrics_providers()
        logs_providers = await registry.get_logs_providers()
        tickets_providers = await registry.get_tickets_providers()

        assert len(metrics_providers) == 2  # metrics + full
        assert len(logs_providers) == 2     # logs + full
        assert len(tickets_providers) == 1  # full only

    @pytest.mark.asyncio
    async def test_health_check_all(self):
        """Test health checking all providers."""
        registry = SREToolRegistry()
        provider = MockSREProvider()

        registry.register_provider("test", provider)

        health_results = await registry.health_check_all()

        assert health_results["overall_status"] == "healthy"
        assert "test" in health_results["providers"]
        assert health_results["providers"]["test"]["status"] == "healthy"

    def test_registry_status(self):
        """Test getting registry status."""
        registry = SREToolRegistry()
        provider = MockSREProvider([ToolCapability.METRICS, ToolCapability.LOGS])

        registry.register_provider("test", provider)

        status = registry.get_registry_status()

        assert status["total_providers"] == 1
        assert "test" in status["providers"]
        assert status["capability_counts"]["metrics"] == 1
        assert status["capability_counts"]["logs"] == 1
        assert status["capability_counts"]["tickets"] == 0


class TestDynamicTools:
    """Test the dynamic SRE tools."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock registry with test providers."""
        registry = SREToolRegistry()
        provider = MockSREProvider([ToolCapability.METRICS, ToolCapability.LOGS, ToolCapability.TICKETS, ToolCapability.REPOS])
        registry.register_provider("test", provider)
        return registry

    @pytest.mark.asyncio
    async def test_query_instance_metrics_current_value(self, mock_registry):
        """Test querying current metric values."""
        with patch("redis_sre_agent.tools.dynamic_tools.get_global_registry", return_value=mock_registry):
            result = await query_instance_metrics("test_metric")

        assert "error" not in result
        assert result["metric_name"] == "test_metric"
        assert result["providers_queried"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["current_value"] == 42

    @pytest.mark.asyncio
    async def test_query_instance_metrics_time_range(self, mock_registry):
        """Test querying metric time ranges."""
        with patch("redis_sre_agent.tools.dynamic_tools.get_global_registry", return_value=mock_registry):
            result = await query_instance_metrics("test_metric", time_range_hours=1.0)

        assert "error" not in result
        assert result["metric_name"] == "test_metric"
        assert result["results"][0]["values_count"] == 5

    @pytest.mark.asyncio
    async def test_list_available_metrics(self, mock_registry):
        """Test listing available metrics."""
        with patch("redis_sre_agent.tools.dynamic_tools.get_global_registry", return_value=mock_registry):
            result = await list_available_metrics()

        assert "error" not in result
        assert result["providers_queried"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["metrics_count"] == 2

    @pytest.mark.asyncio
    async def test_search_logs(self, mock_registry):
        """Test searching logs."""
        with patch("redis_sre_agent.tools.dynamic_tools.get_global_registry", return_value=mock_registry):
            result = await search_logs("error", time_range_hours=1.0)

        assert "error" not in result
        assert result["query"] == "error"
        assert result["providers_queried"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["entries_found"] == 3

    @pytest.mark.asyncio
    async def test_create_incident_ticket(self, mock_registry):
        """Test creating incident tickets."""
        with patch("redis_sre_agent.tools.dynamic_tools.get_global_registry", return_value=mock_registry):
            result = await create_incident_ticket(
                "Test Incident",
                "Test description",
                labels=["test", "incident"],
                priority="high"
            )

        assert "error" not in result
        assert result["ticket_created"] is True
        assert result["ticket"]["id"] == "MOCK-123"
        assert result["ticket"]["title"] == "Test Incident"

    @pytest.mark.asyncio
    async def test_search_related_repositories(self, mock_registry):
        """Test searching related repositories."""
        with patch("redis_sre_agent.tools.dynamic_tools.get_global_registry", return_value=mock_registry):
            result = await search_related_repositories("redis")

        assert "error" not in result
        assert result["query"] == "redis"
        assert result["providers_queried"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["code_results_found"] == 1

    @pytest.mark.asyncio
    async def test_no_providers_available(self):
        """Test behavior when no providers are available."""
        empty_registry = SREToolRegistry()

        with patch("redis_sre_agent.tools.dynamic_tools.get_global_registry", return_value=empty_registry):
            result = await query_instance_metrics("test_metric")

        assert "error" in result
        assert "No metrics providers available" in result["error"]

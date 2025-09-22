"""Tests for dynamic SRE tools that use the Protocol-based provider system."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

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
    Ticket,
)


@pytest.fixture
def mock_registry():
    """Mock registry with test providers."""
    with patch("redis_sre_agent.tools.dynamic_tools.get_global_registry") as mock_get_registry:
        mock_registry = AsyncMock()
        # Set up async methods
        mock_registry.get_metrics_providers = AsyncMock()
        mock_registry.get_logs_providers = AsyncMock()
        mock_registry.get_tickets_providers = AsyncMock()
        mock_registry.get_repos_providers = AsyncMock()
        # Set up sync methods
        mock_registry.get_providers_by_capability = MagicMock()
        mock_registry.get_provider = MagicMock()
        mock_get_registry.return_value = mock_registry
        yield mock_registry


@pytest.fixture
def mock_metrics_provider():
    """Mock metrics provider."""
    provider = AsyncMock()
    provider.provider_name = "Test Metrics Provider"
    provider.supports_time_queries = True
    # Make sure async methods return proper values
    provider.get_current_value = AsyncMock()
    provider.query_time_range = AsyncMock()
    provider.list_available_metrics = AsyncMock()
    return provider


@pytest.fixture
def mock_logs_provider():
    """Mock logs provider."""
    provider = AsyncMock()
    provider.provider_name = "Test Logs Provider"
    # Make sure async methods return proper values
    provider.search_logs = AsyncMock()
    return provider


@pytest.fixture
def mock_tickets_provider():
    """Mock tickets provider."""
    provider = AsyncMock()
    provider.provider_name = "Test Tickets Provider"
    # Make sure async methods return proper values
    provider.create_ticket = AsyncMock()
    return provider


@pytest.fixture
def mock_repos_provider():
    """Mock repositories provider."""
    provider = AsyncMock()
    provider.provider_name = "Test Repos Provider"
    # Make sure async methods return proper values
    provider.search_code = AsyncMock()
    return provider


class TestQueryInstanceMetrics:
    """Test query_instance_metrics function."""

    @pytest.mark.asyncio
    async def test_query_current_value_success(self, mock_registry, mock_metrics_provider):
        """Test successful current value query."""
        # Setup
        mock_registry.get_metrics_providers.return_value = [mock_metrics_provider]
        mock_metrics_provider.get_current_value.return_value = MetricValue(42.0)

        # Execute
        result = await query_instance_metrics("used_memory")

        # Verify
        assert result["metric_name"] == "used_memory"
        assert result["providers_queried"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["provider"] == "Test Metrics Provider"
        assert result["results"][0]["current_value"] == 42.0

        mock_registry.get_metrics_providers.assert_called_once()
        mock_metrics_provider.get_current_value.assert_called_once_with("used_memory", None)

    @pytest.mark.asyncio
    async def test_query_time_range_success(self, mock_registry, mock_metrics_provider):
        """Test successful time range query."""
        # Setup
        mock_registry.get_metrics_providers.return_value = [mock_metrics_provider]
        mock_metrics_provider.supports_time_queries = True
        mock_metrics_provider.query_time_range.return_value = [
            MetricValue(40.0, datetime.now()),
            MetricValue(42.0, datetime.now()),
        ]

        # Execute
        result = await query_instance_metrics("used_memory", time_range_hours=1.0)

        # Verify
        assert result["metric_name"] == "used_memory"
        assert result["providers_queried"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["time_range_hours"] == 1.0
        assert result["results"][0]["values_count"] == 2

        mock_metrics_provider.query_time_range.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_no_providers(self, mock_registry):
        """Test query when no providers are available."""
        # Setup
        mock_registry.get_metrics_providers.return_value = []

        # Execute
        result = await query_instance_metrics("used_memory")

        # Verify
        assert "error" in result
        assert "No metrics providers available" in result["error"]

    @pytest.mark.asyncio
    async def test_query_provider_error(self, mock_registry, mock_metrics_provider):
        """Test query when provider raises an error."""
        # Setup
        mock_registry.get_metrics_providers.return_value = [mock_metrics_provider]
        mock_metrics_provider.get_current_value.side_effect = Exception("Provider error")

        # Execute
        result = await query_instance_metrics("used_memory")

        # Verify
        assert result["providers_queried"] == 1
        assert "error" in result["results"][0]
        assert "Provider error" in result["results"][0]["error"]


class TestListAvailableMetrics:
    """Test list_available_metrics function."""

    @pytest.mark.asyncio
    async def test_list_all_metrics_success(self, mock_registry, mock_metrics_provider):
        """Test successful listing of all metrics."""
        # Setup
        mock_registry.get_metrics_providers.return_value = [mock_metrics_provider]
        mock_metrics_provider.list_metrics.return_value = [
            MetricDefinition("used_memory", "Memory usage", "bytes", "gauge"),
            MetricDefinition("connected_clients", "Client connections", "count", "gauge"),
        ]

        # Execute
        result = await list_available_metrics()

        # Verify
        assert result["providers_queried"] == 1
        assert len(result["results"]) == 1
        assert len(result["results"][0]["metrics"]) == 2
        assert result["results"][0]["metrics"][0]["name"] == "used_memory"
        assert result["results"][0]["metrics"][1]["name"] == "connected_clients"

    @pytest.mark.asyncio
    async def test_list_specific_provider_metrics(self, mock_registry, mock_metrics_provider):
        """Test listing metrics from a specific provider."""
        # Setup
        mock_provider_instance = AsyncMock()
        mock_provider_instance.get_metrics_provider.return_value = mock_metrics_provider
        mock_registry.get_provider.return_value = mock_provider_instance
        mock_metrics_provider.list_metrics.return_value = [
            MetricDefinition("redis_memory", "Redis memory", "bytes", "gauge"),
        ]

        # Execute
        result = await list_available_metrics(provider_name="redis")

        # Verify
        assert result["providers_queried"] == 1
        assert len(result["results"]) == 1
        assert len(result["results"][0]["metrics"]) == 1
        assert result["results"][0]["metrics"][0]["name"] == "redis_memory"

        mock_registry.get_provider.assert_called_once_with("redis")


class TestSearchLogs:
    """Test search_logs function."""

    @pytest.mark.asyncio
    async def test_search_logs_success(self, mock_registry, mock_logs_provider):
        """Test successful log search."""
        # Setup
        mock_registry.get_logs_providers.return_value = [mock_logs_provider]
        mock_logs_provider.search_logs.return_value = [
            LogEntry(
                timestamp=datetime.now(),
                level="ERROR",
                message="Connection failed",
                source="redis-server",
                labels={"service": "redis"},
            )
        ]

        # Execute
        result = await search_logs("connection failed")

        # Verify
        assert result["query"] == "connection failed"
        assert result["providers_queried"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["entries_found"] == 1
        assert result["results"][0]["entries"][0]["level"] == "ERROR"
        assert result["results"][0]["entries"][0]["message"] == "Connection failed"

    @pytest.mark.asyncio
    async def test_search_logs_with_filters(self, mock_registry, mock_logs_provider):
        """Test log search with filters."""
        # Setup
        mock_registry.get_logs_providers.return_value = [mock_logs_provider]
        mock_logs_provider.search_logs.return_value = []

        # Execute
        await search_logs(
            "error", time_range_hours=2.0, log_groups=["app-logs"], level_filter="ERROR", limit=50
        )

        # Verify
        mock_logs_provider.search_logs.assert_called_once()
        call_args = mock_logs_provider.search_logs.call_args
        assert call_args[1]["query"] == "error"
        # Check that time range is approximately 2 hours
        time_range = call_args[1]["time_range"]
        time_diff = time_range.end - time_range.start
        assert abs(time_diff.total_seconds() - 2 * 3600) < 60  # Within 1 minute tolerance
        assert call_args[1]["log_groups"] == ["app-logs"]
        assert call_args[1]["level_filter"] == "ERROR"
        assert call_args[1]["limit"] == 50


class TestCreateIncidentTicket:
    """Test create_incident_ticket function."""

    @pytest.mark.asyncio
    async def test_create_ticket_success(self, mock_registry, mock_tickets_provider):
        """Test successful ticket creation."""
        # Setup
        mock_registry.get_tickets_providers.return_value = [mock_tickets_provider]
        mock_tickets_provider.create_ticket.return_value = Ticket(
            id="TICKET-123",
            title="Redis Memory Issue",
            description="Memory usage critical",
            status="open",
            labels=["redis", "memory"],
        )

        # Execute
        result = await create_incident_ticket(
            title="Redis Memory Issue",
            description="Memory usage critical",
            labels=["redis", "memory"],
            priority="high",
        )

        # Verify
        assert result["provider"] == "Test Tickets Provider"
        assert result["ticket_created"] is True
        assert result["ticket"]["id"] == "TICKET-123"
        assert result["ticket"]["title"] == "Redis Memory Issue"
        assert result["ticket"]["labels"] == ["redis", "memory"]

    @pytest.mark.asyncio
    async def test_create_ticket_no_providers(self, mock_registry):
        """Test ticket creation when no providers are available."""
        # Setup
        mock_registry.get_tickets_providers.return_value = []

        # Execute
        result = await create_incident_ticket("Test", "Description")

        # Verify
        assert "error" in result
        assert "No tickets providers available" in result["error"]


class TestSearchRelatedRepositories:
    """Test search_related_repositories function."""

    @pytest.mark.asyncio
    async def test_search_repos_success(self, mock_registry, mock_repos_provider):
        """Test successful repository search."""
        # Setup
        mock_registry.get_repos_providers.return_value = [mock_repos_provider]
        mock_repos_provider.search_code.return_value = [
            {
                "file_path": "src/cache.py",
                "repository": "myapp",
                "content_snippet": "redis.Redis(host='localhost')",
                "line_number": 42,
            }
        ]

        # Execute
        result = await search_related_repositories("redis")

        # Verify
        assert result["query"] == "redis"
        assert result["providers_queried"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["code_results_found"] == 1
        assert result["results"][0]["code_results"][0]["file_path"] == "src/cache.py"

    @pytest.mark.asyncio
    async def test_search_repos_with_filters(self, mock_registry, mock_repos_provider):
        """Test repository search with file extension filters."""
        # Setup
        mock_registry.get_repos_providers.return_value = [mock_repos_provider]
        mock_repos_provider.search_code.return_value = []

        # Execute
        await search_related_repositories("redis", file_extensions=["py", "js"], limit=10)

        # Verify
        mock_repos_provider.search_code.assert_called_once()
        call_args = mock_repos_provider.search_code.call_args
        assert call_args[1]["query"] == "redis"
        assert call_args[1]["file_extensions"] == ["py", "js"]
        assert call_args[1]["limit"] == 10

"""Unit tests for Docket task system and SRE tasks."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from docket import Retry

from redis_sre_agent.core.tasks import (
    SRE_TASK_COLLECTION,
    analyze_system_metrics,
    check_service_health,
    ingest_sre_document,
    register_sre_tasks,
    search_runbook_knowledge,
    test_task_system,
)


class TestSRETaskCollection:
    """Test SRE task registry."""

    def test_sre_task_collection_populated(self):
        """Test that SRE task collection contains expected tasks."""
        assert len(SRE_TASK_COLLECTION) == 5

        task_names = [task.__name__ for task in SRE_TASK_COLLECTION]
        expected_tasks = [
            "analyze_system_metrics",
            "search_runbook_knowledge",
            "check_service_health",
            "ingest_sre_document",
            "process_agent_turn",
        ]

        for expected_task in expected_tasks:
            assert expected_task in task_names


class TestAnalyzeSystemMetrics:
    """Test analyze_system_metrics task."""

    @pytest.mark.asyncio
    async def test_analyze_metrics_success(self, mock_redis_client):
        """Test successful metrics analysis."""
        mock_redis_client.hset.return_value = 1
        mock_redis_client.expire.return_value = True

        with patch("redis_sre_agent.core.tasks.get_redis_client", return_value=mock_redis_client):
            result = await analyze_system_metrics(
                metric_query="cpu_usage", time_range="1h", threshold=80.0
            )

        assert result["metric_query"] == "cpu_usage"
        assert result["time_range"] == "1h"
        assert result["status"] == "analyzed"
        assert "task_id" in result
        assert "timestamp" in result
        assert "findings" in result

        # Verify Redis operations
        mock_redis_client.hset.assert_called_once()
        mock_redis_client.expire.assert_called_once_with(f"sre:metrics:{result['task_id']}", 3600)

    @pytest.mark.asyncio
    async def test_analyze_metrics_with_retry(self, mock_redis_client):
        """Test metrics analysis with retry configuration."""
        mock_redis_client.hset.return_value = 1
        mock_redis_client.expire.return_value = True

        retry_config = Retry(attempts=5, delay=timedelta(seconds=10))

        with patch("redis_sre_agent.core.tasks.get_redis_client", return_value=mock_redis_client):
            result = await analyze_system_metrics(metric_query="memory_usage", retry=retry_config)

        assert result["metric_query"] == "memory_usage"
        assert result["status"] == "analyzed"

    @pytest.mark.asyncio
    async def test_analyze_metrics_redis_failure(self, mock_redis_client):
        """Test metrics analysis with Redis failure."""
        mock_redis_client.hset.side_effect = Exception("Redis connection failed")

        with patch("redis_sre_agent.core.tasks.get_redis_client", return_value=mock_redis_client):
            with pytest.raises(Exception, match="Redis connection failed"):
                await analyze_system_metrics("cpu_usage")


class TestSearchRunbookKnowledge:
    """Test search_runbook_knowledge task."""

    @pytest.mark.asyncio
    async def test_search_knowledge_success(self, mock_search_index, mock_vectorizer):
        """Test successful knowledge search."""
        # Mock vector embedding
        mock_vectorizer.embed_many = AsyncMock(return_value=[[0.1] * 1536])

        # Mock search results
        mock_search_results = [
            {
                "title": "Redis Memory Alert",
                "content": "Memory usage troubleshooting guide",
                "source": "runbook.md",
                "score": 0.95,
            }
        ]
        mock_search_index.query.return_value = mock_search_results

        with (
            patch("redis_sre_agent.core.tasks.get_knowledge_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.tasks.get_vectorizer", return_value=mock_vectorizer),
        ):
            result = await search_runbook_knowledge(
                query="redis memory issues", category="monitoring", limit=3
            )

        assert result["query"] == "redis memory issues"
        assert result["category"] == "monitoring"
        assert result["results_count"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Redis Memory Alert"
        assert "task_id" in result

        # Verify method calls
        mock_vectorizer.embed_many.assert_called_once_with(["redis memory issues"])
        mock_search_index.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_knowledge_no_category(self, mock_search_index, mock_vectorizer):
        """Test knowledge search without category filter."""
        mock_vectorizer.embed_many = AsyncMock(return_value=[[0.1] * 1536])
        mock_search_index.query.return_value = []

        with (
            patch("redis_sre_agent.core.tasks.get_knowledge_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.tasks.get_vectorizer", return_value=mock_vectorizer),
        ):
            result = await search_runbook_knowledge(query="general help", category=None)

        assert result["query"] == "general help"
        assert result["category"] is None
        assert result["results_count"] == 0

    @pytest.mark.asyncio
    async def test_search_knowledge_vectorizer_failure(self, mock_vectorizer):
        """Test knowledge search with vectorizer failure."""
        mock_vectorizer.embed_many.side_effect = Exception("OpenAI API error")

        with patch("redis_sre_agent.core.tasks.get_vectorizer", return_value=mock_vectorizer):
            with pytest.raises(Exception, match="OpenAI API error"):
                await search_runbook_knowledge("test query")


class TestCheckServiceHealth:
    """Test check_service_health task."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_redis_client):
        """Test successful service health check."""
        mock_redis_client.set = AsyncMock(return_value=True)
        mock_redis_client.expire = AsyncMock(return_value=True)

        endpoints = ["http://service1/health", "http://service2/health"]

        # Mock HTTP responses
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "healthy"})

        # Create async context manager mock for aiohttp
        class MockSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            def get(self, *args, **kwargs):
                class MockContextManager:
                    async def __aenter__(self):
                        return mock_response

                    async def __aexit__(self, *args):
                        return None

                return MockContextManager()

        mock_session = MockSession()

        with (
            patch("redis_sre_agent.core.tasks.get_redis_client", return_value=mock_redis_client),
            patch("aiohttp.ClientSession", return_value=mock_session),
        ):
            result = await check_service_health(
                service_name="my-service", endpoints=endpoints, timeout=60
            )

        assert result["service_name"] == "my-service"
        assert result["overall_status"] == "healthy"
        assert result["endpoints_checked"] == 2
        assert len(result["health_checks"]) == 2

        # Check individual health check structure
        health_check = result["health_checks"][0]
        assert "endpoint" in health_check
        assert "status" in health_check
        assert "response_time_ms" in health_check
        assert "status_code" in health_check
        assert "timestamp" in health_check

        # Verify Redis storage
        mock_redis_client.set.assert_called_once()
        mock_redis_client.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_single_endpoint(self, mock_redis_client):
        """Test health check with single endpoint."""
        mock_redis_client.hset.return_value = 1
        mock_redis_client.expire.return_value = True

        with patch("redis_sre_agent.core.tasks.get_redis_client", return_value=mock_redis_client):
            result = await check_service_health(
                service_name="single-service", endpoints=["http://service/health"]
            )

        assert result["endpoints_checked"] == 1
        assert len(result["health_checks"]) == 1

    @pytest.mark.asyncio
    async def test_health_check_redis_failure(self, mock_redis_client):
        """Test health check with Redis storage failure."""
        mock_redis_client.set = AsyncMock(side_effect=Exception("Redis error"))

        # Mock HTTP responses
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "healthy"})

        # Create async context manager mock for aiohttp
        class MockSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            def get(self, *args, **kwargs):
                class MockContextManager:
                    async def __aenter__(self):
                        return mock_response

                    async def __aexit__(self, *args):
                        return None

                return MockContextManager()

        mock_session = MockSession()

        with (
            patch("redis_sre_agent.core.tasks.get_redis_client", return_value=mock_redis_client),
            patch("aiohttp.ClientSession", return_value=mock_session),
        ):
            with pytest.raises(Exception, match="Redis error"):
                await check_service_health(service_name="test", endpoints=["http://test/health"])


class TestIngestSREDocument:
    """Test ingest_sre_document task."""

    @pytest.mark.asyncio
    async def test_ingest_document_success(self, mock_search_index, mock_vectorizer):
        """Test successful document ingestion."""
        # Mock embedding generation
        mock_vectorizer.embed_many = AsyncMock(return_value=[[0.1] * 1536])

        # Mock index loading
        mock_search_index.load.return_value = None

        with (
            patch("redis_sre_agent.core.tasks.get_knowledge_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.tasks.get_vectorizer", return_value=mock_vectorizer),
        ):
            result = await ingest_sre_document(
                title="Test Runbook",
                content="This is test content for the runbook",
                source="test/runbook.md",
                category="testing",
                severity="info",
            )

        assert result["title"] == "Test Runbook"
        assert result["source"] == "test/runbook.md"
        assert result["category"] == "testing"
        assert result["status"] == "ingested"
        assert "document_id" in result
        assert "task_id" in result

        # Verify embedding generation
        mock_vectorizer.embed_many.assert_called_once_with(["This is test content for the runbook"])

        # Verify document loading
        mock_search_index.load.assert_called_once()
        load_args = mock_search_index.load.call_args
        assert len(load_args.kwargs["data"]) == 1
        document = load_args.kwargs["data"][0]
        assert document["title"] == "Test Runbook"
        assert document["content"] == "This is test content for the runbook"

    @pytest.mark.asyncio
    async def test_ingest_document_with_defaults(self, mock_search_index, mock_vectorizer):
        """Test document ingestion with default values."""
        mock_vectorizer.embed_many = AsyncMock(return_value=[[0.1] * 1536])
        mock_search_index.load.return_value = None

        with (
            patch("redis_sre_agent.core.tasks.get_knowledge_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.tasks.get_vectorizer", return_value=mock_vectorizer),
        ):
            result = await ingest_sre_document(
                title="Default Doc",
                content="Content",
                source="source.md",
                # Using default category="general", severity="info"
            )

        assert result["category"] == "general"
        # Severity is part of the document, not the result
        load_args = mock_search_index.load.call_args
        document = load_args.kwargs["data"][0]
        assert document["severity"] == "info"

    @pytest.mark.asyncio
    async def test_ingest_document_embedding_failure(self, mock_vectorizer):
        """Test document ingestion with embedding failure."""
        mock_vectorizer.embed_many.side_effect = Exception("Embedding failed")

        with patch("redis_sre_agent.core.tasks.get_vectorizer", return_value=mock_vectorizer):
            with pytest.raises(Exception, match="Embedding failed"):
                await ingest_sre_document(title="Test", content="Content", source="test.md")


class TestTaskSystemManagement:
    """Test task system management functions."""

    @pytest.mark.asyncio
    async def test_register_sre_tasks_success(self):
        """Test successful task registration."""
        with (
            patch("redis_sre_agent.core.tasks.Docket") as mock_docket_class,
            patch(
                "redis_sre_agent.core.tasks.get_redis_url", return_value="redis://localhost:6379"
            ),
        ):

            # Set up the mock properly
            mock_docket_instance = AsyncMock()
            mock_docket_instance.__aenter__ = AsyncMock(return_value=mock_docket_instance)
            mock_docket_instance.__aexit__ = AsyncMock(return_value=None)
            mock_docket_instance.register = AsyncMock()
            mock_docket_class.return_value = mock_docket_instance

            await register_sre_tasks()

            # Verify Docket was created and tasks registered
            mock_docket_instance.register.assert_called()
            assert mock_docket_instance.register.call_count == len(SRE_TASK_COLLECTION)

    @pytest.mark.asyncio
    async def test_register_sre_tasks_failure(self):
        """Test task registration failure."""
        with (
            patch("redis_sre_agent.core.tasks.Docket") as mock_docket_class,
            patch(
                "redis_sre_agent.core.tasks.get_redis_url", return_value="redis://localhost:6379"
            ),
        ):
            mock_docket_instance = AsyncMock()
            mock_docket_instance.__aenter__ = AsyncMock(side_effect=Exception("Connection failed"))
            mock_docket_class.return_value = mock_docket_instance

            with pytest.raises(Exception, match="Connection failed"):
                await register_sre_tasks()

    @pytest.mark.asyncio
    async def test_task_system_test_success(self):
        """Test task system connectivity test success."""
        with patch("docket.Docket") as mock_docket_class:
            mock_docket_instance = AsyncMock()
            mock_docket_instance.__aenter__ = AsyncMock(return_value=mock_docket_instance)
            mock_docket_instance.__aexit__ = AsyncMock(return_value=None)
            mock_docket_class.return_value = mock_docket_instance

            with patch(
                "redis_sre_agent.core.tasks.get_redis_url", return_value="redis://localhost:6379"
            ):
                result = await test_task_system()

        assert result is True

    @pytest.mark.asyncio
    async def test_task_system_test_failure(self):
        """Test task system connectivity test failure."""
        with patch("redis_sre_agent.core.tasks.Docket") as mock_docket_class:
            mock_docket_class.side_effect = Exception("Connection failed")

            with patch(
                "redis_sre_agent.core.tasks.get_redis_url", return_value="redis://localhost:6379"
            ):
                result = await test_task_system()

        assert result is False

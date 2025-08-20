"""Integration tests for Redis infrastructure with real Redis instance."""

from unittest.mock import patch

import pytest

from redis_sre_agent.core.redis import (
    cleanup_redis_connections,
    create_indices,
    get_redis_client,
    initialize_redis_infrastructure,
    test_vector_search,
)


@pytest.mark.integration
class TestRedisIntegration:
    """Integration tests with real Redis instance."""

    @pytest.mark.asyncio
    async def test_redis_connection_real(self, async_redis_client):
        """Test real Redis connection."""
        # Clear any global state
        from redis_sre_agent.core import redis

        redis._redis_client = None

        # Test connection
        result = await async_redis_client.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_redis_infrastructure_initialization_real(self, redis_container):
        """Test infrastructure initialization with real Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Clear global state
        from redis_sre_agent.core import redis

        redis._redis_client = None
        redis._vectorizer = None
        redis._document_index = None

        # Mock the vectorizer to avoid OpenAI API calls in tests
        with patch("redis_sre_agent.core.redis.OpenAITextVectorizer") as mock_vectorizer:
            mock_vectorizer_instance = mock_vectorizer.return_value
            mock_vectorizer_instance.embed_many.return_value = [[0.1] * 1536]

            # Test infrastructure initialization
            status = await initialize_redis_infrastructure()

            # Should succeed with real Redis
            assert status["redis_connection"] == "available"
            assert status["vectorizer"] == "available"
            assert status["indices_created"] == "available"
            assert status["vector_search"] == "available"

    @pytest.mark.asyncio
    async def test_index_creation_real(self, redis_container):
        """Test index creation with real Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Clear global state
        from redis_sre_agent.core import redis

        redis._document_index = None

        # Mock vectorizer to avoid API calls
        with patch("redis_sre_agent.core.redis.OpenAITextVectorizer"):
            # Create indices
            result = await create_indices()
            assert result is True

            # Test that index exists
            index_exists = await test_vector_search()
            assert index_exists is True

    @pytest.mark.asyncio
    async def test_document_ingestion_real(self, redis_container):
        """Test document ingestion with real Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Clear global state
        from redis_sre_agent.core import redis
        from redis_sre_agent.core.tasks import ingest_sre_document

        redis._document_index = None
        redis._vectorizer = None

        # Mock vectorizer for embedding generation
        with patch("redis_sre_agent.core.redis.OpenAITextVectorizer") as mock_vectorizer:
            mock_vectorizer_instance = mock_vectorizer.return_value
            mock_vectorizer_instance.embed_many.return_value = [[0.1] * 1536]

            # Ensure index is created first
            await create_indices()

            # Test document ingestion
            result = await ingest_sre_document(
                title="Test Integration Document",
                content="This is a test document for integration testing",
                source="integration_test.md",
                category="testing",
                severity="info",
            )

            assert result["status"] == "ingested"
            assert result["title"] == "Test Integration Document"
            assert "document_id" in result

    @pytest.mark.asyncio
    async def test_search_real_documents(self, redis_container):
        """Test searching documents with real Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Clear global state
        from redis_sre_agent.core import redis
        from redis_sre_agent.core.tasks import ingest_sre_document, search_runbook_knowledge

        redis._document_index = None
        redis._vectorizer = None

        # Mock vectorizer
        with patch("redis_sre_agent.core.redis.OpenAITextVectorizer") as mock_vectorizer:
            mock_vectorizer_instance = mock_vectorizer.return_value
            mock_vectorizer_instance.embed_many.return_value = [[0.1] * 1536]

            # Create index and ingest a document
            await create_indices()
            await ingest_sre_document(
                title="Redis Performance Guide",
                content="Guide for optimizing Redis performance and memory usage",
                source="performance.md",
                category="optimization",
                severity="info",
            )

            # Search for the document
            search_result = await search_runbook_knowledge(
                query="Redis performance", category="optimization", limit=5
            )

            assert search_result["query"] == "Redis performance"
            assert search_result["category"] == "optimization"
            # Note: Real search might not return results due to vector similarity,
            # but the operation should complete without error

    @pytest.mark.asyncio
    async def test_cleanup_real(self, redis_container):
        """Test cleanup with real Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Initialize connections
        client = get_redis_client()
        assert client is not None

        # Test cleanup
        await cleanup_redis_connections()

        # Should not throw errors


@pytest.mark.integration
class TestTaskIntegration:
    """Integration tests for task system with real Redis."""

    @pytest.mark.asyncio
    async def test_task_system_connectivity_real(self, redis_container):
        """Test task system connectivity with real Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        from redis_sre_agent.core.tasks import register_sre_tasks, test_task_system

        # Test basic connectivity
        result = await test_task_system()
        assert result is True

        # Test task registration (should not fail)
        await register_sre_tasks()

    @pytest.mark.asyncio
    async def test_metrics_analysis_real(self, redis_container):
        """Test metrics analysis task with real Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        from redis_sre_agent.core.tasks import analyze_system_metrics

        result = await analyze_system_metrics(
            metric_query="cpu_usage{instance='server1'}", time_range="1h", threshold=80.0
        )

        assert result["metric_query"] == "cpu_usage{instance='server1'}"
        assert result["status"] == "analyzed"
        assert "task_id" in result

    @pytest.mark.asyncio
    async def test_health_check_real(self, redis_container):
        """Test health check task with real Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        from redis_sre_agent.core.tasks import check_service_health

        result = await check_service_health(
            service_name="test-service", endpoints=["http://localhost/health"], timeout=30
        )

        assert result["service_name"] == "test-service"
        assert result["endpoints_checked"] == 1
        assert "task_id" in result


@pytest.mark.integration
class TestAPIIntegration:
    """Integration tests for API with real Redis."""

    @pytest.mark.asyncio
    async def test_health_endpoint_real(self, async_test_client, redis_container):
        """Test health endpoint with real Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Mock vectorizer to avoid API calls
        with patch("redis_sre_agent.core.redis.OpenAITextVectorizer"):
            response = await async_test_client.get("/health")

        # Should return some status (may be unhealthy due to missing components)
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert "components" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_root_endpoint_real(self, async_test_client):
        """Test root endpoint with real infrastructure."""
        response = await async_test_client.get("/")

        assert response.status_code == 200
        assert "Redis SRE Agent" in response.text

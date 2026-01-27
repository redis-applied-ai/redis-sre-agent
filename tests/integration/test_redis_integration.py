"""Integration tests for Redis infrastructure with real Redis instance."""

from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.redis import (
    create_indices,
    initialize_redis,
    test_vector_search,
)


@pytest.mark.integration
class TestRedisIntegration:
    """Integration tests with real Redis instance."""

    @pytest.mark.asyncio
    async def test_redis_connection_real(self, async_redis_client):
        """Test real Redis connection."""
        # Test connection using injected client
        result = await async_redis_client.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_redis_infrastructure_initialization_real(self, test_settings):
        """Test infrastructure initialization with real Redis."""
        # Mock the vectorizer to avoid OpenAI API calls in tests
        with patch("redis_sre_agent.core.redis.OpenAITextVectorizer") as mock_vectorizer:
            mock_vectorizer_instance = mock_vectorizer.return_value
            mock_vectorizer_instance.embed_many.return_value = [[0.1] * 1536]

            # Test infrastructure initialization with dependency injection
            status = await initialize_redis(config=test_settings)

            # Should succeed with real Redis
            assert status["redis_connection"] == "available"
            assert status["vectorizer"] == "available"
            assert status["indices_created"] == "available"
            assert status["vector_search"] == "available"

    @pytest.mark.asyncio
    async def test_index_creation_real(self, test_settings):
        """Test index creation with real Redis."""
        # Mock vectorizer to avoid API calls
        with patch("redis_sre_agent.core.redis.OpenAITextVectorizer"):
            # Create indices with dependency injection
            result = await create_indices(config=test_settings)
            assert result is True

            # Test that index exists
            index_exists = await test_vector_search(config=test_settings)
            assert index_exists is True

    @pytest.mark.asyncio
    async def test_document_ingestion_real(self, test_settings):
        """Test document ingestion with real Redis."""
        import numpy as np

        from redis_sre_agent.core.docket_tasks import ingest_sre_document

        # Mock vectorizer for embedding generation
        # Create a mock that returns bytes (as_buffer=True behavior)
        mock_inner = AsyncMock()
        mock_inner.embed.return_value = np.array([0.1] * 1536, dtype=np.float32).tobytes()

        mock_vectorizer = AsyncMock()
        mock_vectorizer._inner = mock_inner

        with patch("redis_sre_agent.core.redis.get_vectorizer", return_value=mock_vectorizer):
            # Ensure index is created first
            await create_indices(config=test_settings)

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
    async def test_search_real_documents(self, test_settings):
        """Test searching documents with real Redis."""
        import numpy as np

        from redis_sre_agent.core.docket_tasks import ingest_sre_document, search_knowledge_base

        # Mock vectorizer
        mock_inner = AsyncMock()
        mock_inner.embed.return_value = np.array([0.1] * 1536, dtype=np.float32).tobytes()

        mock_vectorizer = AsyncMock()
        mock_vectorizer._inner = mock_inner
        mock_vectorizer.embed_many.return_value = [[0.1] * 1536]  # For search

        with patch("redis_sre_agent.core.redis.get_vectorizer", return_value=mock_vectorizer):
            # Create index and ingest a document
            await create_indices(config=test_settings)
            await ingest_sre_document(
                title="Redis Performance Guide",
                content="Guide for optimizing Redis performance and memory usage",
                source="performance.md",
                category="optimization",
                severity="info",
            )

            # Search for the document
            search_result = await search_knowledge_base(
                query="Redis performance", category="optimization", limit=5
            )

            assert search_result["query"] == "Redis performance"
            assert search_result["category"] == "optimization"
            # Note: Real search might not return results due to vector similarity,
            # but the operation should complete without error

    @pytest.mark.asyncio
    async def test_cleanup_real(self, async_redis_client):
        """Test cleanup with real Redis."""
        # Verify client is connected
        assert async_redis_client is not None
        await async_redis_client.ping()

        # No explicit cleanup necessary; just ensure no errors after use


@pytest.mark.integration
class TestTaskIntegration:
    """Integration tests for task system with real Redis."""

    @pytest.mark.asyncio
    async def test_task_system_connectivity_real(self, test_settings):
        """Test task system connectivity with real Redis."""
        from redis_sre_agent.core.docket_tasks import register_sre_tasks, test_task_system

        # Test basic connectivity - note: test_task_system uses global settings
        # TODO: Add config parameter to test_task_system for full dependency injection support
        result = await test_task_system()
        assert result is True

        # Test task registration (should not fail)
        await register_sre_tasks()

    @pytest.mark.asyncio
    async def test_health_check_real(self):
        """Test health check task with real Redis."""
        from redis_sre_agent.core.docket_tasks import check_service_health

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
    async def test_health_endpoint_real(self, async_test_client, test_settings):
        """Test health endpoint with real Redis."""
        # Mock vectorizer to avoid API calls
        with patch("redis_sre_agent.core.redis.OpenAITextVectorizer"):
            response = await async_test_client.get("/api/v1/health")

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

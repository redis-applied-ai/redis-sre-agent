"""Unit tests for Redis infrastructure components."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from redis_sre_agent.core.redis import (
    SRE_KNOWLEDGE_SCHEMA,
    cleanup_redis_connections,
    create_indices,
    get_knowledge_index,
    get_redis_client,
    get_vectorizer,
    initialize_redis_infrastructure,
    test_redis_connection,
    test_vector_search,
)


class TestRedisInfrastructure:
    """Test Redis infrastructure components."""

    def test_sre_knowledge_schema(self):
        """Test SRE knowledge schema definition."""
        schema = SRE_KNOWLEDGE_SCHEMA

        assert schema["index"]["name"] == "sre_knowledge"
        assert schema["index"]["prefix"] == "sre_knowledge:"
        assert schema["index"]["storage_type"] == "hash"

        # Check required fields
        field_names = {field["name"] for field in schema["fields"]}
        expected_fields = {
            "title",
            "content",
            "source",
            "category",
            "severity",
            "created_at",
            "vector",
        }
        assert expected_fields.issubset(field_names)

        # Check vector field configuration
        vector_field = next(f for f in schema["fields"] if f["name"] == "vector")
        assert vector_field["type"] == "vector"
        assert vector_field["attrs"]["dims"] == 1536
        assert vector_field["attrs"]["distance_metric"] == "cosine"

    @patch("redis_sre_agent.core.redis.Redis")
    def test_get_redis_client(self, mock_redis):
        """Test Redis client singleton."""
        mock_client = Mock()
        mock_redis.from_url.return_value = mock_client

        # First call creates client
        client1 = get_redis_client()
        assert client1 == mock_client
        mock_redis.from_url.assert_called_once()

        # Second call returns same instance
        client2 = get_redis_client()
        assert client2 == mock_client
        assert client1 is client2
        # from_url should still only be called once
        assert mock_redis.from_url.call_count == 1

    @patch("redis_sre_agent.core.redis.EmbeddingsCache")
    @patch("redis_sre_agent.core.redis.OpenAITextVectorizer")
    def test_get_vectorizer(self, mock_vectorizer, mock_cache):
        """Test vectorizer singleton creation."""
        mock_cache_instance = Mock()
        mock_cache.return_value = mock_cache_instance

        mock_vectorizer_instance = Mock()
        mock_vectorizer.return_value = mock_vectorizer_instance

        # First call creates vectorizer
        vectorizer1 = get_vectorizer()
        assert vectorizer1 == mock_vectorizer_instance
        mock_cache.assert_called_once()
        mock_vectorizer.assert_called_once()

        # Second call returns same instance
        vectorizer2 = get_vectorizer()
        assert vectorizer2 == mock_vectorizer_instance
        assert vectorizer1 is vectorizer2

    @patch("redis_sre_agent.core.redis.AsyncSearchIndex")
    def test_get_knowledge_index(self, mock_index):
        """Test knowledge index singleton creation."""
        import os

        mock_index_instance = Mock()
        mock_index.from_dict.return_value = mock_index_instance

        # First call creates index
        index1 = get_knowledge_index()
        assert index1 == mock_index_instance

        # Should use whatever REDIS_URL is set in environment
        expected_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        mock_index.from_dict.assert_called_once_with(
            SRE_KNOWLEDGE_SCHEMA, redis_url=expected_redis_url
        )

        # Second call returns same instance
        index2 = get_knowledge_index()
        assert index2 == mock_index_instance
        assert index1 is index2

    @pytest.mark.asyncio
    async def test_redis_connection_success(self, mock_redis_client):
        """Test successful Redis connection."""
        mock_redis_client.ping.return_value = True

        with patch("redis_sre_agent.core.redis.get_redis_client", return_value=mock_redis_client):
            result = await test_redis_connection()

        assert result is True
        mock_redis_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_connection_failure(self, mock_redis_client):
        """Test Redis connection failure."""
        mock_redis_client.ping.side_effect = Exception("Connection failed")

        with patch("redis_sre_agent.core.redis.get_redis_client", return_value=mock_redis_client):
            result = await test_redis_connection()

        assert result is False
        mock_redis_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_search_success(self, mock_search_index):
        """Test successful vector search test."""
        mock_search_index.exists.return_value = True

        with patch(
            "redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_search_index
        ):
            result = await test_vector_search()

        assert result is True
        mock_search_index.exists.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_search_failure(self, mock_search_index):
        """Test vector search test failure."""
        mock_search_index.exists.side_effect = Exception("Index error")

        with patch(
            "redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_search_index
        ):
            result = await test_vector_search()

        assert result is False
        mock_search_index.exists.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_indices_new_index(self, mock_search_index):
        """Test creating new indices."""
        mock_search_index.exists.return_value = False
        mock_search_index.create.return_value = None

        with (
            patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_schedules_index", return_value=mock_search_index),
        ):
            result = await create_indices()

        assert result is True
        # Should be called twice - once for knowledge index, once for schedules index
        assert mock_search_index.exists.call_count == 2
        assert mock_search_index.create.call_count == 2

    @pytest.mark.asyncio
    async def test_create_indices_existing_index(self, mock_search_index):
        """Test handling existing indices."""
        mock_search_index.exists.return_value = True

        with (
            patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_schedules_index", return_value=mock_search_index),
        ):
            result = await create_indices()

        assert result is True
        # Should be called twice - once for knowledge index, once for schedules index
        assert mock_search_index.exists.call_count == 2
        mock_search_index.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_indices_failure(self, mock_search_index):
        """Test index creation failure."""
        mock_search_index.exists.side_effect = Exception("Index creation failed")

        with patch(
            "redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_search_index
        ):
            result = await create_indices()

        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_redis_infrastructure_success(self):
        """Test successful infrastructure initialization."""
        with (
            patch("redis_sre_agent.core.redis.test_redis_connection", return_value=True),
            patch("redis_sre_agent.core.redis.get_vectorizer", return_value=Mock()),
            patch("redis_sre_agent.core.redis.create_indices", return_value=True),
            patch("redis_sre_agent.core.redis.test_vector_search", return_value=True),
            patch("redis_sre_agent.core.redis.initialize_docket_infrastructure", return_value=True),
        ):
            result = await initialize_redis_infrastructure()

        expected_status = {
            "redis_connection": "available",
            "vectorizer": "available",
            "indices_created": "available",
            "docket_infrastructure": "available",
            "vector_search": "available",
        }
        assert result == expected_status

    @pytest.mark.asyncio
    async def test_initialize_redis_infrastructure_redis_failure(self):
        """Test infrastructure initialization with Redis failure."""
        with (
            patch("redis_sre_agent.core.redis.test_redis_connection", return_value=False),
            patch("redis_sre_agent.core.redis.get_vectorizer", return_value=Mock()),
        ):
            result = await initialize_redis_infrastructure()

        assert result["redis_connection"] == "unavailable"
        assert result["indices_created"] == "unavailable"
        assert result["vector_search"] == "unavailable"

    @pytest.mark.asyncio
    async def test_initialize_redis_infrastructure_vectorizer_failure(self):
        """Test infrastructure initialization with vectorizer failure."""
        with (
            patch("redis_sre_agent.core.redis.test_redis_connection", return_value=True),
            patch(
                "redis_sre_agent.core.redis.get_vectorizer", side_effect=Exception("API key error")
            ),
        ):
            result = await initialize_redis_infrastructure()

        assert result["redis_connection"] == "available"
        assert result["vectorizer"] == "unavailable"

    @pytest.mark.asyncio
    async def test_cleanup_redis_connections(self, mock_redis_client):
        """Test Redis connection cleanup."""
        mock_redis_client.aclose = AsyncMock()

        with patch("redis_sre_agent.core.redis._redis_client", mock_redis_client):
            await cleanup_redis_connections()

        mock_redis_client.aclose.assert_called_once()


class TestRedisSingletons:
    """Test singleton behavior reset between tests."""

    def test_singleton_reset(self):
        """Test that singletons are properly reset between tests."""
        # This test verifies that our fixtures properly reset global state
        from redis_sre_agent.core import redis

        # All singletons should be None at start of test
        assert redis._redis_client is None
        assert redis._vectorizer is None
        assert redis._document_index is None

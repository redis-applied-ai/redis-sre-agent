"""Unit tests for Redis infrastructure components."""

from unittest.mock import Mock, patch

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

        from redis_sre_agent.core.keys import RedisKeys

        assert schema["index"]["name"] == "sre_knowledge"
        assert schema["index"]["prefix"] == RedisKeys.PREFIX_KNOWLEDGE + ":"
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
        """Test Redis client creation (no caching - creates fresh each time)."""
        mock_client = Mock()
        mock_redis.from_url.return_value = mock_client

        # First call creates client
        client1 = get_redis_client()
        assert client1 == mock_client
        mock_redis.from_url.assert_called_once()

        # Second call creates NEW client (no caching to avoid event loop issues)
        client2 = get_redis_client()
        assert client2 == mock_client
        # from_url should be called TWICE (no caching)
        assert mock_redis.from_url.call_count == 2

    @patch("redis_sre_agent.core.redis.EmbeddingsCache")
    @patch("redis_sre_agent.core.redis.OpenAITextVectorizer")
    def test_get_vectorizer(self, mock_vectorizer, mock_cache):
        """Test vectorizer creation (no caching - creates fresh each time)."""
        mock_cache_instance = Mock()
        mock_cache.return_value = mock_cache_instance

        mock_vectorizer_instance = Mock()
        mock_vectorizer.return_value = mock_vectorizer_instance

        # First call creates vectorizer
        vectorizer1 = get_vectorizer()
        assert vectorizer1 == mock_vectorizer_instance
        mock_cache.assert_called_once()
        mock_vectorizer.assert_called_once()

        # Second call creates NEW instance (no caching to avoid event loop issues)
        vectorizer2 = get_vectorizer()
        assert vectorizer2 == mock_vectorizer_instance
        # Should be called TWICE (no caching)
        assert mock_cache.call_count == 2
        assert mock_vectorizer.call_count == 2

    @pytest.mark.asyncio
    async def test_get_knowledge_index(self):
        """Test knowledge index creation (no caching - creates fresh each time)."""
        # Just test that it returns an AsyncSearchIndex instance
        # Don't test implementation details
        index1 = await get_knowledge_index()
        assert index1 is not None

        # Second call creates NEW instance (no caching to avoid event loop issues)
        index2 = await get_knowledge_index()
        assert index2 is not None
        # Should be different instances (no caching)
        assert index1 is not index2

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
            patch("redis_sre_agent.core.redis.get_threads_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_tasks_index", return_value=mock_search_index),
        ):
            result = await create_indices()

        assert result is True
        # Should be called four times - knowledge, schedules, threads, tasks
        assert mock_search_index.exists.call_count == 4
        assert mock_search_index.create.call_count == 4

    @pytest.mark.asyncio
    async def test_create_indices_existing_index(self, mock_search_index):
        """Test handling existing indices."""
        mock_search_index.exists.return_value = True

        with (
            patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_schedules_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_threads_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_tasks_index", return_value=mock_search_index),
        ):
            result = await create_indices()

        assert result is True
        # Should be called four times - knowledge, schedules, threads, tasks
        assert mock_search_index.exists.call_count == 4
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
        """Test Redis connection cleanup (no-op since we removed caching)."""
        # Cleanup function still exists but does nothing since we removed caching
        await cleanup_redis_connections()
        # No assertions needed - just verify it doesn't crash

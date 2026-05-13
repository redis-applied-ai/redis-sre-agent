"""Unit tests for Redis infrastructure components."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from redis_sre_agent.core.redis import (
    SRE_KNOWLEDGE_SCHEMA,
    SRE_SKILLS_SCHEMA,
    SRE_SUPPORT_TICKETS_SCHEMA,
    create_indices,
    get_index_schema_status,
    get_knowledge_index,
    get_redis_client,
    get_vectorizer,
    initialize_redis,
    sync_index_schemas,
    test_redis_connection,
    test_vector_search,
)


class TestRedisInfrastructure:
    """Test Redis infrastructure components."""

    def test_sre_knowledge_schema(self):
        """Test SRE knowledge schema definition."""
        schema = SRE_KNOWLEDGE_SCHEMA

        from redis_sre_agent.core.config import settings
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
        # Use settings.vector_dim since schema is defined at import time with that value
        assert vector_field["attrs"]["dims"] == settings.vector_dim
        assert vector_field["attrs"]["distance_metric"] == "cosine"

    def test_skills_and_support_ticket_schema_include_pinned_field(self):
        """Skills and support-ticket indexes should include pinned as a tag field."""
        for schema in (SRE_SKILLS_SCHEMA, SRE_SUPPORT_TICKETS_SCHEMA):
            field_names = {field["name"] for field in schema["fields"]}
            assert "pinned" in field_names
            ordered_field_names = [field["name"] for field in schema["fields"]]
            assert ordered_field_names.index("pinned") < ordered_field_names.index("chunk_index")

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

    @patch("redis_sre_agent.core.redis.create_vectorizer")
    def test_get_vectorizer(self, mock_create_vectorizer):
        """Test vectorizer creation delegates to the helper on each call."""
        mock_vectorizer_instance = Mock()
        mock_create_vectorizer.return_value = mock_vectorizer_instance

        vectorizer1 = get_vectorizer()
        assert vectorizer1 == mock_vectorizer_instance
        mock_create_vectorizer.assert_called_once_with(config=None)

        vectorizer2 = get_vectorizer()
        assert vectorizer2 == mock_vectorizer_instance
        assert mock_create_vectorizer.call_count == 2

    @patch("redis_sre_agent.core.redis.create_vectorizer")
    def test_get_vectorizer_passes_explicit_config(self, mock_create_vectorizer):
        """Test get_vectorizer forwards explicit config for dependency injection."""
        mock_vectorizer_instance = Mock()
        mock_create_vectorizer.return_value = mock_vectorizer_instance
        config = Mock()

        result = get_vectorizer(config=config)

        assert result is mock_vectorizer_instance
        mock_create_vectorizer.assert_called_once_with(config=config)

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
            patch("redis_sre_agent.core.redis.get_skills_index", return_value=mock_search_index),
            patch(
                "redis_sre_agent.core.redis.get_support_tickets_index",
                return_value=mock_search_index,
            ),
            patch("redis_sre_agent.core.redis.get_schedules_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_threads_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_tasks_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_instances_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_clusters_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_targets_index", return_value=mock_search_index),
        ):
            result = await create_indices()

        assert result is True
        # Should be called nine times - knowledge, skills, support_tickets,
        # schedules, threads, tasks, instances, clusters, targets
        assert mock_search_index.exists.call_count == 9
        assert mock_search_index.create.call_count == 9

    @pytest.mark.asyncio
    async def test_create_indices_existing_index(self, mock_search_index):
        """Test handling existing indices."""
        mock_search_index.exists.return_value = True

        with (
            patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_skills_index", return_value=mock_search_index),
            patch(
                "redis_sre_agent.core.redis.get_support_tickets_index",
                return_value=mock_search_index,
            ),
            patch("redis_sre_agent.core.redis.get_schedules_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_threads_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_tasks_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_instances_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_clusters_index", return_value=mock_search_index),
            patch("redis_sre_agent.core.redis.get_targets_index", return_value=mock_search_index),
        ):
            result = await create_indices()

        assert result is True
        # Should be called nine times - knowledge, skills, support_tickets,
        # schedules, threads, tasks, instances, clusters, targets
        assert mock_search_index.exists.call_count == 9
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
    async def test_initialize_redis_runs_knowledge_pack_auto_load_when_indices_ready(self):
        mock_config = Mock(openai_api_key=None)

        with (
            patch("redis_sre_agent.core.redis.test_redis_connection", return_value=True),
            patch("redis_sre_agent.core.redis.create_indices", return_value=True),
            patch("redis_sre_agent.core.redis.initialize_docket", return_value=True),
            patch("redis_sre_agent.core.redis.test_vector_search", return_value=True),
            patch(
                "redis_sre_agent.knowledge_pack.loader.auto_load_configured_knowledge_pack",
                return_value={"status": "loaded", "pack_id": "pack-123"},
            ) as auto_load_mock,
        ):
            status = await initialize_redis(config=mock_config)

        assert status["knowledge_pack_auto_load"] == {"status": "loaded", "pack_id": "pack-123"}
        auto_load_mock.assert_awaited_once_with(mock_config)

    @pytest.mark.asyncio
    async def test_get_index_schema_status_detects_missing_pinned_field(self):
        """Schema status should flag older indices that are missing pinned."""
        from redis_sre_agent.core.config import settings

        mock_index = AsyncMock()
        mock_index.exists.return_value = True
        mock_index._redis_client = AsyncMock()
        attributes = []
        for field in SRE_SKILLS_SCHEMA["fields"]:
            if field["name"] == "pinned":
                continue
            field_type = str(field["type"]).upper()
            attribute = [b"attribute", str(field["name"]).encode(), b"type", field_type.encode()]
            if field_type == "VECTOR":
                attrs = field["attrs"]
                attribute.extend(
                    [
                        b"algorithm",
                        str(attrs["algorithm"]).upper().encode(),
                        b"data_type",
                        str(attrs["datatype"]).upper().encode(),
                        b"dim",
                        str(settings.vector_dim).encode(),
                        b"distance_metric",
                        str(attrs["distance_metric"]).upper().encode(),
                    ]
                )
            attributes.append(attribute)
        mock_index._redis_client.execute_command.return_value = [b"attributes", attributes]

        with patch("redis_sre_agent.core.redis.get_skills_index", return_value=mock_index):
            result = await get_index_schema_status(index_name="skills")

        assert result["success"] is True
        assert result["indices"]["skills"]["status"] == "drifted"
        assert result["indices"]["skills"]["missing_fields"] == ["pinned"]

    @pytest.mark.asyncio
    async def test_get_index_schema_status_normalizes_vector_dim_from_redis_info(self):
        """Vector dim should not trigger false drift when Redis returns it as a string."""
        from redis_sre_agent.core.config import settings

        mock_index = AsyncMock()
        mock_index.exists.return_value = True
        mock_index._redis_client = AsyncMock()

        attributes = []
        for field in SRE_KNOWLEDGE_SCHEMA["fields"]:
            name = field["name"]
            field_type = str(field["type"]).upper()
            attribute = [b"attribute", str(name).encode(), b"type", field_type.encode()]
            if field_type == "VECTOR":
                attrs = field["attrs"]
                attribute.extend(
                    [
                        b"algorithm",
                        str(attrs["algorithm"]).upper().encode(),
                        b"data_type",
                        str(attrs["datatype"]).upper().encode(),
                        b"dim",
                        str(settings.vector_dim).encode(),
                        b"distance_metric",
                        str(attrs["distance_metric"]).upper().encode(),
                    ]
                )
            attributes.append(attribute)

        mock_index._redis_client.execute_command.return_value = [b"attributes", attributes]

        with patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_index):
            result = await get_index_schema_status(index_name="knowledge")

        assert result["success"] is True
        assert result["indices"]["knowledge"]["status"] == "in_sync"
        assert result["indices"]["knowledge"]["mismatched_fields"] == {}

    @pytest.mark.asyncio
    async def test_sync_index_schemas_recreates_drifted_index(self):
        """Schema sync should recreate an index whose fields have drifted."""
        mock_index = AsyncMock()
        mock_index.exists.return_value = True
        mock_index.create = AsyncMock()
        mock_index._redis_client = AsyncMock()
        mock_index._redis_client.execute_command = AsyncMock(
            side_effect=[
                [
                    b"attributes",
                    [
                        [b"attribute", b"title", b"type", b"TEXT"],
                        [b"attribute", b"content", b"type", b"TEXT"],
                    ],
                ],
                b"OK",
            ]
        )

        with patch("redis_sre_agent.core.redis.get_skills_index", return_value=mock_index):
            result = await sync_index_schemas(index_name="skills")

        assert result["success"] is True
        assert result["indices"]["skills"]["action"] == "recreated"
        mock_index.create.assert_awaited_once()
        assert mock_index._redis_client.execute_command.await_args_list[1].args == (
            "FT.DROPINDEX",
            "sre_skills",
        )

    @pytest.mark.asyncio
    async def test_initialize_redis_infrastructure_success(self):
        """Test successful infrastructure initialization."""
        with (
            patch("redis_sre_agent.core.redis.test_redis_connection", return_value=True),
            patch("redis_sre_agent.core.redis.get_vectorizer", return_value=Mock()),
            patch("redis_sre_agent.core.redis.create_indices", return_value=True),
            patch("redis_sre_agent.core.redis.test_vector_search", return_value=True),
            patch("redis_sre_agent.core.redis.initialize_docket", return_value=True),
        ):
            result = await initialize_redis()

        expected_status = {
            "redis_connection": "available",
            "vectorizer": "available",
            "indices_created": "available",
            "knowledge_pack_auto_load": {
                "status": "skipped",
                "reason": "knowledge_pack_auto_load_disabled",
            },
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
            result = await initialize_redis()

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
            result = await initialize_redis()

        assert result["redis_connection"] == "available"
        assert result["vectorizer"] == "unavailable"

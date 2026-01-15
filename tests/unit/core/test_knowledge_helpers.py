"""Tests for knowledge helper functions."""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.knowledge_helpers import (
    get_all_document_fragments,
    get_related_document_fragments,
    ingest_sre_document_helper,
    search_knowledge_base_helper,
)


class TestKnowledgeHelpers:
    """Test knowledge helper functions."""

    def test_get_all_document_fragments_exists(self):
        """Test that get_all_document_fragments exists and has correct signature."""
        sig = inspect.signature(get_all_document_fragments)
        params = list(sig.parameters.keys())

        assert "document_hash" in params
        assert "include_metadata" in params

        # Verify it's an async function
        assert inspect.iscoroutinefunction(get_all_document_fragments)

    def test_get_related_document_fragments_exists(self):
        """Test that get_related_document_fragments exists and has correct signature."""
        sig = inspect.signature(get_related_document_fragments)
        params = list(sig.parameters.keys())

        assert "document_hash" in params
        assert "current_chunk_index" in params
        assert "context_window" in params

        # Verify it's an async function
        assert inspect.iscoroutinefunction(get_related_document_fragments)

    def test_functions_are_documented(self):
        """Test that helper functions have docstrings."""
        assert get_all_document_fragments.__doc__ is not None
        assert get_related_document_fragments.__doc__ is not None
        assert "retrieve all fragments" in get_all_document_fragments.__doc__.lower()
        assert "related fragments" in get_related_document_fragments.__doc__.lower()


class TestSearchKnowledgeBaseHelper:
    """Test search_knowledge_base_helper function."""

    @pytest.mark.asyncio
    async def test_search_knowledge_base_success(self):
        """Test successful knowledge base search."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {
                    "id": "doc-1",
                    "document_hash": "hash-1",
                    "chunk_index": 0,
                    "title": "Redis Memory",
                    "content": "Redis memory management guide",
                    "source": "docs",
                    "category": "monitoring",
                    "version": "latest",
                    "score": 0.95,
                }
            ]
        )

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            result = await search_knowledge_base_helper(
                query="redis memory",
                limit=10,
            )

        assert result["query"] == "redis memory"
        assert result["results_count"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Redis Memory"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_with_version_filter(self):
        """Test knowledge base search with version filter."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(return_value=[])

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            result = await search_knowledge_base_helper(
                query="redis memory",
                version="7.8",
                limit=10,
            )

        assert result["version"] == "7.8"
        assert result["results_count"] == 0

    @pytest.mark.asyncio
    async def test_search_knowledge_base_hybrid_search(self):
        """Test knowledge base hybrid search."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(return_value=[])

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            result = await search_knowledge_base_helper(
                query="redis memory",
                hybrid_search=True,
                limit=10,
            )

        assert result["results_count"] == 0
        mock_index.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_knowledge_base_with_offset(self):
        """Test knowledge base search with offset pagination."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {"id": "doc-1", "title": "Doc 1", "score": 0.9},
                {"id": "doc-2", "title": "Doc 2", "score": 0.8},
                {"id": "doc-3", "title": "Doc 3", "score": 0.7},
            ]
        )

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            result = await search_knowledge_base_helper(
                query="redis",
                offset=1,
                limit=2,
            )

        # Should skip first result due to offset
        assert result["offset"] == 1
        assert result["results_count"] == 2
        assert result["total_fetched"] == 3

    @pytest.mark.asyncio
    async def test_search_knowledge_base_no_distance_threshold(self):
        """Test knowledge base search with no distance threshold (pure KNN)."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(return_value=[])

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            result = await search_knowledge_base_helper(
                query="redis",
                distance_threshold=None,  # Disable threshold
                limit=10,
            )

        assert result["results_count"] == 0
        mock_index.query.assert_called_once()


class TestIngestSreDocumentHelper:
    """Test ingest_sre_document_helper function."""

    @pytest.mark.asyncio
    async def test_ingest_document_success(self):
        """Test successful document ingestion."""
        mock_index = AsyncMock()
        mock_index.load = AsyncMock()

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed = AsyncMock(return_value=b"vector_bytes")

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            result = await ingest_sre_document_helper(
                title="Test Document",
                content="This is test content",
                source="test",
                category="runbook",
                severity="info",
            )

        assert result["status"] == "ingested"
        assert result["title"] == "Test Document"
        assert result["source"] == "test"
        assert result["category"] == "runbook"
        assert "document_id" in result
        mock_index.load.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_document_with_product_labels(self):
        """Test document ingestion with product labels."""
        mock_index = AsyncMock()
        mock_index.load = AsyncMock()

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed = AsyncMock(return_value=b"vector_bytes")

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            result = await ingest_sre_document_helper(
                title="Redis Cloud Guide",
                content="Redis Cloud content",
                source="docs",
                category="guide",
                product_labels=["redis-cloud", "enterprise"],
            )

        assert result["status"] == "ingested"
        # Verify the document was loaded with product labels
        call_args = mock_index.load.call_args
        doc_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert doc_data[0]["product_labels"] == "redis-cloud,enterprise"


class TestGetAllDocumentFragments:
    """Test get_all_document_fragments function."""

    @pytest.mark.asyncio
    async def test_get_all_fragments_success(self):
        """Test successful retrieval of all document fragments."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {"chunk_index": "0", "content": "Part 1", "title": "Doc"},
                {"chunk_index": "1", "content": "Part 2", "title": "Doc"},
                {"chunk_index": "2", "content": "Part 3", "title": "Doc"},
            ]
        )

        mock_deduplicator = MagicMock()
        mock_deduplicator.get_document_metadata = AsyncMock(
            return_value={"title": "Test Doc", "source": "test"}
        )

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.pipelines.ingestion.deduplication.DocumentDeduplicator",
                return_value=mock_deduplicator,
            ),
        ):
            result = await get_all_document_fragments(
                document_hash="test-hash-123",
                include_metadata=True,
            )

        assert result["document_hash"] == "test-hash-123"
        assert result["fragments_count"] == 3
        assert len(result["fragments"]) == 3
        # Verify fragments are sorted by chunk_index
        assert result["fragments"][0]["chunk_index"] == 0
        assert result["fragments"][1]["chunk_index"] == 1
        assert result["fragments"][2]["chunk_index"] == 2

    @pytest.mark.asyncio
    async def test_get_all_fragments_no_results(self):
        """Test retrieval when no fragments found."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(return_value=[])

        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ):
            result = await get_all_document_fragments(
                document_hash="nonexistent-hash",
            )

        assert result["document_hash"] == "nonexistent-hash"
        assert "error" in result
        assert result["fragments"] == []

    @pytest.mark.asyncio
    async def test_get_all_fragments_error_handling(self):
        """Test error handling in get_all_document_fragments."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
            new_callable=AsyncMock,
            side_effect=Exception("Connection error"),
        ):
            result = await get_all_document_fragments(
                document_hash="test-hash",
            )

        assert result["document_hash"] == "test-hash"
        assert "error" in result
        assert "Connection error" in result["error"]


class TestGetRelatedDocumentFragments:
    """Test get_related_document_fragments function."""

    @pytest.mark.asyncio
    async def test_get_related_fragments_with_context(self):
        """Test getting related fragments with context window."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {"chunk_index": "0", "content": "Part 0"},
                {"chunk_index": "1", "content": "Part 1"},
                {"chunk_index": "2", "content": "Part 2"},
                {"chunk_index": "3", "content": "Part 3"},
                {"chunk_index": "4", "content": "Part 4"},
            ]
        )

        mock_deduplicator = MagicMock()
        mock_deduplicator.get_document_metadata = AsyncMock(return_value={})

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.pipelines.ingestion.deduplication.DocumentDeduplicator",
                return_value=mock_deduplicator,
            ),
        ):
            result = await get_related_document_fragments(
                document_hash="test-hash",
                current_chunk_index=2,
                context_window=1,
            )

        assert result["document_hash"] == "test-hash"
        assert result["target_chunk_index"] == 2
        assert result["context_window"] == 1
        # Should include chunks 1, 2, 3 (context_window=1 around chunk 2)
        assert result["related_fragments_count"] == 3

    @pytest.mark.asyncio
    async def test_get_related_fragments_no_chunk_index(self):
        """Test getting all fragments when no chunk index specified."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {"chunk_index": "0", "content": "Part 0"},
                {"chunk_index": "1", "content": "Part 1"},
            ]
        )

        mock_deduplicator = MagicMock()
        mock_deduplicator.get_document_metadata = AsyncMock(return_value={})

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.pipelines.ingestion.deduplication.DocumentDeduplicator",
                return_value=mock_deduplicator,
            ),
        ):
            result = await get_related_document_fragments(
                document_hash="test-hash",
                current_chunk_index=None,  # No specific chunk
            )

        # Should return all fragments
        assert result["fragments_count"] == 2

    @pytest.mark.asyncio
    async def test_get_related_fragments_error_handling(self):
        """Test error handling in get_related_document_fragments."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
            new_callable=AsyncMock,
            side_effect=Exception("Database error"),
        ):
            result = await get_related_document_fragments(
                document_hash="test-hash",
                current_chunk_index=0,
            )

        assert result["document_hash"] == "test-hash"
        assert "error" in result
        assert "Database error" in result["error"]

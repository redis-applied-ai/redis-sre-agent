"""Tests for knowledge helper functions."""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.knowledge_helpers import (
    _dedupe_docs,
    _doc_matches_requested_version,
    get_all_document_fragments,
    get_pinned_documents_helper,
    get_related_document_fragments,
    get_skill_helper,
    get_support_ticket_helper,
    ingest_sre_document_helper,
    search_knowledge_base_helper,
    search_support_tickets_helper,
    skills_check_helper,
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
                    "doc_type": "runbook",
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
        assert result["results"][0]["doc_type"] == "runbook"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_with_doc_type_filter(self):
        """Test document type filtering."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {
                    "id": "doc-1",
                    "title": "Skill Doc",
                    "doc_type": "skill",
                    "version": "latest",
                },
                {
                    "id": "doc-2",
                    "title": "Ticket Doc",
                    "doc_type": "ticket",
                    "version": "latest",
                },
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
                query="documents",
                doc_type="skill",
                limit=10,
                include_special_document_types=True,
            )

        assert result["doc_type"] == "skill"
        assert result["results_count"] == 1
        assert result["results"][0]["id"] == "doc-1"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_support_ticket_filter(self):
        """`support_ticket` filter should match support_ticket docs."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {
                    "id": "doc-ticket",
                    "title": "Support Ticket",
                    "doc_type": "support_ticket",
                    "version": "latest",
                },
                {
                    "id": "doc-runbook",
                    "title": "Runbook",
                    "doc_type": "runbook",
                    "version": "latest",
                },
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
                query="tickets",
                doc_type="support_ticket",
                limit=10,
                include_special_document_types=True,
            )

        assert result["doc_type"] == "support_ticket"
        assert result["results_count"] == 1
        assert result["results"][0]["id"] == "doc-ticket"
        assert result["results"][0]["doc_type"] == "support_ticket"

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
    async def test_search_knowledge_base_latest_filters_versioned_source_paths(self):
        """Test latest filtering excludes versioned source paths from legacy docs."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {
                    "id": "doc-latest",
                    "title": "Latest doc",
                    "source": "https://github.com/redis/docs/blob/main/content/operate/rs/references/a.md",
                    "version": "latest",
                },
                {
                    "id": "doc-7-22",
                    "title": "Versioned doc",
                    "source": "https://github.com/redis/docs/blob/main/content/operate/rs/7.22/references/a.md",
                    "version": "latest",
                },
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
                version="latest",
                limit=10,
            )

        assert result["results_count"] == 1
        assert result["results"][0]["id"] == "doc-latest"
        assert result["results"][0]["version"] == "latest"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_specific_version_uses_fallback(self):
        """Test fallback query can recover versioned docs from legacy-tagged data."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            side_effect=[
                [],
                [
                    {
                        "id": "doc-7-22",
                        "title": "Versioned doc",
                        "source": "https://github.com/redis/docs/blob/main/content/operate/rs/7.22/references/a.md",
                        "version": "latest",
                    },
                    {
                        "id": "doc-latest",
                        "title": "Latest doc",
                        "source": "https://github.com/redis/docs/blob/main/content/operate/rs/references/a.md",
                        "version": "latest",
                    },
                ],
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
                version="7.22",
                limit=5,
            )

        assert mock_index.query.call_count == 2
        assert result["results_count"] == 1
        assert result["results"][0]["id"] == "doc-7-22"
        assert result["results"][0]["version"] == "7.22"

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


class TestSearchKnowledgeBaseVersionHelpers:
    """Test helper functions used by search_knowledge_base_helper."""

    def test_doc_matches_requested_version_none_matches_any(self):
        """None requested version should match all docs."""
        doc = {
            "source": "https://github.com/redis/docs/blob/main/content/operate/rs/7.22/references/a.md",
            "version": "latest",
        }
        assert _doc_matches_requested_version(doc, None) is True

    def test_dedupe_docs_removes_duplicates_and_preserves_order(self):
        """Duplicate docs should be removed while preserving first-seen order."""
        docs = [
            {"id": "a", "document_hash": "h1", "chunk_index": 0, "source": "s1"},
            {"id": "b", "document_hash": "h2", "chunk_index": 1, "source": "s2"},
            {"id": "a", "document_hash": "h1", "chunk_index": 0, "source": "s1"},
        ]

        deduped = _dedupe_docs(docs)

        assert [doc["id"] for doc in deduped] == ["a", "b"]


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
        assert result["doc_type"] == "knowledge"
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
                "redis_sre_agent.core.knowledge_helpers.get_skills_index",
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
                doc_type="skill",
                product_labels=["redis-cloud", "enterprise"],
            )

        assert result["status"] == "ingested"
        assert result["doc_type"] == "skill"
        # Verify the document was loaded with product labels
        call_args = mock_index.load.call_args
        doc_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert doc_data[0]["product_labels"] == "redis-cloud,enterprise"
        assert doc_data[0]["doc_type"] == "skill"
        assert doc_data[0]["pinned"] == "false"

    @pytest.mark.asyncio
    async def test_ingest_support_ticket_defaults_pinned_false(self):
        """Support tickets should store pinned=false to support tag filters."""
        mock_index = AsyncMock()
        mock_index.load = AsyncMock()

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed = AsyncMock(return_value=b"vector_bytes")

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_support_tickets_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            result = await ingest_sre_document_helper(
                title="Ticket 123",
                content="Customer incident details",
                source="support",
                category="incident",
                severity="warning",
                doc_type="support_ticket",
            )

        assert result["status"] == "ingested"
        assert result["doc_type"] == "support_ticket"
        call_args = mock_index.load.call_args
        doc_data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert doc_data[0]["pinned"] == "false"


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

    @pytest.mark.asyncio
    async def test_get_all_fragments_version_filter_uses_version_tag(self):
        """Version filtering should work when source URL does not encode version."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {
                    "chunk_index": "0",
                    "content": "Version 7.4 content",
                    "title": "Doc",
                    "source": "docs/path/no-version",
                    "version": "7.4",
                },
                {
                    "chunk_index": "1",
                    "content": "Version 7.2 content",
                    "title": "Doc",
                    "source": "docs/path/no-version",
                    "version": "7.2",
                },
            ]
        )

        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ):
            result = await get_all_document_fragments(
                document_hash="test-hash-versioned",
                include_metadata=False,
                version="7.4",
            )

        query_obj = mock_index.query.call_args.args[0]
        assert "version" in query_obj._return_fields
        assert result["fragments_count"] == 1
        assert result["fragments"][0]["content"] == "Version 7.4 content"


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


class TestSkillHelpers:
    """Tests for skill-specific helper functions."""

    @pytest.mark.asyncio
    async def test_skills_check_helper_lists_unique_skills(self):
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {
                    "id": "a-0",
                    "document_hash": "hash-a",
                    "chunk_index": 0,
                    "title": "Skill A",
                    "content": "First chunk",
                    "source": "docs/latest/a",
                    "doc_type": "skill",
                    "version": "latest",
                },
                {
                    "id": "a-1",
                    "document_hash": "hash-a",
                    "chunk_index": 1,
                    "title": "Skill A",
                    "content": "Second chunk",
                    "source": "docs/latest/a",
                    "doc_type": "skill",
                    "version": "latest",
                },
                {
                    "id": "b-0",
                    "document_hash": "hash-b",
                    "chunk_index": 0,
                    "title": "Skill B",
                    "content": "Only chunk",
                    "source": "docs/latest/b",
                    "doc_type": "skill",
                    "version": "latest",
                },
            ]
        )

        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_skills_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ):
            result = await skills_check_helper(limit=10, offset=0, version="latest")

        assert result["results_count"] == 2
        assert result["total_fetched"] == 2
        assert [skill["title"] for skill in result["skills"]] == ["Skill A", "Skill B"]
        assert [skill["document_hash"] for skill in result["skills"]] == ["hash-a", "hash-b"]

    @pytest.mark.asyncio
    async def test_skills_check_helper_legacy_query_uses_common_return_fields(self):
        class _QueryStub:
            def __init__(self, *, vector, vector_field_name, return_fields, num_results, **kwargs):
                self.vector = vector
                self.vector_field_name = vector_field_name
                self.return_fields = return_fields
                self.num_results = num_results
                self.kwargs = kwargs
                self.filter = None

            def set_filter(self, filter_expr):
                self.filter = filter_expr

        skills_index = AsyncMock()
        skills_index.query = AsyncMock(return_value=[])
        legacy_index = AsyncMock()
        legacy_index.query = AsyncMock(
            return_value=[
                {
                    "id": "legacy-0",
                    "document_hash": "legacy-hash",
                    "chunk_index": 0,
                    "title": "Legacy Skill",
                    "content": "Legacy content",
                    "source": "docs/latest/legacy",
                    "name": "Legacy Skill",
                    "summary": "Legacy summary",
                    "priority": "normal",
                    "pinned": "false",
                    "doc_type": "skill",
                    "version": "latest",
                }
            ]
        )
        vectorizer = MagicMock()
        vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2]])

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_skills_index",
                new_callable=AsyncMock,
                return_value=skills_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=legacy_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                return_value=vectorizer,
            ),
            patch("redis_sre_agent.core.knowledge_helpers.VectorQuery", _QueryStub),
            patch("redis_sre_agent.core.knowledge_helpers.VectorRangeQuery", _QueryStub),
        ):
            result = await skills_check_helper(query="memory issue", limit=10, offset=0)

        legacy_query = legacy_index.query.await_args.args[0]
        assert "meta_name" not in legacy_query.return_fields
        assert "meta_summary" not in legacy_query.return_fields
        assert result["results_count"] == 1

    @pytest.mark.asyncio
    async def test_get_skill_helper_returns_full_content_for_skill(self):
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {
                    "id": "skill-0",
                    "document_hash": "hash-skill",
                    "chunk_index": 0,
                    "name": "Incident Triage",
                    "title": "Skill Doc",
                    "source": "docs/latest/skill",
                    "doc_type": "skill",
                    "version": "latest",
                }
            ]
        )
        fragments_result = {
            "document_hash": "hash-skill",
            "title": "Skill Doc",
            "source": "docs/latest/skill",
            "doc_type": "skill",
            "fragments": [
                {"chunk_index": 0, "content": "Part 1"},
                {"chunk_index": 1, "content": "Part 2"},
            ],
            "metadata": {"owner": "sre"},
        }

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_skills_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.skills_check_helper",
                new_callable=AsyncMock,
                side_effect=AssertionError("should not call skills_check_helper on exact match"),
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
                new_callable=AsyncMock,
                return_value=fragments_result,
            ),
        ):
            result = await get_skill_helper(skill_name="Incident Triage")

        assert result["skill_name"] == "Incident Triage"
        assert result["full_content"] == "Part 1\n\nPart 2"
        assert "fragments" not in result
        assert "fragments_count" not in result

    @pytest.mark.asyncio
    async def test_get_skill_helper_rejects_non_skill_document(self):
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            return_value=[
                {
                    "id": "skill-0",
                    "document_hash": "hash-runbook",
                    "chunk_index": 0,
                    "name": "Incident Triage",
                    "title": "Runbook",
                    "source": "docs/latest/runbook",
                    "doc_type": "skill",
                    "version": "latest",
                }
            ]
        )
        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_skills_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.skills_check_helper",
                new_callable=AsyncMock,
                side_effect=AssertionError("should not call skills_check_helper on exact match"),
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
                new_callable=AsyncMock,
                return_value={
                    "document_hash": "hash-runbook",
                    "doc_type": "runbook",
                    "fragments": [{"chunk_index": 0, "content": "text"}],
                },
            ),
        ):
            result = await get_skill_helper(skill_name="Incident Triage")

        assert result["document_hash"] == "hash-runbook"
        assert result["doc_type"] == "runbook"
        assert "not 'skill'" in result["error"]

    @pytest.mark.asyncio
    async def test_get_skill_helper_uses_legacy_knowledge_index_type(self):
        skills_index = AsyncMock()
        skills_index.query = AsyncMock(return_value=[])
        legacy_index = AsyncMock()
        legacy_index.query = AsyncMock(
            return_value=[
                {
                    "id": "legacy-skill-0",
                    "document_hash": "hash-legacy",
                    "chunk_index": 0,
                    "name": "Legacy Skill",
                    "title": "Legacy Skill",
                    "source": "docs/latest/legacy-skill",
                    "doc_type": "skill",
                    "version": "latest",
                }
            ]
        )

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_skills_index",
                new_callable=AsyncMock,
                return_value=skills_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=legacy_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
                new_callable=AsyncMock,
                return_value={
                    "document_hash": "hash-legacy",
                    "doc_type": "skill",
                    "fragments": [{"chunk_index": 0, "content": "Legacy content"}],
                },
            ) as mock_get_all,
        ):
            result = await get_skill_helper(skill_name="Legacy Skill")

        assert result["skill_name"] == "Legacy Skill"
        first_call_kwargs = mock_get_all.await_args_list[0].kwargs
        assert first_call_kwargs["index_type"] == "knowledge"

    @pytest.mark.asyncio
    async def test_get_skill_helper_filter_query_supports_required_filter_expression(self):
        """Guard against redisvl versions requiring filter_expression in FilterQuery."""

        class _StrictFilterQuery:
            def __init__(self, *, filter_expression, return_fields, num_results):
                self.filter_expression = filter_expression
                self.return_fields = return_fields
                self.num_results = num_results

            def set_filter(self, _filter):
                self._filter = _filter

        skills_index = AsyncMock()
        skills_index.query = AsyncMock(return_value=[])
        knowledge_index = AsyncMock()
        knowledge_index.query = AsyncMock(return_value=[])

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.FilterQuery",
                _StrictFilterQuery,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_skills_index",
                new_callable=AsyncMock,
                return_value=skills_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=knowledge_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.skills_check_helper",
                new_callable=AsyncMock,
                return_value={"skills": []},
            ),
        ):
            result = await get_skill_helper(skill_name="Not Found")

        assert result["error"] == "Skill not found"


class TestSupportTicketHelpers:
    @pytest.mark.asyncio
    async def test_search_support_tickets_helper_normalizes_ticket_id_from_chunk_key(self):
        with patch(
            "redis_sre_agent.core.knowledge_helpers.search_knowledge_base_helper",
            new_callable=AsyncMock,
            return_value={
                "results": [
                    {
                        "id": "sre_support_tickets:abc123def456:chunk:0",
                        "title": "Ticket A",
                        "doc_type": "support_ticket",
                    }
                ]
            },
        ):
            result = await search_support_tickets_helper(query="cache-prod-1 failover")

        assert result["tickets"][0]["ticket_id"] == "abc123def456"

    @pytest.mark.asyncio
    async def test_get_support_ticket_helper_normalizes_chunk_key_input(self):
        mock_fragments = {
            "document_hash": "abc123def456",
            "doc_type": "support_ticket",
            "title": "Ticket A",
            "source": "source",
            "fragments": [{"chunk_index": 0, "content": "body", "doc_type": "support_ticket"}],
            "metadata": {},
        }

        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
            new_callable=AsyncMock,
            return_value=mock_fragments,
        ) as mock_get_fragments:
            result = await get_support_ticket_helper(
                ticket_id="sre_support_tickets:abc123def456:chunk:0"
            )

        call_kwargs = mock_get_fragments.await_args.kwargs
        assert call_kwargs["document_hash"] == "abc123def456"
        assert result["document_hash"] == "abc123def456"


class TestPinnedDocumentsHelper:
    @pytest.mark.asyncio
    async def test_get_pinned_documents_includes_skills_and_support_tickets(self):
        knowledge_index = AsyncMock()
        knowledge_index.query = AsyncMock(
            return_value=[
                {
                    "id": "knowledge:doc-1:chunk:0",
                    "document_hash": "doc-1",
                    "chunk_index": 0,
                    "name": "Pinned KB",
                    "title": "Pinned KB",
                    "content": "Pinned KB content",
                    "source": "docs/latest/kb",
                    "priority": "high",
                    "pinned": "true",
                    "doc_type": "runbook",
                    "version": "latest",
                },
                {
                    "id": "knowledge:skill-1:chunk:0",
                    "document_hash": "skill-1",
                    "chunk_index": 0,
                    "name": "Pinned Skill",
                    "title": "Pinned Skill",
                    "content": "Legacy skill content",
                    "source": "docs/latest/legacy-skill",
                    "priority": "critical",
                    "pinned": "true",
                    "doc_type": "skill",
                    "version": "latest",
                },
            ]
        )
        skills_index = AsyncMock()
        skills_index.query = AsyncMock(
            return_value=[
                {
                    "id": "skills:skill-1:chunk:0",
                    "document_hash": "skill-1",
                    "chunk_index": 0,
                    "name": "Pinned Skill",
                    "title": "Pinned Skill",
                    "content": "Dedicated skill content",
                    "source": "source_documents/shared/skills/pinned-skill",
                    "priority": "critical",
                    "pinned": "true",
                    "doc_type": "skill",
                    "version": "latest",
                }
            ]
        )
        tickets_index = AsyncMock()
        tickets_index.query = AsyncMock(
            return_value=[
                {
                    "id": "tickets:ticket-1:chunk:0",
                    "document_hash": "ticket-1",
                    "chunk_index": 0,
                    "name": "Pinned Ticket",
                    "title": "Pinned Ticket",
                    "content": "Pinned ticket content",
                    "source": "source_documents/shared/support/ticket-1",
                    "priority": "high",
                    "pinned": "true",
                    "doc_type": "support_ticket",
                    "version": "latest",
                }
            ]
        )

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=knowledge_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_skills_index",
                new_callable=AsyncMock,
                return_value=skills_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_support_tickets_index",
                new_callable=AsyncMock,
                return_value=tickets_index,
            ),
        ):
            result = await get_pinned_documents_helper(version="latest", limit=10)

        assert result["results_count"] == 3
        by_name = {doc["name"]: doc for doc in result["pinned_documents"]}
        assert by_name["Pinned Skill"]["doc_type"] == "skill"
        assert by_name["Pinned Skill"]["full_content"] == "Dedicated skill content"
        assert by_name["Pinned Ticket"]["doc_type"] == "support_ticket"
        assert by_name["Pinned KB"]["doc_type"] == "runbook"

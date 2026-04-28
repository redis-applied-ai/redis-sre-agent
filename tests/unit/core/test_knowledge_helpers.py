"""Tests for knowledge helper functions."""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import redis_sre_agent.core.knowledge_helpers as knowledge_helpers
from redis_sre_agent.core.knowledge_helpers import (
    _dedupe_docs,
    _doc_matches_requested_version,
    _exact_match_sort_key,
    _quoted_text_phrase_query,
    _RawTextQuery,
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
from redis_sre_agent.evaluation.injection import eval_runtime_overrides


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

    def test_exact_match_sort_key_ranks_source_and_non_match_after_name_and_hash(self):
        """Source equality should outrank unrelated rows in exact-match ordering."""
        source_match = {
            "document_hash": "hash-1",
            "chunk_index": 0,
            "source": "ticket-ret-4421.md",
        }
        non_match = {
            "document_hash": "hash-2",
            "chunk_index": 1,
            "source": "other.md",
        }

        assert _exact_match_sort_key(source_match, "ticket-ret-4421.md")[0] == 2
        assert _exact_match_sort_key(non_match, "ticket-ret-4421.md")[0] == 3

    def test_tag_equals_expression_uses_canonical_tag_syntax(self):
        """Exact TAG filters should use escaped canonical syntax, not quoted values."""
        assert str(knowledge_helpers._tag_equals_expression("name", "INC432323")) == (
            "@name:{INC432323}"
        )
        assert str(knowledge_helpers._tag_equals_expression("name", "foo|bar/baz[prod]")) == (
            r"@name:{foo\|bar\/baz\[prod\]}"
        )

    def test_hybrid_unsupported_error_detector_avoids_generic_ft_hybrid_mentions(self):
        """Only explicit capability/command failures should trip the fallback detector."""
        assert knowledge_helpers._is_hybrid_query_unsupported_error(
            RuntimeError("ERR unknown command 'FT.HYBRID'")
        )
        assert knowledge_helpers._is_hybrid_query_unsupported_error(
            RuntimeError("ERR no such command 'FT.HYBRID'")
        )
        assert not knowledge_helpers._is_hybrid_query_unsupported_error(
            RuntimeError("transport failure while issuing FT.HYBRID request")
        )
        assert not knowledge_helpers._is_hybrid_query_unsupported_error(
            RuntimeError("ERR no such index")
        )


class TestSearchKnowledgeBaseHelper:
    """Test search_knowledge_base_helper function."""

    @pytest.mark.asyncio
    async def test_search_knowledge_base_uses_eval_backend_override(self):
        """Eval-scoped overrides should bypass the global vectorized knowledge path."""

        class FakeKnowledgeBackend:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict[str, object]]] = []

            async def search_knowledge_base(self, **kwargs):
                self.calls.append(("search_knowledge_base", kwargs))
                return {
                    "query": kwargs["query"],
                    "results": [{"title": "Scenario doc", "doc_type": "runbook"}],
                    "results_count": 1,
                }

        backend = FakeKnowledgeBackend()

        with (
            eval_runtime_overrides(knowledge_backend=backend),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                side_effect=AssertionError("global vectorizer should not be used"),
            ),
        ):
            result = await search_knowledge_base_helper(
                query="redis memory",
                limit=3,
                version="latest",
            )

        assert result["results_count"] == 1
        assert result["results"][0]["title"] == "Scenario doc"
        assert backend.calls == [
            (
                "search_knowledge_base",
                {
                    "query": "redis memory",
                    "category": None,
                    "doc_type": None,
                    "limit": 3,
                    "offset": 0,
                    "distance_threshold": 0.8,
                    "hybrid_search": False,
                    "version": "latest",
                    "index_type": "knowledge",
                    "include_special_document_types": False,
                },
            )
        ]

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
    async def test_search_knowledge_base_treats_none_offset_as_zero(self):
        """Knowledge helper should normalize nullable pagination values."""
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
                limit=3,
                offset=None,
            )

        assert result["offset"] == 0
        assert result["limit"] == 3
        assert result["results_count"] == 1

    @pytest.mark.asyncio
    async def test_search_knowledge_base_promotes_exact_name_match(self):
        """Exact tag matches should appear ahead of semantic-only matches."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            side_effect=[
                [
                    {
                        "id": "doc-exact",
                        "document_hash": "hash-exact",
                        "chunk_index": 0,
                        "title": "RET-4421 incident",
                        "content": "Exact incident record",
                        "source": "tickets",
                        "category": "incident",
                        "doc_type": "runbook",
                        "name": "ret-4421",
                        "version": "latest",
                    }
                ],
                [],
                [],
                [],
                [
                    {
                        "id": "doc-semantic",
                        "document_hash": "hash-semantic",
                        "chunk_index": 0,
                        "title": "Similar issue",
                        "content": "Related ticket analysis",
                        "source": "docs",
                        "category": "incident",
                        "doc_type": "runbook",
                        "name": "incident-analysis",
                        "version": "latest",
                        "score": 0.2,
                    }
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
            result = await search_knowledge_base_helper(query="ret-4421", limit=10)

        assert result["results_count"] == 2
        assert result["results"][0]["id"] == "doc-exact"
        assert result["results"][0]["name"] == "ret-4421"
        assert result["results"][1]["id"] == "doc-semantic"
        assert mock_index.query.await_args_list[3].args[0].__class__.__name__ == "_RawTextQuery"
        assert mock_index.query.await_args_list[4].args[0].__class__.__name__ == "HybridQuery"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_promotes_exact_document_hash_match(self):
        """Exact document_hash hits should be surfaced before semantic matches."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            side_effect=[
                [],
                [
                    {
                        "id": "doc-exact",
                        "document_hash": "abc123def456",
                        "chunk_index": 0,
                        "title": "Exact doc",
                        "content": "Exact hash match",
                        "source": "docs",
                        "category": "general",
                        "doc_type": "runbook",
                        "version": "latest",
                    }
                ],
                [],
                [],
                [
                    {
                        "id": "doc-semantic",
                        "document_hash": "zzz999",
                        "chunk_index": 0,
                        "title": "Approximate doc",
                        "content": "Approximate result",
                        "source": "docs",
                        "category": "general",
                        "doc_type": "runbook",
                        "version": "latest",
                        "score": 0.3,
                    }
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
            result = await search_knowledge_base_helper(query="abc123def456", limit=10)

        assert result["results_count"] == 2
        assert result["results"][0]["document_hash"] == "abc123def456"
        assert result["results"][1]["id"] == "doc-semantic"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_identifier_query_runs_literal_text_query(self):
        """Identifier-like queries should search TEXT fields even without wrapping quotes."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            side_effect=[
                [],
                [],
                [],
                [
                    {
                        "id": "doc-phrase",
                        "document_hash": "hash-phrase",
                        "chunk_index": 0,
                        "title": "Follow-up incident",
                        "content": "See RET-4421 for the original incident timeline.",
                        "source": "alerts",
                        "category": "incident",
                        "doc_type": "runbook",
                        "version": "latest",
                        "score": 5.0,
                    }
                ],
                [
                    {
                        "id": "doc-semantic",
                        "document_hash": "hash-semantic",
                        "chunk_index": 0,
                        "title": "Memory pressure",
                        "content": "Related semantic result",
                        "source": "docs",
                        "category": "incident",
                        "doc_type": "runbook",
                        "version": "latest",
                        "score": 0.2,
                    }
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
            result = await search_knowledge_base_helper(query="RET-4421", limit=10)

        literal_query = str(mock_index.query.await_args_list[3].args[0])
        assert '@title:("ret-4421")' in literal_query
        assert '@summary:("ret-4421")' in literal_query
        assert '@content:("ret-4421")' in literal_query
        assert result["results_count"] == 2
        assert result["results"][0]["id"] == "doc-phrase"
        assert result["results"][1]["id"] == "doc-semantic"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_quoted_phrase_runs_literal_text_query(self):
        """Quoted input should trigger a literal phrase query over TEXT fields."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            side_effect=[
                [],
                [],
                [],
                [
                    {
                        "id": "doc-phrase",
                        "document_hash": "hash-phrase",
                        "chunk_index": 0,
                        "title": "DB memory full",
                        "content": "Alert: DB memory full on cluster.",
                        "source": "alerts",
                        "category": "incident",
                        "doc_type": "runbook",
                        "version": "latest",
                        "score": 5.0,
                    }
                ],
                [
                    {
                        "id": "doc-semantic",
                        "document_hash": "hash-semantic",
                        "chunk_index": 0,
                        "title": "Memory pressure",
                        "content": "Related semantic result",
                        "source": "docs",
                        "category": "incident",
                        "doc_type": "runbook",
                        "version": "latest",
                        "score": 0.2,
                    }
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
            result = await search_knowledge_base_helper(query='"DB memory full"', limit=10)

        literal_query = str(mock_index.query.await_args_list[3].args[0])
        assert '@title:("db memory full")' in literal_query
        assert '@summary:("db memory full")' in literal_query
        assert '@content:("db memory full")' in literal_query
        assert result["results_count"] == 2
        assert result["results"][0]["id"] == "doc-phrase"
        assert mock_index.query.await_args_list[4].args[0].__class__.__name__ == "HybridQuery"

    def test_quoted_text_phrase_query_uses_implicit_and_for_filters(self):
        """Phrase queries should only contain the literal TEXT search expression."""
        query = _quoted_text_phrase_query("DB memory full")

        assert " AND " not in query
        assert "@version:{latest}" not in query
        assert '@title:("db memory full")' in query

    def test_raw_text_query_uses_implicit_and_for_filters(self):
        """Raw text queries should concatenate filters without a literal AND token."""
        query = _RawTextQuery(
            '@content:("db memory full")',
            filter_expression="@version:{latest}",
            num_results=5,
        )

        assert " AND " not in str(query)
        assert '@content:("db memory full") @version:{latest}' in str(query)

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
        mock_index.query = AsyncMock(side_effect=[[], []])

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
        """Test latest filtering excludes versioned source paths."""
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
    async def test_search_knowledge_base_specific_version_does_not_use_unfiltered_fallback(self):
        """Versioned searches should not run an unfiltered second query."""
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
                version="7.22",
                limit=5,
            )

        assert mock_index.query.call_count == 1
        assert result["results_count"] == 0

    @pytest.mark.asyncio
    async def test_search_knowledge_base_hybrid_search(self):
        """Hybrid search alone should not trigger exact/literal prequeries."""
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
        assert mock_index.query.call_count == 1
        assert mock_index.query.await_args_list[0].args[0].__class__.__name__ == "HybridQuery"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_hybrid_falls_back_to_rrf_when_unsupported(self):
        """Older RediSearch deployments should fall back to separate text/vector queries."""
        knowledge_helpers._HYBRID_UNSUPPORTED_INDEX_TYPES.clear()
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            side_effect=[
                RuntimeError("Syntax error at offset 42 near YIELD_DISTANCE_AS"),
                [
                    {
                        "id": "doc-text",
                        "document_hash": "hash-text",
                        "chunk_index": 0,
                        "title": "Redis memory guide",
                        "content": "Tune memory fragmentation first.",
                        "source": "docs",
                        "category": "monitoring",
                        "doc_type": "runbook",
                        "version": "latest",
                        "score": 5.0,
                    }
                ],
                [
                    {
                        "id": "doc-vector",
                        "document_hash": "hash-vector",
                        "chunk_index": 0,
                        "title": "Latency checklist",
                        "content": "Check allocator pressure and swap activity.",
                        "source": "docs",
                        "category": "monitoring",
                        "doc_type": "runbook",
                        "version": "latest",
                        "vector_distance": 0.15,
                    }
                ],
            ]
        )

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

        try:
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
        finally:
            knowledge_helpers._HYBRID_UNSUPPORTED_INDEX_TYPES.clear()

        assert result["results_count"] == 2
        assert [doc["id"] for doc in result["results"]] == ["doc-text", "doc-vector"]
        assert mock_index.query.await_args_list[0].args[0].__class__.__name__ == "HybridQuery"
        assert mock_index.query.await_args_list[1].args[0].__class__.__name__ == "_RawTextQuery"
        assert mock_index.query.await_args_list[2].args[0].__class__.__name__ == "VectorQuery"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_hybrid_falls_back_to_rrf_on_unknown_command(self):
        """Servers that reject FT.HYBRID outright should still fall back cleanly."""
        knowledge_helpers._HYBRID_UNSUPPORTED_INDEX_TYPES.clear()
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            side_effect=[
                RuntimeError("ERR unknown command 'FT.HYBRID'"),
                [
                    {
                        "id": "doc-text",
                        "document_hash": "hash-text",
                        "chunk_index": 0,
                        "title": "Redis memory guide",
                        "content": "Tune memory fragmentation first.",
                        "source": "docs",
                        "category": "monitoring",
                        "doc_type": "runbook",
                        "version": "latest",
                        "score": 5.0,
                    }
                ],
                [
                    {
                        "id": "doc-vector",
                        "document_hash": "hash-vector",
                        "chunk_index": 0,
                        "title": "Latency checklist",
                        "content": "Check allocator pressure and swap activity.",
                        "source": "docs",
                        "category": "monitoring",
                        "doc_type": "runbook",
                        "version": "latest",
                        "vector_distance": 0.15,
                    }
                ],
            ]
        )

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

        try:
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
        finally:
            knowledge_helpers._HYBRID_UNSUPPORTED_INDEX_TYPES.clear()

        assert result["results_count"] == 2
        assert [doc["id"] for doc in result["results"]] == ["doc-text", "doc-vector"]
        assert mock_index.query.await_args_list[0].args[0].__class__.__name__ == "HybridQuery"
        assert mock_index.query.await_args_list[1].args[0].__class__.__name__ == "_RawTextQuery"
        assert mock_index.query.await_args_list[2].args[0].__class__.__name__ == "VectorQuery"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_hybrid_uses_cached_rrf_fallback(self):
        """Once a server is known to lack HybridQuery support, skip the failing probe."""
        knowledge_helpers._HYBRID_UNSUPPORTED_INDEX_TYPES.clear()
        knowledge_helpers._HYBRID_UNSUPPORTED_INDEX_TYPES.add("knowledge")
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            side_effect=[
                [
                    {
                        "id": "doc-text",
                        "document_hash": "hash-text",
                        "chunk_index": 0,
                        "title": "Redis memory guide",
                        "content": "Tune memory fragmentation first.",
                        "source": "docs",
                        "category": "monitoring",
                        "doc_type": "runbook",
                        "version": "latest",
                        "score": 5.0,
                    }
                ],
                [
                    {
                        "id": "doc-vector",
                        "document_hash": "hash-vector",
                        "chunk_index": 0,
                        "title": "Latency checklist",
                        "content": "Check allocator pressure and swap activity.",
                        "source": "docs",
                        "category": "monitoring",
                        "doc_type": "runbook",
                        "version": "latest",
                        "vector_distance": 0.15,
                    }
                ],
            ]
        )

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

        try:
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
        finally:
            knowledge_helpers._HYBRID_UNSUPPORTED_INDEX_TYPES.clear()

        assert result["results_count"] == 2
        assert mock_index.query.call_count == 2
        assert mock_index.query.await_args_list[0].args[0].__class__.__name__ == "_RawTextQuery"
        assert mock_index.query.await_args_list[1].args[0].__class__.__name__ == "VectorQuery"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_natural_language_query_skips_exact_prequery(self):
        """Natural-language searches should not pay for exact TAG/TEXT probes."""
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
                query="how do I tune memory",
                limit=10,
            )

        assert result["results_count"] == 0
        mock_index.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_knowledge_base_category_fallback_runs_precise_text_query_for_identifier(
        self,
    ):
        """Category fallback should retry literal TEXT matching for exact-looking queries."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            side_effect=[
                [],
                [],
                [],
                [],
                [],
                [],
                [],
                [],
                [],
                [
                    {
                        "id": "doc-fallback-phrase",
                        "document_hash": "hash-fallback",
                        "chunk_index": 0,
                        "title": "Follow-up incident",
                        "content": "RET-4421 shows the linked failover issue.",
                        "source": "alerts",
                        "category": "incident",
                        "doc_type": "runbook",
                        "version": "latest",
                        "score": 5.0,
                    }
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
                query="RET-4421",
                category="incident",
                version=None,
                limit=10,
            )

        assert result["results_count"] == 1
        assert result["results"][0]["id"] == "doc-fallback-phrase"
        assert mock_index.query.call_count == 10
        assert mock_index.query.await_args_list[9].args[0].__class__.__name__ == "_RawTextQuery"

    @pytest.mark.asyncio
    async def test_search_knowledge_base_category_fallback_skips_exact_prequery_for_natural_language_hybrid(
        self,
    ):
        """Category fallback should not run exact TAG/TEXT probes for ordinary hybrid queries."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(side_effect=[[], []])

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
                query="redis memory tuning",
                category="incident",
                hybrid_search=True,
                limit=10,
            )

        assert result["results_count"] == 0
        assert mock_index.query.call_count == 2
        assert mock_index.query.await_args_list[0].args[0].__class__.__name__ == "HybridQuery"
        assert mock_index.query.await_args_list[1].args[0].__class__.__name__ == "HybridQuery"

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
        assert mock_index.query.call_count == 1


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

    @pytest.mark.asyncio
    async def test_get_all_fragments_uses_filter_expression_object(self):
        """Fragment lookup should pass a FilterExpression, not a raw string."""

        class _StrictFilterQuery:
            def __init__(self, *, filter_expression, return_fields, num_results, dialect=2):
                if isinstance(filter_expression, str):
                    raise TypeError("filter_expression must be a FilterExpression")
                self._filter_expression = filter_expression
                self._return_fields = return_fields
                self.num_results = num_results
                self.dialect = dialect

        mock_index = AsyncMock()
        mock_index.query = AsyncMock(return_value=[])

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.FilterQuery",
                _StrictFilterQuery,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
        ):
            result = await get_all_document_fragments(document_hash="test-hash-123")

        assert result["document_hash"] == "test-hash-123"
        assert result["fragments"] == []


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
                "redis_sre_agent.core.knowledge_helpers.skills_check_helper",
                new_callable=AsyncMock,
                return_value={"skills": []},
            ),
        ):
            result = await get_skill_helper(skill_name="Not Found")

        assert result["error"] == "Skill not found"

    @pytest.mark.asyncio
    async def test_skills_check_helper_uses_filter_expression_object(self):
        """Guard against redisvl versions that reject raw string filter expressions."""

        class _StrictFilterQuery:
            def __init__(self, *, filter_expression, return_fields, num_results):
                if isinstance(filter_expression, str):
                    raise TypeError("filter_expression must be a FilterExpression")
                self.filter_expression = filter_expression
                self.return_fields = return_fields
                self.num_results = num_results

        skills_index = AsyncMock()
        skills_index.query = AsyncMock(return_value=[])
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
        ):
            result = await skills_check_helper(query=None, limit=10, offset=0, version="latest")

        assert result["results_count"] == 0

    @pytest.mark.asyncio
    async def test_skills_check_helper_normalizes_limit_offset_before_backend(self):
        backend = MagicMock()
        backend.list_skills = AsyncMock(return_value={"results_count": 0, "skills": []})

        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_skill_backend",
            return_value=backend,
        ):
            await skills_check_helper(query=None, limit="7", offset="-2", version="latest")

        backend.list_skills.assert_awaited_once_with(
            query=None,
            limit=7,
            offset=0,
            version="latest",
            distance_threshold=0.8,
        )


class TestSupportTicketHelpers:
    @pytest.mark.asyncio
    async def test_find_support_ticket_exact_matches_runs_one_query_per_exact_tag_field(self):
        support_tickets_index = AsyncMock()
        matching_doc = {
            "id": "sre_support_tickets:ticket-hash:chunk:0",
            "document_hash": "ticket-hash",
            "chunk_index": 0,
            "title": "Incident ticket",
            "content": "Exact match content",
            "source": "foo|bar/baz[prod]",
            "doc_type": "support_ticket",
            "name": "foo|bar/baz[prod]",
            "version": "latest",
        }
        support_tickets_index.query = AsyncMock(
            side_effect=[[matching_doc], [matching_doc], [matching_doc]]
        )

        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_support_tickets_index",
            new_callable=AsyncMock,
            return_value=support_tickets_index,
        ):
            result = await knowledge_helpers._find_support_ticket_exact_matches(
                query="foo|bar/baz[prod]",
                version="latest",
            )

        assert len(result) == 1
        assert result[0]["document_hash"] == "ticket-hash"
        assert support_tickets_index.query.await_count == len(
            knowledge_helpers._EXACT_MATCH_TAG_FIELDS
        )

        expected_field_filters = (
            r"@name:{foo\|bar\/baz\[prod\]}",
            r"@document_hash:{foo\|bar\/baz\[prod\]}",
            r"@source:{foo\|bar\/baz\[prod\]}",
        )
        observed_filters = [
            str(call.args[0]._filter_expression)
            for call in support_tickets_index.query.await_args_list
        ]

        for expected_filter, observed_filter in zip(expected_field_filters, observed_filters):
            assert expected_filter in observed_filter
            assert "@doc_type:{support_ticket}" in observed_filter
            assert "@version:{latest}" in observed_filter
            assert '"foo|bar/baz[prod]"' not in observed_filter

    @pytest.mark.asyncio
    async def test_search_support_tickets_helper_normalizes_ticket_id_from_chunk_key(self):
        with (
            patch(
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
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers._find_support_ticket_exact_matches",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await search_support_tickets_helper(query="cache-prod-1 failover")

        assert result["tickets"][0]["ticket_id"] == "abc123def456"

    @pytest.mark.asyncio
    async def test_search_support_tickets_helper_prefers_stable_ticket_name(self):
        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.search_knowledge_base_helper",
                new_callable=AsyncMock,
                return_value={
                    "results": [
                        {
                            "id": "sre_support_tickets:abc123def456:chunk:0",
                            "document_hash": "abc123def456",
                            "name": "ret-4421",
                            "title": "Ticket RET-4421",
                            "doc_type": "support_ticket",
                        }
                    ]
                },
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers._find_support_ticket_exact_matches",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await search_support_tickets_helper(query="ret-4421")

        assert result["tickets"][0]["ticket_id"] == "ret-4421"

    @pytest.mark.asyncio
    async def test_search_support_tickets_helper_restores_requested_pagination_metadata(self):
        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.search_knowledge_base_helper",
                new_callable=AsyncMock,
                return_value={
                    "offset": 0,
                    "limit": 4,
                    "results": [
                        {"id": "ticket-1", "document_hash": "a", "title": "Ticket 1"},
                        {"id": "ticket-2", "document_hash": "b", "title": "Ticket 2"},
                        {"id": "ticket-3", "document_hash": "c", "title": "Ticket 3"},
                    ],
                },
            ) as mock_search,
            patch(
                "redis_sre_agent.core.knowledge_helpers._find_support_ticket_exact_matches",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await search_support_tickets_helper(query="ret-4421", limit=2, offset=1)

        mock_search.assert_awaited_once()
        assert result["offset"] == 1
        assert result["limit"] == 2
        assert result["ticket_count"] == 2
        assert [ticket["id"] for ticket in result["tickets"]] == ["ticket-2", "ticket-3"]

    @pytest.mark.asyncio
    async def test_search_support_tickets_helper_overfetches_to_cover_dedupe(self):
        with patch(
            "redis_sre_agent.core.knowledge_helpers.search_knowledge_base_helper",
            new_callable=AsyncMock,
            return_value={"results": []},
        ) as mock_search:
            await search_support_tickets_helper(
                query="cache-prod-1 failover",
                limit=2,
                offset=0,
                version=None,
            )

        mock_search.assert_awaited_once_with(
            query="cache-prod-1 failover",
            limit=4,
            offset=0,
            distance_threshold=0.8,
            hybrid_search=False,
            version=None,
            config=None,
            index_type="support_tickets",
        )

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

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers._find_support_ticket_exact_matches",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
                new_callable=AsyncMock,
                return_value=mock_fragments,
            ) as mock_get_fragments,
        ):
            result = await get_support_ticket_helper(
                ticket_id="sre_support_tickets:abc123def456:chunk:0"
            )

        call_kwargs = mock_get_fragments.await_args.kwargs
        assert call_kwargs["document_hash"] == "abc123def456"
        assert result["document_hash"] == "abc123def456"

    @pytest.mark.asyncio
    async def test_get_support_ticket_helper_resolves_stable_ticket_name(self):
        mock_fragments = {
            "document_hash": "abc123def456",
            "doc_type": "support_ticket",
            "title": "Ticket RET-4421",
            "source": "source",
            "fragments": [{"chunk_index": 0, "content": "body", "doc_type": "support_ticket"}],
            "metadata": {},
        }
        support_tickets_index = AsyncMock()
        support_tickets_index.query = AsyncMock(
            return_value=[
                {
                    "id": "sre_support_tickets:abc123def456:chunk:0",
                    "document_hash": "abc123def456",
                    "name": "ret-4421",
                    "title": "Ticket RET-4421",
                    "doc_type": "support_ticket",
                    "source": "source",
                    "chunk_index": 0,
                    "content": "body",
                    "version": "latest",
                }
            ]
        )

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_support_tickets_index",
                new_callable=AsyncMock,
                return_value=support_tickets_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
                new_callable=AsyncMock,
                return_value=mock_fragments,
            ) as mock_get_fragments,
        ):
            result = await get_support_ticket_helper(ticket_id="ret-4421")

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
                    "content": "Pinned skill content",
                    "source": "docs/latest/pinned-skill",
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

    @pytest.mark.asyncio
    async def test_get_pinned_documents_uses_filter_expression_object(self):
        """Guard against redisvl versions that reject raw string filter expressions."""

        class _StrictFilterQuery:
            def __init__(self, *, filter_expression, return_fields, num_results):
                if isinstance(filter_expression, str):
                    raise TypeError("filter_expression must be a FilterExpression")
                self.filter_expression = filter_expression
                self.return_fields = return_fields
                self.num_results = num_results

        mock_index = AsyncMock()
        mock_index.query = AsyncMock(return_value=[])
        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.FilterQuery",
                _StrictFilterQuery,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_skills_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_support_tickets_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
        ):
            result = await get_pinned_documents_helper(version="latest", limit=10)

        assert result["results_count"] == 0

    @pytest.mark.asyncio
    async def test_get_pinned_documents_falls_back_when_pinned_field_missing(self):
        """Older indices without a pinned field should not emit hard warnings or fail."""

        class _FallbackIndex:
            def __init__(self, rows):
                self.rows = rows
                self.calls = 0

            async def query(self, query):
                self.calls += 1
                filter_expr = getattr(query, "_filter_expression", None)
                if self.calls == 1 and "pinned" in str(filter_expr):
                    raise RuntimeError(
                        "Error while searching: unknown field at offset 0 near pinned"
                    )
                return self.rows

        knowledge_index = AsyncMock()
        knowledge_index.query = AsyncMock(return_value=[])
        skills_index = _FallbackIndex(
            [
                {
                    "id": "skill-1",
                    "document_hash": "skill-1",
                    "chunk_index": 0,
                    "title": "Pinned Skill",
                    "content": "Dedicated skill content",
                    "source": "skills/pinned.md",
                    "name": "Pinned Skill",
                    "priority": "critical",
                    "pinned": "true",
                    "doc_type": "skill",
                    "version": "latest",
                }
            ]
        )
        tickets_index = _FallbackIndex([])

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

        assert result["results_count"] == 1
        assert result["pinned_documents"][0]["name"] == "Pinned Skill"
        assert skills_index.calls == 2

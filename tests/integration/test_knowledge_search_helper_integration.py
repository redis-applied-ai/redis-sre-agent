"""Integration tests for search_knowledge_base_helper with a live Redis via testcontainers.

These tests exercise the new distance_threshold behavior (default ON) and ensure
'score' is returned in results when using RedisVL queries.
"""

from array import array
from typing import List
from unittest.mock import patch

import pytest

from redis_sre_agent.core.knowledge_helpers import (
    search_knowledge_base_helper,
    search_support_tickets_helper,
)
from redis_sre_agent.core.redis import (
    SRE_KNOWLEDGE_INDEX,
    SRE_SUPPORT_TICKETS_INDEX,
    create_indices,
    get_knowledge_index,
    get_support_tickets_index,
)

VECTOR_DIM = 1536


def _vec(first_one_index: int) -> List[float]:
    v = [0.0] * VECTOR_DIM
    v[first_one_index] = 1.0
    return v


class MockVectorizer:
    def __init__(self, query_vec, doc_vecs_by_content):
        self._query_vec = query_vec
        self._doc_vecs_by_content = doc_vecs_by_content

    async def aembed_many(self, texts: List[str]):
        # Only the first query vector is used by the helper
        return [self._query_vec for _ in texts]

    async def aembed(self, text: str, as_buffer: bool = False):
        import numpy as np

        vec = self._doc_vecs_by_content.get(text)
        if vec is None:
            vec = [0.0] * VECTOR_DIM
        arr = np.array(vec, dtype=np.float32)
        return arr.tobytes() if as_buffer else arr


def _vec_buffer(vec: List[float]) -> bytes:
    return array("f", vec).tobytes()


def _doc(
    *,
    doc_id: str,
    title: str,
    content: str,
    source: str,
    category: str = "alpha",
    severity: str = "info",
    doc_type: str = "knowledge",
    name: str | None = None,
    summary: str = "",
    priority: str = "normal",
    pinned: str = "false",
    version: str = "latest",
    document_hash: str = "",
    content_hash: str = "",
    chunk_index: int = 0,
    vector: bytes,
) -> dict:
    return {
        "id": doc_id,
        "title": title,
        "content": content,
        "source": source,
        "category": category,
        "severity": severity,
        "doc_type": doc_type,
        "name": name or title,
        "summary": summary,
        "priority": priority,
        "pinned": pinned,
        "version": version,
        "document_hash": document_hash,
        "content_hash": content_hash,
        "chunk_index": chunk_index,
        "created_at": 0,
        "vector": vector,
    }


async def _load_docs(index, prefix: str, docs: List[dict]) -> None:
    keys = [f"{prefix}:{doc['id']}" for doc in docs]
    await index.load(id_field="id", keys=keys, data=docs)


@pytest.mark.integration
class TestKnowledgeSearchHelper:
    @pytest.mark.asyncio
    async def test_distance_threshold_filters_results(self, test_settings, async_redis_client):
        # Ensure indices exist and DB is clean (async_redis_client fixture flushes)
        await create_indices(config=test_settings)
        index = await get_knowledge_index(config=test_settings)

        # Prepare deterministic vectors: doc A ~ query, doc B far away
        doc_a_content = "Doc A content about Redis memory tuning"
        doc_b_content = "Doc B content about unrelated topic"
        doc_a_vec = _vec(0)
        doc_b_vec = _vec(1)
        query_vec = doc_a_vec[:]  # identical to A => cosine distance ~ 0

        mock_vec = MockVectorizer(query_vec, {doc_a_content: doc_a_vec, doc_b_content: doc_b_vec})
        docs = [
            _doc(
                doc_id="threshold-doc-a",
                title="Doc A",
                content=doc_a_content,
                source="a.md",
                document_hash="threshold-hash-a",
                content_hash="threshold-content-hash-a",
                vector=_vec_buffer(doc_a_vec),
            ),
            _doc(
                doc_id="threshold-doc-b",
                title="Doc B",
                content=doc_b_content,
                source="b.md",
                document_hash="threshold-hash-b",
                content_hash="threshold-content-hash-b",
                vector=_vec_buffer(doc_b_vec),
            ),
        ]
        await _load_docs(index, SRE_KNOWLEDGE_INDEX, docs)

        with patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vec):
            # Default distance_threshold (0.2) should return only Doc A
            result = await search_knowledge_base_helper(
                query="redis memory", category="alpha", limit=5, config=test_settings
            )

        assert result["query"] == "redis memory"
        assert result["category"] == "alpha"
        assert result["results_count"] == 1
        assert len(result["results"]) == 1
        top = result["results"][0]
        assert top["title"] == "Doc A"
        # Score should be present and near zero for identical vectors
        assert "score" in top
        assert isinstance(top["score"], (int, float))
        assert 0.0 <= top["score"] <= 0.05  # near-perfect match under cosine distance

    @pytest.mark.asyncio
    async def test_without_threshold_returns_more(self, test_settings, async_redis_client):
        await create_indices(config=test_settings)
        index = await get_knowledge_index(config=test_settings)

        # Prepare vectors and ingest again
        doc_a_content = "Doc A content about Redis memory tuning"
        doc_b_content = "Doc B content about unrelated topic"
        doc_a_vec = _vec(0)
        doc_b_vec = _vec(1)
        query_vec = doc_a_vec[:]

        mock_vec = MockVectorizer(query_vec, {doc_a_content: doc_a_vec, doc_b_content: doc_b_vec})
        docs = [
            _doc(
                doc_id="knn-doc-a",
                title="Doc A",
                content=doc_a_content,
                source="a.md",
                document_hash="knn-hash-a",
                content_hash="knn-content-hash-a",
                vector=_vec_buffer(doc_a_vec),
            ),
            _doc(
                doc_id="knn-doc-b",
                title="Doc B",
                content=doc_b_content,
                source="b.md",
                document_hash="knn-hash-b",
                content_hash="knn-content-hash-b",
                vector=_vec_buffer(doc_b_vec),
            ),
        ]
        await _load_docs(index, SRE_KNOWLEDGE_INDEX, docs)

        with patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vec):
            # Disable threshold to fall back to KNN-style query and request top-2
            result = await search_knowledge_base_helper(
                query="redis memory",
                category="alpha",
                limit=2,
                distance_threshold=None,
                config=test_settings,
            )

        assert result["results_count"] == 2
        titles = [r["title"] for r in result["results"]]
        assert titles[0] == "Doc A"
        assert "Doc B" in titles
        # Ensure scores are present and ordering is by increasing distance
        scores = [r["score"] for r in result["results"]]
        assert all(isinstance(s, (int, float)) for s in scores)
        assert scores[0] <= scores[1]
        # Sanity: first score is near 0, second is substantially larger (orthogonal ~ 1.0)
        assert 0.0 <= scores[0] <= 0.05
        assert scores[1] >= 0.5

    @pytest.mark.asyncio
    async def test_category_fallback_on_no_results(self, test_settings, async_redis_client):
        await create_indices(config=test_settings)
        index = await get_knowledge_index(config=test_settings)

        doc_a_content = "Doc A content about Redis memory tuning"
        doc_a_vec = _vec(0)
        query_vec = doc_a_vec[:]
        mock_vec = MockVectorizer(query_vec, {doc_a_content: doc_a_vec})
        docs = [
            _doc(
                doc_id="fallback-doc-a",
                title="Doc A",
                content=doc_a_content,
                source="a.md",
                document_hash="fallback-hash-a",
                content_hash="fallback-content-hash-a",
                vector=_vec_buffer(doc_a_vec),
            )
        ]
        await _load_docs(index, SRE_KNOWLEDGE_INDEX, docs)

        with patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vec):
            # Search with a category that yields 0, expect fallback without filter to return Doc A
            result = await search_knowledge_base_helper(
                query="redis memory",
                category="nonexistent",
                limit=5,
                config=test_settings,
            )

        assert result["results_count"] >= 1
        assert any(r["title"] == "Doc A" for r in result["results"])

    @pytest.mark.asyncio
    async def test_exact_document_hash_match_beats_semantic_result(
        self, test_settings, async_redis_client
    ):
        await create_indices(config=test_settings)

        index = await get_knowledge_index(config=test_settings)
        exact_content = "Orthogonal incident record"
        semantic_content = "Cache failover timeline and impact summary"
        exact_vec = _vec(1)
        semantic_vec = _vec(0)
        query_vec = semantic_vec[:]
        mock_vec = MockVectorizer(
            query_vec,
            {
                exact_content: exact_vec,
                semantic_content: semantic_vec,
            },
        )

        docs = [
            _doc(
                doc_id="exact-doc-hash",
                title="Ticket record",
                name="Ticket record",
                content=exact_content,
                source="incidents/doc-hash.md",
                document_hash="ret-4421-hash",
                content_hash="content-hash-1",
                vector=_vec_buffer(exact_vec),
            ),
            _doc(
                doc_id="semantic-doc",
                title="Failover incident analysis",
                content=semantic_content,
                source="incidents/failover.md",
                document_hash="semantic-hash",
                content_hash="content-hash-2",
                vector=_vec_buffer(semantic_vec),
            ),
        ]
        await _load_docs(index, SRE_KNOWLEDGE_INDEX, docs)

        with patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vec):
            result = await search_knowledge_base_helper(
                query="ret-4421-hash",
                limit=2,
                distance_threshold=None,
                config=test_settings,
            )

        assert result["results_count"] == 2
        assert result["results"][0]["document_hash"] == "ret-4421-hash"
        assert result["results"][0]["title"] == "Ticket record"
        assert result["results"][1]["document_hash"] == "semantic-hash"

    @pytest.mark.asyncio
    async def test_exact_source_match_beats_semantic_result(
        self, test_settings, async_redis_client
    ):
        await create_indices(config=test_settings)

        index = await get_knowledge_index(config=test_settings)
        exact_content = "Orthogonal source match record"
        semantic_content = "Redis memory failover investigation"
        exact_vec = _vec(1)
        semantic_vec = _vec(0)
        query_vec = semantic_vec[:]
        mock_vec = MockVectorizer(
            query_vec,
            {
                exact_content: exact_vec,
                semantic_content: semantic_vec,
            },
        )

        docs = [
            _doc(
                doc_id="exact-source",
                title="Runbook source target",
                content=exact_content,
                source="runbooks/cache/failover.md",
                document_hash="source-match-hash",
                content_hash="source-content-hash",
                vector=_vec_buffer(exact_vec),
            ),
            _doc(
                doc_id="semantic-source",
                title="Cache failover guidance",
                content=semantic_content,
                source="runbooks/cache/overview.md",
                document_hash="source-semantic-hash",
                content_hash="source-content-hash-2",
                vector=_vec_buffer(semantic_vec),
            ),
        ]
        await _load_docs(index, SRE_KNOWLEDGE_INDEX, docs)

        with patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vec):
            result = await search_knowledge_base_helper(
                query="runbooks/cache/failover.md",
                limit=2,
                distance_threshold=None,
                config=test_settings,
            )

        assert result["results_count"] == 2
        assert result["results"][0]["source"] == "runbooks/cache/failover.md"
        assert result["results"][0]["document_hash"] == "source-match-hash"
        assert result["results"][1]["document_hash"] == "source-semantic-hash"

    @pytest.mark.asyncio
    async def test_exact_symbol_heavy_name_match_beats_semantic_result(
        self, test_settings, async_redis_client
    ):
        await create_indices(config=test_settings)

        index = await get_knowledge_index(config=test_settings)
        exact_content = "Literal identifier reference"
        semantic_content = "General configuration guidance"
        exact_vec = _vec(1)
        semantic_vec = _vec(0)
        query_vec = semantic_vec[:]
        mock_vec = MockVectorizer(
            query_vec,
            {
                exact_content: exact_vec,
                semantic_content: semantic_vec,
            },
        )

        docs = [
            _doc(
                doc_id="exact-name-symbols",
                title="Exact name match",
                content=exact_content,
                source="configs/literal.md",
                name="foo|bar/baz[prod]",
                document_hash="symbol-name-exact-hash",
                content_hash="symbol-name-exact-content-hash",
                vector=_vec_buffer(exact_vec),
            ),
            _doc(
                doc_id="semantic-name-symbols",
                title="Semantic distractor",
                content=semantic_content,
                source="configs/semantic.md",
                name="semantic-config",
                document_hash="symbol-name-semantic-hash",
                content_hash="symbol-name-semantic-content-hash",
                vector=_vec_buffer(semantic_vec),
            ),
        ]
        await _load_docs(index, SRE_KNOWLEDGE_INDEX, docs)

        with patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vec):
            result = await search_knowledge_base_helper(
                query="foo|bar/baz[prod]",
                limit=2,
                distance_threshold=None,
                config=test_settings,
            )

        assert result["results_count"] == 2
        assert result["results"][0]["name"] == "foo|bar/baz[prod]"
        assert result["results"][0]["document_hash"] == "symbol-name-exact-hash"
        assert result["results"][1]["document_hash"] == "symbol-name-semantic-hash"

    @pytest.mark.asyncio
    async def test_quoted_phrase_search_finds_title_summary_and_content_matches_first(
        self, test_settings, async_redis_client
    ):
        await create_indices(config=test_settings)

        index = await get_knowledge_index(config=test_settings)
        title_content = "Orthogonal title match content"
        summary_content = "Orthogonal summary match content"
        content_match = "When DB memory full appears, page the on-call engineer."
        semantic_content = "Redis memory investigation and failover analysis"
        title_vec = _vec(1)
        summary_vec = _vec(2)
        content_vec = _vec(3)
        semantic_vec = _vec(0)
        query_vec = semantic_vec[:]
        mock_vec = MockVectorizer(
            query_vec,
            {
                title_content: title_vec,
                summary_content: summary_vec,
                content_match: content_vec,
                semantic_content: semantic_vec,
            },
        )

        docs = [
            _doc(
                doc_id="quoted-title",
                title="DB memory full",
                content=title_content,
                source="quoted/title.md",
                summary="Escalation guide",
                document_hash="quoted-title-hash",
                content_hash="quoted-title-content-hash",
                vector=_vec_buffer(title_vec),
            ),
            _doc(
                doc_id="quoted-summary",
                title="Node pressure",
                content=summary_content,
                source="quoted/summary.md",
                summary="DB memory full",
                document_hash="quoted-summary-hash",
                content_hash="quoted-summary-content-hash",
                vector=_vec_buffer(summary_vec),
            ),
            _doc(
                doc_id="quoted-content",
                title="Paging flow",
                content=content_match,
                source="quoted/content.md",
                summary="Escalation detail",
                document_hash="quoted-content-hash",
                content_hash="quoted-content-content-hash",
                vector=_vec_buffer(content_vec),
            ),
            _doc(
                doc_id="quoted-semantic",
                title="Semantic distractor",
                content=semantic_content,
                source="quoted/semantic.md",
                summary="Related but not exact",
                document_hash="quoted-semantic-hash",
                content_hash="quoted-semantic-content-hash",
                vector=_vec_buffer(semantic_vec),
            ),
        ]
        await _load_docs(index, SRE_KNOWLEDGE_INDEX, docs)

        with patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vec):
            result = await search_knowledge_base_helper(
                query='"DB memory full"',
                limit=4,
                distance_threshold=None,
                config=test_settings,
            )

        assert result["results_count"] == 4
        first_three = {doc["document_hash"] for doc in result["results"][:3]}
        assert first_three == {
            "quoted-title-hash",
            "quoted-summary-hash",
            "quoted-content-hash",
        }
        assert result["results"][3]["document_hash"] == "quoted-semantic-hash"

    @pytest.mark.asyncio
    async def test_support_ticket_search_and_lookup_resolve_stable_ticket_id(
        self, test_settings, async_redis_client
    ):
        await create_indices(config=test_settings)

        index = await get_support_tickets_index(config=test_settings)
        exact_content = "Orthogonal ticket body"
        semantic_content = "Follow-up for RET-4421 after failover investigation"
        exact_vec = _vec(1)
        semantic_vec = _vec(0)
        query_vec = exact_vec[:]
        mock_vec = MockVectorizer(
            query_vec,
            {
                exact_content: exact_vec,
                semantic_content: semantic_vec,
            },
        )

        docs = [
            _doc(
                doc_id="ret-4421-chunk-0",
                title="Cache failover incident",
                name="RET-4421",
                content=exact_content,
                source="tickets/ret-4421.md",
                category="incident",
                severity="critical",
                doc_type="support_ticket",
                document_hash="ticket-hash-4421",
                content_hash="ticket-content-hash-4421",
                vector=_vec_buffer(exact_vec),
            ),
            _doc(
                doc_id="ret-9999-chunk-0",
                title="Failover incident notes",
                name="RET-9999",
                content=semantic_content,
                source="tickets/ret-9999.md",
                category="incident",
                severity="critical",
                doc_type="support_ticket",
                document_hash="ticket-hash-9999",
                content_hash="ticket-content-hash-9999",
                vector=_vec_buffer(semantic_vec),
            ),
        ]
        await _load_docs(index, SRE_SUPPORT_TICKETS_INDEX, docs)

        with patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vec):
            search_result = await search_support_tickets_helper(
                query="RET-4421",
                limit=2,
                config=test_settings,
            )

        assert search_result["results_count"] == 2
        assert search_result["tickets"][0]["ticket_id"] == "RET-4421"
        assert search_result["tickets"][0]["document_hash"] == "ticket-hash-4421"
        assert search_result["tickets"][1]["ticket_id"] == "RET-9999"

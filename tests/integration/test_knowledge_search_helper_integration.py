"""Integration tests for search_knowledge_base_helper with a live Redis via testcontainers.

These tests exercise the new distance_threshold behavior (default ON) and ensure
'score' is returned in results when using RedisVL queries.
"""

from typing import List
from unittest.mock import patch

import pytest

from redis_sre_agent.core.knowledge_helpers import (
    ingest_sre_document_helper,
    search_knowledge_base_helper,
)
from redis_sre_agent.core.redis import create_indices

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


@pytest.mark.integration
class TestKnowledgeSearchHelper:
    @pytest.mark.asyncio
    async def test_distance_threshold_filters_results(self, redis_container, async_redis_client):
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Ensure indices exist and DB is clean (async_redis_client fixture flushes)
        await create_indices()

        # Prepare deterministic vectors: doc A ~ query, doc B far away
        doc_a_content = "Doc A content about Redis memory tuning"
        doc_b_content = "Doc B content about unrelated topic"
        doc_a_vec = _vec(0)
        doc_b_vec = _vec(1)
        query_vec = doc_a_vec[:]  # identical to A => cosine distance ~ 0

        mock_vec = MockVectorizer(query_vec, {doc_a_content: doc_a_vec, doc_b_content: doc_b_vec})

        with patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vec):
            # Ingest two documents in same category
            await ingest_sre_document_helper(
                title="Doc A",
                content=doc_a_content,
                source="a.md",
                category="alpha",
                severity="info",
            )
            await ingest_sre_document_helper(
                title="Doc B",
                content=doc_b_content,
                source="b.md",
                category="alpha",
                severity="info",
            )

            # Default distance_threshold (0.2) should return only Doc A
            result = await search_knowledge_base_helper(
                query="redis memory", category="alpha", limit=5
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
    async def test_without_threshold_returns_more(self, redis_container, async_redis_client):
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        await create_indices()

        # Prepare vectors and ingest again
        doc_a_content = "Doc A content about Redis memory tuning"
        doc_b_content = "Doc B content about unrelated topic"
        doc_a_vec = _vec(0)
        doc_b_vec = _vec(1)
        query_vec = doc_a_vec[:]

        mock_vec = MockVectorizer(query_vec, {doc_a_content: doc_a_vec, doc_b_content: doc_b_vec})

        with patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vec):
            await ingest_sre_document_helper(
                title="Doc A",
                content=doc_a_content,
                source="a.md",
                category="alpha",
                severity="info",
            )
            await ingest_sre_document_helper(
                title="Doc B",
                content=doc_b_content,
                source="b.md",
                category="alpha",
                severity="info",
            )

            # Disable threshold to fall back to KNN-style query and request top-2
            result = await search_knowledge_base_helper(
                query="redis memory", category="alpha", limit=2, distance_threshold=None
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
    async def test_category_fallback_on_no_results(self, redis_container, async_redis_client):
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        await create_indices()

        doc_a_content = "Doc A content about Redis memory tuning"
        doc_a_vec = _vec(0)
        query_vec = doc_a_vec[:]
        mock_vec = MockVectorizer(query_vec, {doc_a_content: doc_a_vec})

        with patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vec):
            await ingest_sre_document_helper(
                title="Doc A",
                content=doc_a_content,
                source="a.md",
                category="alpha",
                severity="info",
            )

            # Search with a category that yields 0, expect fallback without filter to return Doc A
            result = await search_knowledge_base_helper(
                query="redis memory", category="nonexistent", limit=5
            )

        assert result["results_count"] >= 1
        assert any(r["title"] == "Doc A" for r in result["results"])

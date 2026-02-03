"""Integration test for Q&A recording with citations.

This test exercises the QAManager against a real Redis instance
(provided by the testcontainers-backed redis_container fixture).
It creates Q&A records with citations, retrieves them, and verifies
the data is stored correctly in Redis.
"""

from typing import List
from unittest.mock import patch

import pytest

from redis_sre_agent.core.qa import Citation, QAManager
from redis_sre_agent.core.redis import SRE_QA_INDEX

VECTOR_DIM = 1536


def _vec(first_one_index: int) -> List[float]:
    """Create a deterministic unit vector with a 1.0 at the given index."""
    v = [0.0] * VECTOR_DIM
    v[first_one_index] = 1.0
    return v


class MockVectorizer:
    """Mock vectorizer that returns deterministic vectors for testing."""

    def __init__(self, query_vec: List[float], content_map: dict):
        self.query_vec = query_vec
        self.content_map = content_map

    def embed(self, text: str, as_buffer: bool = False) -> bytes | List[float]:
        vec = self.content_map.get(text, self.query_vec)
        if as_buffer:
            import struct

            return struct.pack(f"{len(vec)}f", *vec)
        return vec

    async def aembed(self, text: str, as_buffer: bool = False) -> bytes | List[float]:
        return self.embed(text, as_buffer)

    async def aembed_many(
        self, texts: List[str], as_buffer: bool = False
    ) -> List[bytes | List[float]]:
        return [self.embed(t, as_buffer) for t in texts]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qa_record_lifecycle(async_redis_client, redis_container):
    """Test full Q&A record lifecycle: create, retrieve, update feedback, delete."""
    if not redis_container:
        pytest.skip("Integration tests not enabled")

    qa_manager = QAManager(redis_client=async_redis_client)

    # 1. Create a Q&A record with citations
    citations = [
        Citation(
            document_id="doc-123",
            document_hash="abc123",
            title="Redis Overview",
            source="https://redis.io/docs/overview",
            content_preview="Redis is an in-memory data structure store.",
            chunk_index=0,
            score=0.95,
        ),
        Citation(
            document_id="doc-456",
            document_hash="def456",
            title="Redis Data Types",
            source="https://redis.io/docs/data-types",
            content_preview="Redis supports various data structures.",
            chunk_index=1,
            score=0.87,
        ),
    ]

    qa = await qa_manager.record_qa(
        question="What is Redis?",
        answer="Redis is a fast in-memory database that supports various data structures.",
        citations=citations,
        user_id="test-user",
        thread_id="test-thread",
        task_id="test-task",
    )

    assert qa.id is not None
    assert qa.question == "What is Redis?"
    assert len(qa.citations) == 2

    # 2. Verify the record exists in Redis (uses RedisVL index key pattern)
    key = f"{SRE_QA_INDEX}:{qa.id}"
    exists = await async_redis_client.exists(key)
    assert exists == 1

    # 3. Retrieve the Q&A record
    retrieved = await qa_manager.get_qa(qa.id)
    assert retrieved is not None
    assert retrieved.question == qa.question
    assert retrieved.answer == qa.answer
    assert len(retrieved.citations) == 2
    assert retrieved.citations[0].document_id == "doc-123"
    assert retrieved.citations[1].document_id == "doc-456"

    # 4. Record feedback
    success = await qa_manager.record_feedback(
        qa.id, accepted=True, feedback_text="Very helpful answer!"
    )
    assert success is True

    # 5. Verify feedback was saved
    with_feedback = await qa_manager.get_qa(qa.id)
    assert with_feedback.feedback is not None
    assert with_feedback.feedback.accepted is True
    assert with_feedback.feedback.feedback_text == "Very helpful answer!"

    # 6. Test listing by thread
    by_thread = await qa_manager.list_qa_by_thread("test-thread")
    assert len(by_thread) == 1
    assert by_thread[0].id == qa.id

    # 7. Test listing by user
    by_user = await qa_manager.list_qa_by_user("test-user")
    assert len(by_user) == 1
    assert by_user[0].id == qa.id

    # 8. Test listing by task
    by_task = await qa_manager.list_qa_by_task("test-task")
    assert len(by_task) == 1
    assert by_task[0].id == qa.id

    # 9. Delete the Q&A record
    deleted = await qa_manager.delete_qa(qa.id)
    assert deleted is True

    # 10. Verify deletion
    after_delete = await qa_manager.get_qa(qa.id)
    assert after_delete is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qa_update_vectors(async_redis_client, redis_container):
    """Test updating vector embeddings on a Q&A record."""
    if not redis_container:
        pytest.skip("Integration tests not enabled")

    qa_manager = QAManager(redis_client=async_redis_client)

    # Create a Q&A record without vectors
    qa = await qa_manager.record_qa(
        question="How do I configure Redis persistence?",
        answer="You can use RDB snapshots or AOF for persistence.",
        citations=[],
    )

    # Verify no vectors initially
    retrieved = await qa_manager.get_qa(qa.id)
    assert retrieved.question_vector is None
    assert retrieved.answer_vector is None

    # Update with vectors
    question_vec = b"\x00\x01\x02\x03" * 384  # Simulate 1536-dim float32 vector
    answer_vec = b"\x04\x05\x06\x07" * 384

    success = await qa_manager.update_vectors(
        qa.id, question_vector=question_vec, answer_vector=answer_vec
    )
    assert success is True

    # Verify vectors were saved
    with_vectors = await qa_manager.get_qa(qa.id)
    assert with_vectors.question_vector is not None
    assert with_vectors.answer_vector is not None

    # Cleanup
    await qa_manager.delete_qa(qa.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_cycle_ingest_search_qa_citations(
    async_redis_client, redis_container, test_settings
):
    """Test complete cycle: ingest docs → search → record Q&A → verify citations.

    This test proves that:
    1. Documents are ingested into the knowledge base
    2. Search returns those documents with proper metadata
    3. Q&A recording captures citations from search results
    4. Retrieved Q&A has citations matching the original ingested documents
    """
    if not redis_container:
        pytest.skip("Integration tests not enabled")

    from redis_sre_agent.core.keys import RedisKeys
    from redis_sre_agent.core.knowledge_helpers import (
        ingest_sre_document_helper,
        search_knowledge_base_helper,
    )
    from redis_sre_agent.core.redis import create_indices

    # Clean up existing knowledge index data to avoid interference
    keys = await async_redis_client.keys("sre_knowledge:*")
    if keys:
        await async_redis_client.delete(*keys)

    # Drop and recreate indices for clean state
    try:
        await async_redis_client.ft("sre_knowledge_idx").dropindex(delete_documents=True)
    except Exception:
        pass  # Index might not exist

    # Create indices
    await create_indices(config=test_settings)

    # Prepare deterministic vectors for controlled search results
    doc1_content = "Redis memory optimization involves setting maxmemory and eviction policies"
    doc2_content = "Redis persistence uses RDB snapshots and AOF for durability"
    doc1_vec = _vec(0)
    doc2_vec = _vec(1)
    query_vec = doc1_vec[:]  # Query matches doc1 exactly

    mock_vectorizer = MockVectorizer(
        query_vec, {doc1_content: doc1_vec, doc2_content: doc2_vec}
    )

    # Create a test knowledge index connected to the testcontainer Redis
    from redis_sre_agent.core.redis import get_knowledge_index

    test_knowledge_index = await get_knowledge_index(config=test_settings)

    with (
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
            return_value=mock_vectorizer,
        ),
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
            return_value=test_knowledge_index,
        ),
    ):
        # 1. Ingest documents into knowledge base
        ingest1 = await ingest_sre_document_helper(
            title="Redis Memory Guide",
            content=doc1_content,
            source="memory-guide.md",
            category="optimization",
            severity="info",
        )
        ingest2 = await ingest_sre_document_helper(
            title="Redis Persistence Guide",
            content=doc2_content,
            source="persistence-guide.md",
            category="optimization",
            severity="info",
        )

        assert ingest1["status"] == "ingested"
        assert ingest2["status"] == "ingested"
        doc1_id = ingest1["document_id"]
        _doc2_id = ingest2["document_id"]  # noqa: F841 - kept for completeness

        # 2. Search knowledge base - should return doc1 (matches query vector)
        search_result = await search_knowledge_base_helper(
            query="How do I optimize Redis memory?",
            category="optimization",
            limit=5,
            distance_threshold=0.5,  # Allow some distance
            version=None,  # Disable version filter for test documents
        )

        assert "results" in search_result
        results = search_result["results"]
        assert len(results) >= 1, "Expected at least one search result"

        # Verify search result has expected fields for citation conversion
        first_result = results[0]
        assert "id" in first_result
        assert "title" in first_result
        assert "content" in first_result
        assert "source" in first_result
        assert "score" in first_result

        # 3. Record Q&A with citations from search results
        qa_manager = QAManager(redis_client=async_redis_client)
        qa = await qa_manager.record_qa_from_search(
            question="How do I optimize Redis memory?",
            answer="To optimize Redis memory, configure maxmemory and eviction policies.",
            search_results=results,
            user_id="test-user",
            thread_id="test-thread-cycle",
            task_id="test-task-cycle",
        )

        assert qa.id is not None
        assert len(qa.citations) >= 1, "Expected at least one citation"

        # 4. Retrieve Q&A and verify citations match ingested documents
        retrieved = await qa_manager.get_qa(qa.id)
        assert retrieved is not None
        assert len(retrieved.citations) >= 1

        # Verify citation data matches the ingested document
        # The citation.document_id contains the full Redis key (sre_knowledge:{id})
        # or just the id, depending on what RedisVL returns
        citation = retrieved.citations[0]
        expected_key = RedisKeys.knowledge_document(doc1_id)
        assert citation.document_id in (doc1_id, expected_key), (
            f"Citation document_id {citation.document_id} should match "
            f"ingested doc {doc1_id} or key {expected_key}"
        )
        assert citation.title == "Redis Memory Guide"
        assert citation.source == "memory-guide.md"
        assert citation.content_preview is not None
        assert "memory" in citation.content_preview.lower()
        assert citation.score is not None

        # 5. Cleanup
        await qa_manager.delete_qa(qa.id)

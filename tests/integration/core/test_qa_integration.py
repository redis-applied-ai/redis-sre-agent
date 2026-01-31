"""Integration test for Q&A recording with citations.

This test exercises the QAManager against a real Redis instance
(provided by the testcontainers-backed redis_container fixture).
It creates Q&A records with citations, retrieves them, and verifies
the data is stored correctly in Redis.
"""

import pytest

from redis_sre_agent.core.qa import Citation, QAManager
from redis_sre_agent.core.redis import SRE_QA_INDEX


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

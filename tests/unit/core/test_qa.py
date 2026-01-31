"""Tests for Q&A recording with citation tracking (TDD approach).

Tests written first, then implementation follows.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# These imports will fail until we implement the models
from redis_sre_agent.core.qa import (
    Citation,
    Feedback,
    QAManager,
    QuestionAnswer,
)


class TestCitationModel:
    """Test Citation data model."""

    def test_citation_creation_minimal(self):
        """Test creating a citation with minimal fields."""
        citation = Citation(
            document_id="doc-123",
            document_hash="abc123",
            title="Redis Memory Guide",
            source="redis.io/docs/memory",
        )
        assert citation.document_id == "doc-123"
        assert citation.document_hash == "abc123"
        assert citation.title == "Redis Memory Guide"
        assert citation.source == "redis.io/docs/memory"
        assert citation.chunk_index is None
        assert citation.content_preview is None
        assert citation.score is None

    def test_citation_creation_full(self):
        """Test creating a citation with all fields."""
        citation = Citation(
            document_id="doc-456",
            document_hash="def456",
            chunk_index=3,
            title="Redis Configuration",
            source="redis.io/docs/config",
            content_preview="Configure maxmemory policy...",
            score=0.92,
        )
        assert citation.chunk_index == 3
        assert citation.content_preview == "Configure maxmemory policy..."
        assert citation.score == 0.92

    def test_citation_serialization(self):
        """Test citation JSON serialization."""
        citation = Citation(
            document_id="doc-789",
            document_hash="ghi789",
            title="Test Doc",
            source="test",
            score=0.85,
        )
        data = citation.model_dump()
        assert data["document_id"] == "doc-789"
        assert data["score"] == 0.85


class TestFeedbackModel:
    """Test Feedback data model."""

    def test_feedback_creation_default(self):
        """Test creating feedback with defaults."""
        feedback = Feedback()
        assert feedback.accepted is None
        assert feedback.feedback_text is None
        assert feedback.created_at is not None

    def test_feedback_accepted(self):
        """Test feedback marked as accepted."""
        feedback = Feedback(accepted=True, feedback_text="Helpful answer!")
        assert feedback.accepted is True
        assert feedback.feedback_text == "Helpful answer!"

    def test_feedback_rejected(self):
        """Test feedback marked as rejected."""
        feedback = Feedback(accepted=False, feedback_text="Not accurate")
        assert feedback.accepted is False
        assert feedback.feedback_text == "Not accurate"

    def test_feedback_serialization(self):
        """Test feedback JSON serialization."""
        feedback = Feedback(accepted=True)
        data = feedback.model_dump()
        assert data["accepted"] is True
        assert "created_at" in data


class TestQuestionAnswerModel:
    """Test QuestionAnswer data model."""

    def test_qa_creation_minimal(self):
        """Test creating a Q&A record with minimal fields."""
        qa = QuestionAnswer(
            question="What is Redis eviction?",
            answer="Redis eviction is a memory management feature...",
        )
        assert qa.question == "What is Redis eviction?"
        assert qa.answer == "Redis eviction is a memory management feature..."
        assert qa.id is not None
        assert qa.citations == []
        assert qa.feedback is None
        assert qa.user_id is None
        assert qa.thread_id is None
        assert qa.task_id is None
        assert qa.created_at is not None
        assert qa.updated_at is not None

    def test_qa_creation_full(self):
        """Test creating a Q&A record with all fields."""
        citations = [
            Citation(
                document_id="doc-1",
                document_hash="hash1",
                title="Memory Guide",
                source="redis.io",
            )
        ]
        feedback = Feedback(accepted=True)

        qa = QuestionAnswer(
            id="qa-custom-id",
            question="Test question",
            answer="Test answer",
            citations=citations,
            feedback=feedback,
            user_id="user-123",
            thread_id="thread-456",
            task_id="task-789",
        )
        assert qa.id == "qa-custom-id"
        assert len(qa.citations) == 1
        assert qa.feedback.accepted is True
        assert qa.user_id == "user-123"
        assert qa.thread_id == "thread-456"
        assert qa.task_id == "task-789"

    def test_qa_serialization(self):
        """Test Q&A JSON serialization/deserialization."""
        qa = QuestionAnswer(
            question="Test",
            answer="Answer",
            citations=[
                Citation(
                    document_id="d1",
                    document_hash="h1",
                    title="T1",
                    source="s1",
                )
            ],
        )
        data = qa.model_dump()
        assert data["question"] == "Test"
        assert len(data["citations"]) == 1

        # Test deserialization
        qa2 = QuestionAnswer.model_validate(data)
        assert qa2.question == qa.question
        assert len(qa2.citations) == 1


class TestRedisKeysForQA:
    """Test Redis key patterns for Q&A records."""

    def test_qa_record_key(self):
        """Test Q&A record key generation."""
        from redis_sre_agent.core.keys import RedisKeys

        key = RedisKeys.qa_record("qa-123")
        assert key == "sre:qa:qa-123"

    def test_qa_by_thread_key(self):
        """Test Q&A by thread index key generation."""
        from redis_sre_agent.core.keys import RedisKeys

        key = RedisKeys.qa_by_thread("thread-456")
        assert key == "sre:thread:thread-456:qa"

    def test_qa_by_user_key(self):
        """Test Q&A by user index key generation."""
        from redis_sre_agent.core.keys import RedisKeys

        key = RedisKeys.qa_by_user("user-789")
        assert key == "sre:user:user-789:qa"

    def test_qa_by_task_key(self):
        """Test Q&A by task index key generation."""
        from redis_sre_agent.core.keys import RedisKeys

        key = RedisKeys.qa_by_task("task-101")
        assert key == "sre:task:task-101:qa"


class TestQAManager:
    """Test QAManager class for recording Q&A pairs with citations."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client for testing (hash storage pattern)."""
        client = AsyncMock()
        # Hash operations for RedisVL index pattern
        client.hset = AsyncMock(return_value=1)
        client.hget = AsyncMock(return_value=None)
        client.hgetall = AsyncMock(return_value={})
        client.exists = AsyncMock(return_value=0)
        client.sadd = AsyncMock(return_value=1)
        client.smembers = AsyncMock(return_value=set())
        client.srem = AsyncMock(return_value=1)
        client.delete = AsyncMock(return_value=1)
        return client

    @pytest.fixture
    def qa_manager(self, mock_redis_client):
        """Create QAManager with mocked Redis."""
        manager = QAManager(redis_client=mock_redis_client)
        manager._index_ensured = True  # Skip index creation in tests
        return manager

    @pytest.mark.asyncio
    async def test_record_qa_minimal(self, qa_manager):
        """Test recording a Q&A pair with minimal data."""
        result = await qa_manager.record_qa(
            question="What is Redis?",
            answer="Redis is an in-memory data store.",
        )
        assert result is not None
        assert result.question == "What is Redis?"
        assert result.answer == "Redis is an in-memory data store."
        assert result.id is not None
        assert result.citations == []

    @pytest.mark.asyncio
    async def test_record_qa_with_citations(self, qa_manager):
        """Test recording a Q&A pair with citations."""
        citations = [
            Citation(
                document_id="doc-1",
                document_hash="hash1",
                title="Redis Introduction",
                source="redis.io/docs/about",
                score=0.95,
            ),
            Citation(
                document_id="doc-2",
                document_hash="hash2",
                title="Redis Data Types",
                source="redis.io/docs/data-types",
                score=0.88,
            ),
        ]

        result = await qa_manager.record_qa(
            question="What are Redis data types?",
            answer="Redis supports strings, lists, sets...",
            citations=citations,
        )
        assert len(result.citations) == 2
        assert result.citations[0].score == 0.95
        assert result.citations[1].title == "Redis Data Types"

    @pytest.mark.asyncio
    async def test_record_qa_with_context(self, qa_manager):
        """Test recording a Q&A pair with user/thread/task context."""
        result = await qa_manager.record_qa(
            question="Test question",
            answer="Test answer",
            user_id="user-123",
            thread_id="thread-456",
            task_id="task-789",
        )
        assert result.user_id == "user-123"
        assert result.thread_id == "thread-456"
        assert result.task_id == "task-789"

        # Verify indices were updated
        qa_manager._redis_client.sadd.assert_called()

    @pytest.mark.asyncio
    async def test_record_feedback(self, qa_manager, mock_redis_client):
        """Test recording feedback on a Q&A pair."""
        import json

        # Setup: mock existing Q&A data in hash format
        existing_qa = QuestionAnswer(
            id="qa-existing",
            question="Test",
            answer="Answer",
        )
        qa_dict = existing_qa.model_dump(mode="json", exclude={"question_vector", "answer_vector"})
        mock_redis_client.hget = AsyncMock(return_value=json.dumps(qa_dict).encode())

        result = await qa_manager.record_feedback(
            qa_id="qa-existing",
            accepted=True,
            feedback_text="Very helpful!",
        )
        assert result is True
        mock_redis_client.hset.assert_called()

    @pytest.mark.asyncio
    async def test_record_feedback_not_found(self, qa_manager):
        """Test recording feedback on non-existent Q&A."""
        qa_manager._redis_client.hget = AsyncMock(return_value=None)

        result = await qa_manager.record_feedback(
            qa_id="nonexistent",
            accepted=True,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_get_qa(self, qa_manager):
        """Test retrieving a Q&A record."""
        import json

        existing_qa = QuestionAnswer(
            id="qa-123",
            question="Test question",
            answer="Test answer",
        )
        qa_dict = existing_qa.model_dump(mode="json", exclude={"question_vector", "answer_vector"})
        # Mock hgetall to return hash data with 'data' field
        qa_manager._redis_client.hgetall = AsyncMock(
            return_value={
                b"data": json.dumps(qa_dict).encode(),
                b"question": b"Test question",
                b"answer": b"Test answer",
            }
        )

        result = await qa_manager.get_qa("qa-123")
        assert result is not None
        assert result.id == "qa-123"
        assert result.question == "Test question"

    @pytest.mark.asyncio
    async def test_get_qa_not_found(self, qa_manager):
        """Test retrieving non-existent Q&A record."""
        qa_manager._redis_client.hgetall = AsyncMock(return_value={})

        result = await qa_manager.get_qa("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_qa_by_thread(self, qa_manager):
        """Test listing Q&A records for a thread."""
        import json

        qa_manager._redis_client.smembers = AsyncMock(
            return_value={b"qa-1", b"qa-2"}
        )
        qa1 = QuestionAnswer(id="qa-1", question="Q1", answer="A1")
        qa2 = QuestionAnswer(id="qa-2", question="Q2", answer="A2")
        qa1_dict = qa1.model_dump(mode="json", exclude={"question_vector", "answer_vector"})
        qa2_dict = qa2.model_dump(mode="json", exclude={"question_vector", "answer_vector"})

        # Mock getting individual QA records via hgetall
        async def mock_hgetall(key):
            key_str = key.decode() if isinstance(key, bytes) else key
            if "qa-1" in key_str:
                return {b"data": json.dumps(qa1_dict).encode()}
            elif "qa-2" in key_str:
                return {b"data": json.dumps(qa2_dict).encode()}
            return {}

        qa_manager._redis_client.hgetall = mock_hgetall

        results = await qa_manager.list_qa_by_thread("thread-123")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_qa_by_user(self, qa_manager):
        """Test listing Q&A records for a user."""
        import json

        qa_manager._redis_client.smembers = AsyncMock(return_value={b"qa-1"})
        qa1 = QuestionAnswer(id="qa-1", question="Q1", answer="A1")
        qa1_dict = qa1.model_dump(mode="json", exclude={"question_vector", "answer_vector"})
        qa_manager._redis_client.hgetall = AsyncMock(
            return_value={b"data": json.dumps(qa1_dict).encode()}
        )

        results = await qa_manager.list_qa_by_user("user-123")
        assert len(results) == 1
        assert results[0].question == "Q1"

    @pytest.mark.asyncio
    async def test_delete_qa(self, qa_manager):
        """Test deleting a Q&A record."""
        import json

        existing_qa = QuestionAnswer(
            id="qa-to-delete",
            question="Test",
            answer="Answer",
            user_id="user-1",
            thread_id="thread-1",
            task_id="task-1",
        )
        qa_dict = existing_qa.model_dump(mode="json", exclude={"question_vector", "answer_vector"})
        qa_manager._redis_client.hgetall = AsyncMock(
            return_value={b"data": json.dumps(qa_dict).encode()}
        )

        result = await qa_manager.delete_qa("qa-to-delete")
        assert result is True
        qa_manager._redis_client.delete.assert_called()

    @pytest.mark.asyncio
    async def test_delete_qa_not_found(self, qa_manager):
        """Test deleting a Q&A record that doesn't exist."""
        qa_manager._redis_client.hgetall = AsyncMock(return_value={})

        result = await qa_manager.delete_qa("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_qa_by_task(self, qa_manager):
        """Test listing Q&A records for a task."""
        import json

        qa_manager._redis_client.smembers = AsyncMock(return_value={b"qa-1"})
        qa1 = QuestionAnswer(id="qa-1", question="Q1", answer="A1")
        qa1_dict = qa1.model_dump(mode="json", exclude={"question_vector", "answer_vector"})
        qa_manager._redis_client.hgetall = AsyncMock(
            return_value={b"data": json.dumps(qa1_dict).encode()}
        )

        results = await qa_manager.list_qa_by_task("task-123")
        assert len(results) == 1
        assert results[0].question == "Q1"


class TestQAManagerLazyInit:
    """Test QAManager lazy initialization of Redis client."""

    @pytest.mark.asyncio
    async def test_get_client_lazy_init(self):
        """Test that QAManager lazily initializes Redis client when needed."""
        # Create QAManager with redis_url but no client
        manager = QAManager(redis_url="redis://localhost:6379/0")
        manager._index_ensured = True  # Skip index creation in tests

        # Mock get_redis_client to return a mock client with hash operations
        mock_client = AsyncMock()
        mock_client.hgetall = AsyncMock(return_value={})

        with patch(
            "redis_sre_agent.core.redis.get_redis_client", return_value=mock_client
        ) as mock_get_client:
            # Call a method that needs the client
            result = await manager.get_qa("test-id")

            # Verify get_redis_client was called with the URL
            mock_get_client.assert_called_once_with("redis://localhost:6379/0")

            # Verify the client was used
            assert result is None
            mock_client.hgetall.assert_called_once()


class TestQAManagerFromSearchResults:
    """Test creating citations from knowledge search results."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client (hash storage pattern)."""
        client = AsyncMock()
        client.hset = AsyncMock(return_value=1)
        client.hgetall = AsyncMock(return_value={})
        client.sadd = AsyncMock(return_value=1)
        return client

    @pytest.fixture
    def qa_manager(self, mock_redis_client):
        """Create QAManager."""
        manager = QAManager(redis_client=mock_redis_client)
        manager._index_ensured = True  # Skip index creation in tests
        return manager

    def test_citations_from_search_results(self, qa_manager):
        """Test converting search results to citations."""
        search_results = [
            {
                "id": "doc-1",
                "document_hash": "hash-1",
                "chunk_index": 0,
                "title": "Redis Memory",
                "content": "Redis uses memory efficiently...",
                "source": "redis.io/docs/memory",
                "score": 0.95,
            },
            {
                "id": "doc-2",
                "document_hash": "hash-2",
                "chunk_index": 2,
                "title": "Redis Config",
                "content": "Configure maxmemory...",
                "source": "redis.io/docs/config",
                "score": 0.87,
            },
        ]

        citations = qa_manager.citations_from_search_results(search_results)

        assert len(citations) == 2
        assert citations[0].document_id == "doc-1"
        assert citations[0].document_hash == "hash-1"
        assert citations[0].title == "Redis Memory"
        assert citations[0].score == 0.95
        assert citations[0].content_preview == "Redis uses memory efficiently..."
        assert citations[1].chunk_index == 2

    def test_citations_from_search_results_with_content_truncation(self, qa_manager):
        """Test that long content is truncated in preview."""
        long_content = "x" * 500
        search_results = [
            {
                "id": "doc-1",
                "document_hash": "hash-1",
                "title": "Test",
                "content": long_content,
                "source": "test",
                "score": 0.9,
            },
        ]

        citations = qa_manager.citations_from_search_results(
            search_results, max_preview_length=100
        )

        assert len(citations[0].content_preview) <= 103  # 100 + "..."

    def test_citations_from_empty_results(self, qa_manager):
        """Test handling empty search results."""
        citations = qa_manager.citations_from_search_results([])
        assert citations == []

    @pytest.mark.asyncio
    async def test_record_qa_from_search(self, qa_manager):
        """Test recording Q&A with citations from search results."""
        search_results = [
            {
                "id": "doc-1",
                "document_hash": "hash-1",
                "title": "Redis Guide",
                "content": "Redis is fast...",
                "source": "redis.io",
                "score": 0.92,
            },
        ]

        result = await qa_manager.record_qa_from_search(
            question="What is Redis?",
            answer="Redis is a fast in-memory database.",
            search_results=search_results,
            user_id="user-1",
            thread_id="thread-1",
        )

        assert result is not None
        assert len(result.citations) == 1
        assert result.citations[0].title == "Redis Guide"
        assert result.user_id == "user-1"


class TestQuestionAnswerVectorFields:
    """Test vector fields on QuestionAnswer model."""

    def test_qa_creation_without_vectors(self):
        """Test creating a Q&A without vector fields (default behavior)."""
        qa = QuestionAnswer(
            question="What is Redis?",
            answer="Redis is a fast in-memory database.",
        )
        assert qa.question_vector is None
        assert qa.answer_vector is None

    def test_qa_creation_with_vectors(self):
        """Test creating a Q&A with vector fields."""
        question_vec = b"\x00" * 16  # Mock bytes for vector
        answer_vec = b"\x01" * 16
        qa = QuestionAnswer(
            question="What is Redis?",
            answer="Redis is a fast in-memory database.",
            question_vector=question_vec,
            answer_vector=answer_vec,
        )
        assert qa.question_vector == question_vec
        assert qa.answer_vector == answer_vec

    def test_qa_serialization_with_vectors(self):
        """Test serialization of Q&A with vector fields.

        With RedisVL hash storage, vectors are stored as raw bytes in the hash,
        not in the JSON 'data' field. The model keeps vectors as bytes.
        """
        question_vec = b"\x00\x01\x02\x03"
        answer_vec = b"\x04\x05\x06\x07"
        qa = QuestionAnswer(
            question="Test question",
            answer="Test answer",
            question_vector=question_vec,
            answer_vector=answer_vec,
        )
        # Vectors remain as bytes in the model
        assert qa.question_vector == question_vec
        assert qa.answer_vector == answer_vec
        # When dumped, they become bytes (not base64 encoded)
        data = qa.model_dump()
        assert data["question_vector"] == question_vec
        assert data["answer_vector"] == answer_vec

    def test_qa_vector_from_bytes(self):
        """Test that vectors can be created directly from bytes."""
        question_vec_bytes = b"\x00\x01\x02\x03"
        answer_vec_bytes = b"\x04\x05\x06\x07"

        qa = QuestionAnswer(
            question="Test question",
            answer="Test answer",
            question_vector=question_vec_bytes,
            answer_vector=answer_vec_bytes,
        )
        # Vectors are stored directly as bytes
        assert qa.question_vector == question_vec_bytes
        assert qa.answer_vector == answer_vec_bytes


class TestQAManagerUpdateVectors:
    """Test QAManager.update_vectors method."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client (hash storage pattern)."""
        client = AsyncMock()
        client.hset = AsyncMock(return_value=1)
        client.exists = AsyncMock(return_value=0)
        return client

    @pytest.fixture
    def qa_manager(self, mock_redis_client):
        """Create QAManager."""
        manager = QAManager(redis_client=mock_redis_client)
        manager._index_ensured = True
        return manager

    @pytest.mark.asyncio
    async def test_update_vectors_success(self, qa_manager, mock_redis_client):
        """Test successfully updating vectors on a Q&A record."""
        # Set up existing Q&A record - key exists
        mock_redis_client.exists = AsyncMock(return_value=1)

        question_vec = b"\x00" * 16
        answer_vec = b"\x01" * 16

        result = await qa_manager.update_vectors(
            qa_id="qa-123",
            question_vector=question_vec,
            answer_vector=answer_vec,
        )

        assert result is True
        # Verify hset was called with vectors as bytes (not base64)
        mock_redis_client.hset.assert_called()
        call_args = mock_redis_client.hset.call_args
        mapping = call_args.kwargs.get("mapping", {})
        assert mapping.get("question_vector") == question_vec
        assert mapping.get("answer_vector") == answer_vec

    @pytest.mark.asyncio
    async def test_update_vectors_not_found(self, qa_manager, mock_redis_client):
        """Test updating vectors on non-existent Q&A record."""
        mock_redis_client.exists = AsyncMock(return_value=0)

        result = await qa_manager.update_vectors(
            qa_id="nonexistent",
            question_vector=b"\x00" * 16,
            answer_vector=b"\x01" * 16,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_update_vectors_partial(self, qa_manager, mock_redis_client):
        """Test updating only question vector."""
        mock_redis_client.exists = AsyncMock(return_value=1)

        question_vec = b"\x00" * 16

        result = await qa_manager.update_vectors(
            qa_id="qa-456",
            question_vector=question_vec,
        )

        assert result is True
        # Only question_vector should be in mapping
        call_args = mock_redis_client.hset.call_args
        mapping = call_args.kwargs.get("mapping", {})
        assert "question_vector" in mapping
        assert "answer_vector" not in mapping


class TestEmbedQARecordTask:
    """Test the embed_qa_record Docket task."""

    @pytest.mark.asyncio
    async def test_embed_qa_record_success(self):
        """Test successful embedding of a Q&A record."""
        # Import here to avoid import errors if not implemented yet
        from redis_sre_agent.core.docket_tasks import embed_qa_record

        # Mock the QAManager
        mock_qa = QuestionAnswer(
            id="qa-123",
            question="What is Redis?",
            answer="Redis is a fast in-memory database.",
        )

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed = AsyncMock(
            side_effect=[
                b"\x00" * 16,  # question vector
                b"\x01" * 16,  # answer vector
            ]
        )

        mock_qa_manager = MagicMock()
        mock_qa_manager.get_qa = AsyncMock(return_value=mock_qa)
        mock_qa_manager.update_vectors = AsyncMock(return_value=True)

        with (
            patch(
                "redis_sre_agent.core.qa.QAManager",
                return_value=mock_qa_manager,
            ),
            patch(
                "redis_sre_agent.core.redis.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            result = await embed_qa_record(qa_id="qa-123")

        assert result["status"] == "success"
        assert result["qa_id"] == "qa-123"
        mock_qa_manager.get_qa.assert_called_once_with("qa-123")
        mock_qa_manager.update_vectors.assert_called_once()
        assert mock_vectorizer.aembed.call_count == 2

    @pytest.mark.asyncio
    async def test_embed_qa_record_not_found(self):
        """Test embedding when Q&A record doesn't exist."""
        from redis_sre_agent.core.docket_tasks import embed_qa_record

        mock_qa_manager = MagicMock()
        mock_qa_manager.get_qa = AsyncMock(return_value=None)

        with patch(
            "redis_sre_agent.core.qa.QAManager",
            return_value=mock_qa_manager,
        ):
            result = await embed_qa_record(qa_id="nonexistent")

        assert result["status"] == "error"
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_embed_qa_record_vectorizer_error(self):
        """Test handling of vectorizer errors."""
        from redis_sre_agent.core.docket_tasks import embed_qa_record

        mock_qa = QuestionAnswer(
            id="qa-456",
            question="Test?",
            answer="Test.",
        )

        mock_vectorizer = MagicMock()
        mock_vectorizer.aembed = AsyncMock(side_effect=Exception("Embedding failed"))

        mock_qa_manager = MagicMock()
        mock_qa_manager.get_qa = AsyncMock(return_value=mock_qa)

        with (
            patch(
                "redis_sre_agent.core.qa.QAManager",
                return_value=mock_qa_manager,
            ),
            patch(
                "redis_sre_agent.core.redis.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            with pytest.raises(Exception, match="Embedding failed"):
                await embed_qa_record(qa_id="qa-456")

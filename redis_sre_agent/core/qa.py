"""Q&A recording with citation tracking.

Records question-answer pairs with deterministic citations from knowledge search.
Includes feedback support at the data level (thumbs up/down).
Uses RedisVL index for vector search on questions and answers.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from redis.asyncio import Redis
from ulid import ULID

logger = logging.getLogger(__name__)


class Citation(BaseModel):
    """A citation referencing a source document used in generating an answer."""

    document_id: str = Field(description="Unique ID of the cited document")
    document_hash: str = Field(description="Hash of the document for deduplication")
    chunk_index: Optional[int] = Field(
        default=None, description="Index of the chunk within the document"
    )
    title: str = Field(description="Title of the cited document")
    source: str = Field(description="Source URL or path of the document")
    content_preview: Optional[str] = Field(default=None, description="Preview of the cited content")
    score: Optional[float] = Field(default=None, description="Relevance score from vector search")


class Feedback(BaseModel):
    """User feedback on a Q&A pair."""

    accepted: Optional[bool] = Field(
        default=None, description="True=thumbs up, False=thumbs down, None=no feedback"
    )
    feedback_text: Optional[str] = Field(
        default=None, description="Optional text feedback from user"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp when feedback was recorded",
    )


class QuestionAnswer(BaseModel):
    """A recorded Q&A pair with citations and optional feedback."""

    id: str = Field(
        default_factory=lambda: str(ULID()), description="Unique ID for this Q&A record"
    )
    question: str = Field(description="The user's question")
    answer: str = Field(description="The agent's answer")
    citations: List[Citation] = Field(
        default_factory=list, description="List of citations used in the answer"
    )
    feedback: Optional[Feedback] = Field(default=None, description="User feedback on this Q&A")
    user_id: Optional[str] = Field(default=None, description="User who asked the question")
    thread_id: Optional[str] = Field(default=None, description="Thread ID where this Q&A occurred")
    task_id: Optional[str] = Field(default=None, description="Task ID associated with this Q&A")
    question_vector: Optional[bytes] = Field(
        default=None, description="Embedding vector for the question (for semantic search)"
    )
    answer_vector: Optional[bytes] = Field(
        default=None, description="Embedding vector for the answer (for semantic search)"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp when Q&A was recorded",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp when Q&A was last updated",
    )


def _to_epoch(ts: Any) -> float:
    """Convert ISO timestamp string to epoch float."""
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0


class QAManager:
    """Manages Q&A recording with citations in Redis.

    Uses RedisVL index for vector search on questions and answers.
    Stores data as hash with indexed fields + 'data' field for full JSON.
    """

    def __init__(self, redis_url: Optional[str] = None, redis_client: Optional[Redis] = None):
        self._redis_url = redis_url
        self._redis_client = redis_client
        self._index_ensured = False

    async def _get_client(self) -> Redis:
        """Get Redis client (lazy initialization)."""
        if self._redis_client is None:
            from redis_sre_agent.core.redis import get_redis_client

            self._redis_client = get_redis_client(self._redis_url)
        return self._redis_client

    async def _ensure_index_exists(self) -> None:
        """Ensure the Q&A index exists (best-effort, called once per manager instance)."""
        if self._index_ensured:
            return
        try:
            from redis_sre_agent.core.redis import get_qa_index

            index = await get_qa_index()
            if not await index.exists():
                await index.create()
            self._index_ensured = True
        except Exception as e:
            logger.debug(f"Index creation check failed (non-fatal): {e}")

    def citations_from_search_results(
        self,
        search_results: List[Dict[str, Any]],
        max_preview_length: int = 200,
    ) -> List[Citation]:
        """Convert knowledge search results to Citation objects.

        Args:
            search_results: List of search result dicts from knowledge search
            max_preview_length: Maximum length for content preview

        Returns:
            List of Citation objects
        """
        citations = []
        for result in search_results:
            content = result.get("content", "")
            if len(content) > max_preview_length:
                content = content[:max_preview_length] + "..."

            citation = Citation(
                document_id=result.get("id", ""),
                document_hash=result.get("document_hash", ""),
                chunk_index=result.get("chunk_index"),
                title=result.get("title", ""),
                source=result.get("source", ""),
                content_preview=content if content else None,
                score=result.get("score"),
            )
            citations.append(citation)
        return citations

    async def record_qa(
        self,
        question: str,
        answer: str,
        citations: Optional[List[Citation]] = None,
        user_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> QuestionAnswer:
        """Record a Q&A pair with optional citations.

        Args:
            question: The user's question
            answer: The agent's answer
            citations: List of Citation objects for sources used
            user_id: Optional user ID
            thread_id: Optional thread ID
            task_id: Optional task ID

        Returns:
            The recorded QuestionAnswer object
        """
        qa = QuestionAnswer(
            question=question,
            answer=answer,
            citations=citations or [],
            user_id=user_id,
            thread_id=thread_id,
            task_id=task_id,
        )
        await self._save_qa(qa)
        return qa

    async def record_qa_from_search(
        self,
        question: str,
        answer: str,
        search_results: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        task_id: Optional[str] = None,
        max_preview_length: int = 200,
    ) -> QuestionAnswer:
        """Record a Q&A pair with citations from search results.

        Args:
            question: The user's question
            answer: The agent's answer
            search_results: Raw search results from knowledge base
            user_id: Optional user ID
            thread_id: Optional thread ID
            task_id: Optional task ID
            max_preview_length: Max length for content previews

        Returns:
            The recorded QuestionAnswer object with citations
        """
        citations = self.citations_from_search_results(search_results, max_preview_length)
        return await self.record_qa(
            question=question,
            answer=answer,
            citations=citations,
            user_id=user_id,
            thread_id=thread_id,
            task_id=task_id,
        )

    async def _save_qa(self, qa: QuestionAnswer) -> None:
        """Save a Q&A record to Redis using hash storage for RedisVL indexing."""
        from redis_sre_agent.core.redis import SRE_QA_INDEX

        client = await self._get_client()
        await self._ensure_index_exists()

        # Key uses the index prefix for RedisVL compatibility
        key = f"{SRE_QA_INDEX}:{qa.id}"

        # Serialize full Q&A data (excluding vectors which are stored separately)
        qa_dict = qa.model_dump(mode="json", exclude={"question_vector", "answer_vector"})

        # Build hash mapping with indexed fields + full data JSON
        mapping: Dict[str, Any] = {
            "question": qa.question,
            "answer": qa.answer,
            "user_id": qa.user_id or "",
            "thread_id": qa.thread_id or "",
            "task_id": qa.task_id or "",
            "created_at": _to_epoch(qa.created_at),
            "updated_at": _to_epoch(qa.updated_at),
            "data": json.dumps(qa_dict),
        }

        # Add vectors if present (RedisVL handles bytes serialization)
        if qa.question_vector is not None:
            mapping["question_vector"] = qa.question_vector
        if qa.answer_vector is not None:
            mapping["answer_vector"] = qa.answer_vector

        await client.hset(key, mapping=mapping)

        logger.info(f"Recorded Q&A {qa.id} with {len(qa.citations)} citations")

    async def record_feedback(
        self,
        qa_id: str,
        accepted: bool,
        feedback_text: Optional[str] = None,
    ) -> bool:
        """Record feedback on a Q&A pair.

        Args:
            qa_id: ID of the Q&A record
            accepted: True for thumbs up, False for thumbs down
            feedback_text: Optional text feedback

        Returns:
            True if feedback was recorded, False if Q&A not found
        """
        from redis_sre_agent.core.redis import SRE_QA_INDEX

        client = await self._get_client()
        key = f"{SRE_QA_INDEX}:{qa_id}"

        # Get existing data
        data_raw = await client.hget(key, "data")
        if not data_raw:
            logger.warning(f"Q&A {qa_id} not found for feedback")
            return False

        # Parse existing data
        if isinstance(data_raw, bytes):
            data_raw = data_raw.decode("utf-8")
        qa_dict = json.loads(data_raw)

        # Update feedback
        feedback = Feedback(accepted=accepted, feedback_text=feedback_text)
        qa_dict["feedback"] = feedback.model_dump(mode="json")
        qa_dict["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Save back
        await client.hset(
            key,
            mapping={
                "data": json.dumps(qa_dict),
                "updated_at": _to_epoch(qa_dict["updated_at"]),
            },
        )

        logger.info(f"Recorded feedback for Q&A {qa_id}: accepted={accepted}")
        return True

    async def get_qa(self, qa_id: str) -> Optional[QuestionAnswer]:
        """Retrieve a Q&A record by ID.

        Args:
            qa_id: ID of the Q&A record

        Returns:
            QuestionAnswer object if found, None otherwise
        """
        from redis_sre_agent.core.redis import SRE_QA_INDEX

        client = await self._get_client()
        key = f"{SRE_QA_INDEX}:{qa_id}"

        # Get all hash fields
        raw_data = await client.hgetall(key)
        if not raw_data:
            return None

        # Decode bytes keys/values
        data: Dict[str, Any] = {}
        for k, v in raw_data.items():
            k_str = k.decode("utf-8") if isinstance(k, bytes) else k
            data[k_str] = v

        # Parse the JSON data field
        data_json = data.get("data")
        if not data_json:
            return None

        if isinstance(data_json, bytes):
            data_json = data_json.decode("utf-8")

        qa_dict = json.loads(data_json)

        # Add vectors back if present (stored as raw bytes in hash)
        if "question_vector" in data and data["question_vector"]:
            qa_dict["question_vector"] = data["question_vector"]
        if "answer_vector" in data and data["answer_vector"]:
            qa_dict["answer_vector"] = data["answer_vector"]

        return QuestionAnswer.model_validate(qa_dict)

    async def list_qa_by_thread(self, thread_id: str) -> List[QuestionAnswer]:
        """List all Q&A records for a thread.

        Args:
            thread_id: Thread ID to filter by

        Returns:
            List of QuestionAnswer objects
        """
        return await self._search_qa_by_tag("thread_id", thread_id)

    async def list_qa_by_user(self, user_id: str) -> List[QuestionAnswer]:
        """List all Q&A records for a user.

        Args:
            user_id: User ID to filter by

        Returns:
            List of QuestionAnswer objects
        """
        return await self._search_qa_by_tag("user_id", user_id)

    async def list_qa_by_task(self, task_id: str) -> List[QuestionAnswer]:
        """List all Q&A records for a task.

        Args:
            task_id: Task ID to filter by

        Returns:
            List of QuestionAnswer objects
        """
        return await self._search_qa_by_tag("task_id", task_id)

    async def _search_qa_by_tag(self, field: str, value: str) -> List[QuestionAnswer]:
        """Search Q&A records by a TAG field using RedisVL index."""
        from redisvl.query import FilterQuery
        from redisvl.query.filter import Tag

        from redis_sre_agent.core.redis import get_qa_index

        await self._ensure_index_exists()

        try:
            index = await get_qa_index()
            filter_expr = Tag(field) == value
            query = FilterQuery(filter_expression=filter_expr, return_fields=["data"])
            raw_results = await index.query(query)

            results = []
            for result in raw_results:
                data_raw = result.get("data")
                if data_raw:
                    qa = await self._parse_qa_from_data(data_raw)
                    if qa:
                        results.append(qa)
            return results
        except Exception as e:
            logger.warning(f"Search by {field}={value} failed: {e}")
            return []

    async def _parse_qa_from_data(self, data_raw: Any) -> Optional[QuestionAnswer]:
        """Parse Q&A from raw data field."""
        try:
            if isinstance(data_raw, bytes):
                data_raw = data_raw.decode()
            data = json.loads(data_raw)
            return QuestionAnswer.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed to parse Q&A data: {e}")
            return None

    async def delete_qa(self, qa_id: str) -> bool:
        """Delete a Q&A record.

        Args:
            qa_id: ID of the Q&A record to delete

        Returns:
            True if deleted, False if not found
        """
        from redis_sre_agent.core.redis import SRE_QA_INDEX

        client = await self._get_client()
        key = f"{SRE_QA_INDEX}:{qa_id}"

        # Check if record exists
        exists = await client.exists(key)
        if not exists:
            return False

        # Delete the record (index automatically removes it)
        await client.delete(key)

        logger.info(f"Deleted Q&A {qa_id}")
        return True

    async def update_vectors(
        self,
        qa_id: str,
        question_vector: Optional[bytes] = None,
        answer_vector: Optional[bytes] = None,
    ) -> bool:
        """Update vector embeddings on a Q&A record.

        This is called by the Docket task to add embeddings out-of-band
        after the Q&A record has been created.

        Args:
            qa_id: ID of the Q&A record to update
            question_vector: Embedding vector for the question (as bytes)
            answer_vector: Embedding vector for the answer (as bytes)

        Returns:
            True if updated successfully, False if Q&A not found
        """
        from redis_sre_agent.core.redis import SRE_QA_INDEX

        client = await self._get_client()
        key = f"{SRE_QA_INDEX}:{qa_id}"

        # Check if Q&A exists
        exists = await client.exists(key)
        if not exists:
            logger.warning(f"Q&A {qa_id} not found for vector update")
            return False

        # Build mapping for vector updates
        mapping: Dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).timestamp(),
        }

        if question_vector is not None:
            mapping["question_vector"] = question_vector
        if answer_vector is not None:
            mapping["answer_vector"] = answer_vector

        await client.hset(key, mapping=mapping)

        logger.info(f"Updated vectors for Q&A {qa_id}")
        return True

"""
Redis key construction utilities.

Centralizes all Redis key construction to maintain consistency across the codebase.
"""


class RedisKeys:
    """Utility class for constructing Redis keys with consistent naming conventions."""

    # Prefixes
    PREFIX_SRE = "sre"
    PREFIX_KNOWLEDGE = "sre_knowledge"

    # ============================================================================
    # Thread-related keys
    # ============================================================================

    @staticmethod
    def thread_status(thread_id: str) -> str:
        """Key for thread status."""
        return f"sre:thread:{thread_id}:status"

    @staticmethod
    def thread_messages(thread_id: str) -> str:
        """Key for thread messages list (conversation history)."""
        return f"sre:thread:{thread_id}:messages"

    @staticmethod
    def thread_context(thread_id: str) -> str:
        """Key for thread context (conversation history, etc.)."""
        return f"sre:thread:{thread_id}:context"

    @staticmethod
    def thread_metadata(thread_id: str) -> str:
        """Key for thread metadata."""
        return f"sre:thread:{thread_id}:metadata"

    @staticmethod
    def threads_index() -> str:
        """Key for global threads index (sorted set by timestamp)."""
        return "sre:threads:index"

    @staticmethod
    def threads_user_index(user_id: str) -> str:
        """Key for user-specific threads index (sorted set by timestamp)."""
        return f"sre:threads:user:{user_id}"

    @staticmethod
    def thread_instances(thread_id: str) -> str:
        """Key for dynamically created instances in a thread/session."""
        return f"sre:thread:{thread_id}:instances"

    # ============================================================================
    # Instance-related keys
    # ============================================================================

    @staticmethod
    def user_instances(user_id: str) -> str:
        """Key for user's configured instances (set of instance IDs)."""
        return f"sre:user:{user_id}:instances"

    # ============================================================================
    # Knowledge base keys
    # ============================================================================

    @staticmethod
    def knowledge_document(doc_id: str) -> str:
        """Key for a knowledge base document."""
        return f"sre_knowledge:{doc_id}"

    @staticmethod
    def knowledge_chunk(document_hash: str, chunk_index: int) -> str:
        """Key for a specific document chunk."""
        return f"sre_knowledge:{document_hash}:chunk:{chunk_index}"

    @staticmethod
    def knowledge_chunk_pattern(document_hash: str) -> str:
        """Pattern for matching all chunks of a document."""
        return f"sre_knowledge:{document_hash}:chunk:*"

    @staticmethod
    def knowledge_documents() -> str:
        """Key for knowledge documents hash."""
        return "sre_knowledge:documents"

    @staticmethod
    def knowledge_document_meta(document_hash: str) -> str:
        """Key for tracked metadata about one knowledge document."""
        return f"sre_knowledge_meta:{document_hash}"

    @staticmethod
    def knowledge_source_meta(path_hash: str) -> str:
        """Key for tracked metadata about one source-document path."""
        return f"sre_knowledge_meta:source:{path_hash}"

    @staticmethod
    def knowledge_pack_active() -> str:
        """Key for the active knowledge-pack registry payload."""
        return "sre:knowledge_pack:active"

    # ============================================================================
    # Task result keys
    # ============================================================================

    @staticmethod
    def metrics_result(task_id: str) -> str:
        """Key for metrics task result."""
        return f"sre:metrics:{task_id}"

    @staticmethod
    def health_result(task_id: str) -> str:
        """Key for health check task result."""
        return f"sre:health:{task_id}"

    # ============================================================================
    # Task (per-turn) keys
    # ============================================================================

    @staticmethod
    def task_status(task_id: str) -> str:
        return f"sre:task:{task_id}:status"

    @staticmethod
    def task_updates(task_id: str) -> str:
        return f"sre:task:{task_id}:updates"

    @staticmethod
    def task_result(task_id: str) -> str:
        return f"sre:task:{task_id}:result"

    @staticmethod
    def task_error(task_id: str) -> str:
        return f"sre:task:{task_id}:error"

    @staticmethod
    def task_metadata(task_id: str) -> str:
        return f"sre:task:{task_id}:metadata"

    @staticmethod
    def task_approvals(task_id: str) -> str:
        """Sorted set of approval_ids for a task (score=requested timestamp)."""
        return f"sre:task:{task_id}:approvals"

    @staticmethod
    def task_resume_state(task_id: str) -> str:
        """Key for persisted graph resume state for a task."""
        return f"sre:task:{task_id}:resume_state"

    @staticmethod
    def approval(approval_id: str) -> str:
        """Key for a serialized approval record."""
        return f"sre:approval:{approval_id}"

    @staticmethod
    def approvals_pending() -> str:
        """Sorted set of pending approval_ids (score=requested timestamp)."""
        return "sre:approvals:pending"

    @staticmethod
    def approval_execution(approval_id: str, action_hash: str) -> str:
        """Key for the execution ledger entry of an approved action."""
        return f"sre:approval_execution:{approval_id}:{action_hash}"

    @staticmethod
    def message_decision_trace(message_id: str) -> str:
        """Key for message decision trace (tool calls for a specific message).

        Decision traces are always associated with messages (not tasks).
        Tasks contain messages, so traces can be retrieved via message_id
        from the message metadata.
        """
        return f"sre:message:{message_id}:decision_trace"

    @staticmethod
    def thread_tasks_index(thread_id: str) -> str:
        """Sorted set of task_ids for a thread (score=timestamp)."""
        return f"sre:thread:{thread_id}:tasks"

    @staticmethod
    def schedule_key(schedule_id: str) -> str:
        """Key for a schedule definition (legacy-compatible)."""
        # Schedules use underscore prefix for historical compatibility
        return f"sre_schedules:{schedule_id}"

    # ============================================================================
    # Stream keys (for WebSocket updates)
    # ============================================================================

    @staticmethod
    def task_stream(thread_id: str) -> str:
        """Key for task update stream."""
        return f"sre:stream:task:{thread_id}"

    # ============================================================================
    # Helper methods
    # ============================================================================

    @staticmethod
    def all_thread_keys(thread_id: str) -> dict[str, str]:
        """
        Get all keys associated with a thread.

        Returns:
            Dictionary mapping key names to their Redis keys
        """
        return {
            "status": RedisKeys.thread_status(thread_id),
            "messages": RedisKeys.thread_messages(thread_id),
            "context": RedisKeys.thread_context(thread_id),
            "metadata": RedisKeys.thread_metadata(thread_id),
        }

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
    def thread_updates(thread_id: str) -> str:
        """Key for thread updates list."""
        return f"sre:thread:{thread_id}:updates"

    @staticmethod
    def thread_context(thread_id: str) -> str:
        """Key for thread context (conversation history, etc.)."""
        return f"sre:thread:{thread_id}:context"

    @staticmethod
    def thread_action_items(thread_id: str) -> str:
        """Key for thread action items."""
        return f"sre:thread:{thread_id}:action_items"

    @staticmethod
    def thread_metadata(thread_id: str) -> str:
        """Key for thread metadata."""
        return f"sre:thread:{thread_id}:metadata"

    @staticmethod
    def thread_result(thread_id: str) -> str:
        """Key for thread result."""
        return f"sre:thread:{thread_id}:result"

    @staticmethod
    def thread_error(thread_id: str) -> str:
        """Key for thread error information."""
        return f"sre:thread:{thread_id}:error"

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

    # ============================================================================
    # Instance-related keys
    # ============================================================================

    @staticmethod
    def instances_set() -> str:
        """Key for the set of all instance IDs."""
        return "sre:instances"

    @staticmethod
    def instance(instance_id: str) -> str:
        """Key for a specific Redis instance configuration."""
        return f"sre:instance:{instance_id}"

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
            "updates": RedisKeys.thread_updates(thread_id),
            "context": RedisKeys.thread_context(thread_id),
            "action_items": RedisKeys.thread_action_items(thread_id),
            "metadata": RedisKeys.thread_metadata(thread_id),
            "result": RedisKeys.thread_result(thread_id),
            "error": RedisKeys.thread_error(thread_id),
        }

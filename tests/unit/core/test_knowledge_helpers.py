"""Tests for knowledge helper functions."""

import inspect

from redis_sre_agent.core.knowledge_helpers import (
    get_all_document_fragments,
    get_related_document_fragments,
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

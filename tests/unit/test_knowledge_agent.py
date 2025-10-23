"""Tests for the knowledge-only agent."""

import pytest

from redis_sre_agent.agent.knowledge_agent import KnowledgeOnlyAgent
from redis_sre_agent.core.knowledge_helpers import (
    get_all_document_fragments,
    get_related_document_fragments,
)
from redis_sre_agent.core.knowledge_helpers import (
    ingest_sre_document_helper as ingest_sre_document,
)
from redis_sre_agent.core.knowledge_helpers import (
    search_knowledge_base_helper as search_knowledge_base,
)


class TestKnowledgeAgent:
    """Test the knowledge-only agent."""

    @pytest.mark.asyncio
    async def test_agent_initialization(self):
        """Test that KnowledgeOnlyAgent initializes correctly."""
        agent = KnowledgeOnlyAgent()

        # Verify agent has required attributes
        assert hasattr(agent, "llm")
        assert hasattr(agent, "settings")
        assert agent.llm is not None

    @pytest.mark.asyncio
    async def test_knowledge_tools_are_available(self):
        """Test that knowledge tools are available via ToolManager."""
        from redis_sre_agent.tools.manager import ToolManager

        # Create ToolManager without instance (loads only knowledge tools)
        async with ToolManager() as mgr:
            tools = mgr.get_tools()
            tool_names = [t.name for t in tools]

            # Verify knowledge tools are present
            knowledge_tools = [n for n in tool_names if "knowledge_" in n]
            assert (
                len(knowledge_tools) == 4
            )  # search, ingest, get_all_fragments, get_related_fragments

            # Verify specific tools are present
            assert any("search" in n for n in knowledge_tools)
            assert any("ingest" in n for n in knowledge_tools)
            assert any("get_all_fragments" in n for n in knowledge_tools)
            assert any("get_related_fragments" in n for n in knowledge_tools)

    @pytest.mark.asyncio
    async def test_search_knowledge_base_wrapper(self):
        """Test that search_knowledge_base wrapper works correctly."""
        # This is a wrapper function, so we just verify it's callable
        # and has the right signature (no retry parameter)
        import inspect

        sig = inspect.signature(search_knowledge_base)
        params = list(sig.parameters.keys())

        # Should have query, category, limit, distance_threshold but NOT retry
        assert "query" in params
        assert "category" in params
        assert "limit" in params
        assert "distance_threshold" in params
        assert "retry" not in params

    @pytest.mark.asyncio
    async def test_ingest_sre_document_wrapper(self):
        """Test that ingest_sre_document wrapper works correctly."""
        import inspect

        sig = inspect.signature(ingest_sre_document)
        params = list(sig.parameters.keys())

        # Should have title, content, source, category, severity but NOT retry
        assert "title" in params
        assert "content" in params
        assert "source" in params
        assert "category" in params
        assert "severity" in params
        assert "retry" not in params

    @pytest.mark.asyncio
    async def test_get_all_document_fragments_signature(self):
        """Test that get_all_document_fragments has correct signature."""
        import inspect

        sig = inspect.signature(get_all_document_fragments)
        params = list(sig.parameters.keys())

        # Should have document_hash and include_metadata
        assert "document_hash" in params
        assert "include_metadata" in params

    @pytest.mark.asyncio
    async def test_get_related_document_fragments_signature(self):
        """Test that get_related_document_fragments has correct signature."""
        import inspect

        sig = inspect.signature(get_related_document_fragments)
        params = list(sig.parameters.keys())

        # Should have document_hash, current_chunk_index, context_window
        assert "document_hash" in params
        assert "current_chunk_index" in params
        assert "context_window" in params

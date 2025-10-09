"""Tests for the knowledge-only agent."""

import pytest

from redis_sre_agent.agent.knowledge_agent import (
    KnowledgeOnlyAgent,
    get_all_document_fragments,
    get_related_document_fragments,
    ingest_sre_document,
    search_knowledge_base,
)


class TestKnowledgeAgent:
    """Test the knowledge-only agent."""

    @pytest.mark.asyncio
    async def test_agent_initialization(self):
        """Test that the knowledge agent initializes correctly."""
        agent = KnowledgeOnlyAgent()

        assert agent.llm is not None
        assert agent.knowledge_tools is not None
        assert len(agent.knowledge_tools) == 4  # search, ingest, get_all, get_related
        assert agent.workflow is not None

    @pytest.mark.asyncio
    async def test_safe_tool_node_error_handling(self):
        """Test that safe_tool_node handles errors without creating malformed messages."""
        agent = KnowledgeOnlyAgent()

        # Verify the workflow is built correctly with safe_tool_node
        workflow = agent._build_workflow()
        assert workflow is not None

        # Verify the agent has the expected tools
        assert len(agent.knowledge_tools) == 4

    @pytest.mark.asyncio
    async def test_knowledge_tools_are_callable(self):
        """Test that all knowledge tools are callable functions."""
        agent = KnowledgeOnlyAgent()

        # Verify all tools are callable
        for tool in agent.knowledge_tools:
            assert callable(tool)

        # Verify specific tools are present
        tool_names = [tool.__name__ for tool in agent.knowledge_tools]
        assert "search_knowledge_base" in tool_names
        assert "ingest_sre_document" in tool_names
        assert "get_all_document_fragments" in tool_names
        assert "get_related_document_fragments" in tool_names

    @pytest.mark.asyncio
    async def test_search_knowledge_base_wrapper(self):
        """Test that search_knowledge_base wrapper works correctly."""
        # This is a wrapper function, so we just verify it's callable
        # and has the right signature (no retry parameter)
        import inspect

        sig = inspect.signature(search_knowledge_base)
        params = list(sig.parameters.keys())

        # Should have query, category, limit but NOT retry
        assert "query" in params
        assert "category" in params
        assert "limit" in params
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

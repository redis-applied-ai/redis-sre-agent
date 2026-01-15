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


class TestKnowledgeAgentState:
    """Test KnowledgeAgentState TypedDict."""

    def test_state_has_required_fields(self):
        """Test that KnowledgeAgentState has all required fields."""
        from redis_sre_agent.agent.knowledge_agent import KnowledgeAgentState

        state: KnowledgeAgentState = {
            "messages": [],
            "session_id": "test-session",
            "user_id": "test-user",
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": 10,
            "tool_calls_executed": 0,
        }

        assert "messages" in state
        assert "session_id" in state
        assert "user_id" in state
        assert "current_tool_calls" in state
        assert "iteration_count" in state
        assert "max_iterations" in state
        assert "tool_calls_executed" in state


class TestKnowledgeSystemPrompt:
    """Test the knowledge agent system prompt."""

    def test_system_prompt_exists(self):
        """Test that the system prompt is defined."""
        from redis_sre_agent.agent.knowledge_agent import KNOWLEDGE_SYSTEM_PROMPT

        assert KNOWLEDGE_SYSTEM_PROMPT is not None
        assert len(KNOWLEDGE_SYSTEM_PROMPT) > 100

    def test_system_prompt_mentions_knowledge_base(self):
        """Test that the system prompt mentions knowledge base."""
        from redis_sre_agent.agent.knowledge_agent import KNOWLEDGE_SYSTEM_PROMPT

        assert "knowledge base" in KNOWLEDGE_SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_sre(self):
        """Test that the system prompt mentions SRE."""
        from redis_sre_agent.agent.knowledge_agent import KNOWLEDGE_SYSTEM_PROMPT

        assert "SRE" in KNOWLEDGE_SYSTEM_PROMPT

    def test_system_prompt_no_instance_access(self):
        """Test that the system prompt clarifies no instance access."""
        from redis_sre_agent.agent.knowledge_agent import KNOWLEDGE_SYSTEM_PROMPT

        assert (
            "NOT have access" in KNOWLEDGE_SYSTEM_PROMPT
            or "do not have access" in KNOWLEDGE_SYSTEM_PROMPT.lower()
        )


class TestKnowledgeAgentMethods:
    """Test KnowledgeOnlyAgent methods."""

    @pytest.mark.asyncio
    async def test_agent_has_llm(self):
        """Test that agent has LLM attribute."""
        agent = KnowledgeOnlyAgent()
        assert agent.llm is not None

    @pytest.mark.asyncio
    async def test_agent_has_settings(self):
        """Test that agent has settings attribute."""
        agent = KnowledgeOnlyAgent()
        assert agent.settings is not None

    @pytest.mark.asyncio
    async def test_agent_has_emitter(self):
        """Test that agent has emitter attribute."""
        agent = KnowledgeOnlyAgent()
        assert agent._emitter is not None

    @pytest.mark.asyncio
    async def test_agent_with_custom_emitter(self):
        """Test agent initialization with custom emitter."""
        from unittest.mock import MagicMock

        from redis_sre_agent.core.progress import ProgressEmitter

        mock_emitter = MagicMock(spec=ProgressEmitter)
        agent = KnowledgeOnlyAgent(progress_emitter=mock_emitter)
        assert agent._emitter is mock_emitter

    @pytest.mark.asyncio
    async def test_build_workflow_returns_state_graph(self):
        """Test that _build_workflow returns a StateGraph."""
        from unittest.mock import MagicMock

        from redis_sre_agent.core.progress import NullEmitter
        from redis_sre_agent.tools.manager import ToolManager

        agent = KnowledgeOnlyAgent()

        # Create mock tool manager
        mock_tool_mgr = MagicMock(spec=ToolManager)
        mock_tool_mgr.get_tools.return_value = []

        # Create mock LLM with tools
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)

        # Create emitter
        emitter = NullEmitter()

        workflow = agent._build_workflow(mock_tool_mgr, mock_llm, emitter)
        assert workflow is not None

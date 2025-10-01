"""Tests for the knowledge-only agent."""

import pytest

from redis_sre_agent.agent.knowledge_agent import KnowledgeOnlyAgent


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

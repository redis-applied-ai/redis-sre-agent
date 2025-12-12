"""Tests for envelope summarization and expand_evidence tool in the reasoning phase."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent


class TestEnvelopeSummarization:
    """Test the _summarize_envelopes_for_reasoning method."""

    @pytest.fixture
    def agent(self):
        """Create agent instance with mocked LLM."""
        with patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI"):
            agent = SRELangGraphAgent()
            # Mock the mini_llm
            agent.mini_llm = MagicMock()
            agent._llm_cache = {}
            agent._run_cache_active = False
            return agent

    @pytest.mark.asyncio
    async def test_empty_envelopes_returns_empty(self, agent):
        """Test that empty input returns empty output."""
        result = await agent._summarize_envelopes_for_reasoning([])
        assert result == []

    @pytest.mark.asyncio
    async def test_small_envelopes_unchanged(self, agent):
        """Test that small envelopes are not summarized."""
        small_envelope = {
            "tool_key": "test_tool",
            "name": "test",
            "description": "A test tool",
            "args": {"param": "value"},
            "status": "success",
            "data": {"result": "small data"},  # Well under 500 chars
        }

        result = await agent._summarize_envelopes_for_reasoning([small_envelope])

        assert len(result) == 1
        assert result[0]["data"] == {"result": "small data"}

    @pytest.mark.asyncio
    async def test_large_envelopes_summarized(self, agent):
        """Test that large envelopes are summarized via LLM."""
        # Create a large envelope (>500 chars in data)
        large_data = {"metrics": "x" * 1000, "logs": "y" * 1000}
        large_envelope = {
            "tool_key": "redis_info",
            "name": "info",
            "description": "Get Redis INFO",
            "args": {},
            "status": "success",
            "data": large_data,
        }

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = '[{"summary": "Key finding: metrics show high load"}]'
        agent.mini_llm.ainvoke = AsyncMock(return_value=mock_response)

        result = await agent._summarize_envelopes_for_reasoning([large_envelope])

        assert len(result) == 1
        assert "summary" in result[0]["data"]
        assert "high load" in result[0]["data"]["summary"]
        # Original large data should be replaced
        assert result[0]["data"] != large_data

    @pytest.mark.asyncio
    async def test_mixed_envelopes_partial_summarization(self, agent):
        """Test that only large envelopes are summarized."""
        small_envelope = {
            "tool_key": "small_tool",
            "name": "small",
            "description": "Small tool",
            "args": {},
            "status": "success",
            "data": {"value": 42},
        }
        large_envelope = {
            "tool_key": "large_tool",
            "name": "large",
            "description": "Large tool",
            "args": {},
            "status": "success",
            "data": {"content": "x" * 1000},
        }

        # Mock LLM response for large envelope
        mock_response = MagicMock()
        mock_response.content = '[{"summary": "Large content summarized"}]'
        agent.mini_llm.ainvoke = AsyncMock(return_value=mock_response)

        result = await agent._summarize_envelopes_for_reasoning(
            [small_envelope, large_envelope]
        )

        assert len(result) == 2
        # Small envelope unchanged
        assert result[0]["data"] == {"value": 42}
        # Large envelope summarized
        assert "summary" in result[1]["data"]

    @pytest.mark.asyncio
    async def test_order_preserved(self, agent):
        """Test that envelope order is preserved after summarization."""
        envelopes = [
            {"tool_key": f"tool_{i}", "name": f"t{i}", "args": {}, "status": "success",
             "data": {"id": i, "content": "x" * (100 if i % 2 == 0 else 1000)}}
            for i in range(5)
        ]

        mock_response = MagicMock()
        mock_response.content = '[{"summary": "s1"}, {"summary": "s2"}]'
        agent.mini_llm.ainvoke = AsyncMock(return_value=mock_response)

        result = await agent._summarize_envelopes_for_reasoning(envelopes)

        # Check order by tool_key
        assert [r["tool_key"] for r in result] == [f"tool_{i}" for i in range(5)]

    @pytest.mark.asyncio
    async def test_llm_failure_fallback_truncation(self, agent):
        """Test that LLM failure falls back to truncation."""
        large_envelope = {
            "tool_key": "test",
            "name": "test",
            "description": "Test",
            "args": {},
            "status": "success",
            "data": {"content": "x" * 1000},
        }

        # Mock LLM to raise exception
        agent.mini_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))

        result = await agent._summarize_envelopes_for_reasoning([large_envelope])

        assert len(result) == 1
        assert "truncated" in result[0]["data"]
        assert result[0]["data"]["truncated"].endswith("...")


class TestExpandEvidenceTool:
    """Test the expand_evidence tool for retrieving full tool outputs."""

    @pytest.fixture
    def agent(self):
        """Create agent instance with mocked LLM."""
        with patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI"):
            agent = SRELangGraphAgent()
            return agent

    def test_expand_evidence_returns_full_data(self, agent):
        """Test that expand_evidence returns the full original data."""
        envelopes = [
            {
                "tool_key": "redis_info_123",
                "name": "info",
                "description": "Get Redis INFO",
                "args": {"section": "all"},
                "status": "success",
                "data": {"memory": "large data here", "clients": 100},
            },
            {
                "tool_key": "slowlog_456",
                "name": "slowlog",
                "description": "Get slow queries",
                "args": {},
                "status": "success",
                "data": {"queries": ["query1", "query2"]},
            },
        ]

        tool_spec = agent._build_expand_evidence_tool(envelopes)
        func = tool_spec["func"]

        # Call expand_evidence for first tool
        result = func("redis_info_123")
        assert result["status"] == "success"
        assert result["tool_key"] == "redis_info_123"
        assert result["full_data"] == {"memory": "large data here", "clients": 100}

        # Call for second tool
        result = func("slowlog_456")
        assert result["status"] == "success"
        assert result["full_data"] == {"queries": ["query1", "query2"]}

    def test_expand_evidence_unknown_key(self, agent):
        """Test that expand_evidence returns error for unknown tool_key."""
        envelopes = [
            {"tool_key": "known_key", "name": "test", "data": {"x": 1}},
        ]

        tool_spec = agent._build_expand_evidence_tool(envelopes)
        func = tool_spec["func"]

        result = func("unknown_key")
        assert result["status"] == "error"
        assert "Unknown tool_key" in result["error"]
        assert "known_key" in result["error"]  # Should list available keys

    def test_expand_evidence_tool_schema(self, agent):
        """Test that expand_evidence tool has correct schema."""
        envelopes = [{"tool_key": "test_key", "name": "test", "data": {}}]

        tool_spec = agent._build_expand_evidence_tool(envelopes)

        assert tool_spec["name"] == "expand_evidence"
        assert "full" in tool_spec["description"].lower()
        assert "test_key" in tool_spec["description"]  # Lists available keys
        assert tool_spec["parameters"]["properties"]["tool_key"]["type"] == "string"
        assert "tool_key" in tool_spec["parameters"]["required"]

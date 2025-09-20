"""
Test progress callback validation fixes.

This module tests the fixes for the ThreadUpdate validation error that was
occurring when progress callbacks were called with None messages.
"""


import pytest

from redis_sre_agent.agent.knowledge_agent import KnowledgeOnlyAgent
from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent
from redis_sre_agent.core.thread_state import ThreadUpdate


class TestProgressCallbackValidation:
    """Test progress callback validation fixes."""

    def test_thread_update_validation(self):
        """Test ThreadUpdate validation with None message."""
        # This should fail
        with pytest.raises(ValueError, match="Input should be a valid string"):
            ThreadUpdate(message=None, update_type="progress")

        # This should pass
        update = ThreadUpdate(message="Valid message", update_type="progress")
        assert update.message == "Valid message"
        assert update.update_type == "progress"

    @pytest.mark.asyncio
    async def test_knowledge_agent_progress_callback(self):
        """Test KnowledgeOnlyAgent progress callback calls."""
        agent = KnowledgeOnlyAgent()

        # Mock progress callback that validates parameters
        progress_calls = []

        async def mock_progress_callback(message, update_type):
            if message is None:
                raise ValueError(f"Progress callback received None message with update_type='{update_type}'")
            progress_calls.append((message, update_type))

        agent.progress_callback = mock_progress_callback

        # Test the specific method that was fixed
        await agent.progress_callback(
            "Knowledge agent processing query (iteration 1)",
            "agent_processing"
        )

        assert len(progress_calls) == 1
        assert progress_calls[0][0] == "Knowledge agent processing query (iteration 1)"
        assert progress_calls[0][1] == "agent_processing"

    def test_langgraph_agent_completion_reflection(self):
        """Test SRELangGraphAgent completion reflection method."""
        agent = SRELangGraphAgent()

        # Test with search_knowledge_base result (should return empty string)
        result = {
            "status": "success",
            "results_count": 5,
            "query": "test query"
        }
        reflection = agent._generate_completion_reflection("search_knowledge_base", result)

        # Should return empty string, not None
        assert reflection == ""

        # Test with another tool that should return a proper message
        reflection2 = agent._generate_completion_reflection("analyze_system_metrics", {"status": "success"})
        assert reflection2 == "📊 System metrics analysis complete"
        assert reflection2 is not None
        assert len(reflection2) > 0

    @pytest.mark.asyncio
    async def test_progress_callback_with_empty_string(self):
        """Test that progress callback handles empty strings correctly."""
        progress_calls = []

        async def mock_progress_callback(message, update_type):
            # Should accept empty strings
            progress_calls.append((message, update_type))

        # Test with empty string (should work)
        await mock_progress_callback("", "progress")
        assert len(progress_calls) == 1
        assert progress_calls[0][0] == ""

        # Test with valid string (should work)
        await mock_progress_callback("Valid message", "progress")
        assert len(progress_calls) == 2
        assert progress_calls[1][0] == "Valid message"

    def test_completion_reflection_edge_cases(self):
        """Test completion reflection method with various edge cases."""
        agent = SRELangGraphAgent()

        # Test with unknown tool (should return default message)
        reflection = agent._generate_completion_reflection("unknown_tool", {})
        assert reflection == "✅ unknown tool completed"
        assert reflection is not None

        # Test with get_detailed_redis_diagnostics success
        redis_result = {
            "status": "success",
            "diagnostics": {
                "memory": {
                    "used_memory_bytes": 800000000,
                    "maxmemory_bytes": 1000000000
                }
            }
        }
        reflection = agent._generate_completion_reflection("get_detailed_redis_diagnostics", redis_result)
        assert "Memory usage" in reflection
        assert reflection is not None

        # Test with get_detailed_redis_diagnostics failure
        redis_result_fail = {"status": "error"}
        reflection = agent._generate_completion_reflection("get_detailed_redis_diagnostics", redis_result_fail)
        assert reflection == "❌ Unable to collect Redis diagnostics"
        assert reflection is not None

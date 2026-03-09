"""Unit tests for the agent router."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from redis_sre_agent.agent.router import (
    AgentType,
    format_conversation_context,
    route_to_appropriate_agent,
)


class TestAgentTypeEnum:
    """Test the AgentType enum."""

    def test_agent_types_exist(self):
        """Test that all expected agent types exist."""
        assert AgentType.REDIS_TRIAGE.value == "redis_triage"
        assert AgentType.REDIS_CHAT.value == "redis_chat"
        assert AgentType.KNOWLEDGE_ONLY.value == "knowledge_only"

    def test_redis_focused_is_alias_for_triage(self):
        """Test that REDIS_FOCUSED is an alias for REDIS_TRIAGE."""
        # In Python enums, same value = same member
        assert AgentType.REDIS_FOCUSED is AgentType.REDIS_TRIAGE
        assert AgentType.REDIS_FOCUSED.value == "redis_triage"


@pytest.mark.asyncio
class TestRouteToAppropriateAgent:
    """Test the route_to_appropriate_agent function."""

    async def test_no_instance_routes_to_knowledge(self):
        """Test that queries without instance context route to knowledge agent."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "KNOWLEDGE_ONLY"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="What are Redis best practices?",
                context=None,
            )

            assert result == AgentType.KNOWLEDGE_ONLY

    async def test_instance_with_deep_triage_request_routes_to_triage(self):
        """Test that deep triage requests with instance route to triage agent."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "DEEP_TRIAGE"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="Do a deep triage on my Redis",
                context={"instance_id": "test-instance"},
            )

            assert result == AgentType.REDIS_TRIAGE

    async def test_instance_with_quick_question_routes_to_chat(self):
        """Test that quick questions with instance route to chat agent."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "CHAT"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="What's the memory usage?",
                context={"instance_id": "test-instance"},
            )

            assert result == AgentType.REDIS_CHAT

    async def test_llm_error_with_instance_defaults_to_chat(self):
        """Test that LLM errors with instance default to chat agent."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="Check something",
                context={"instance_id": "test-instance"},
            )

            assert result == AgentType.REDIS_CHAT

    async def test_llm_error_without_instance_defaults_to_knowledge(self):
        """Test that LLM errors without instance default to knowledge agent."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="What is Redis?",
                context=None,
            )

            assert result == AgentType.KNOWLEDGE_ONLY

    async def test_user_preference_respected(self):
        """Test that user preferences are respected when instance exists."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            # LLM should not be called when preference is set
            mock_create.return_value = MagicMock()

            result = await route_to_appropriate_agent(
                query="Some query",
                context={"instance_id": "test-instance"},
                user_preferences={"preferred_agent": "redis_triage"},
            )

            assert result == AgentType.REDIS_TRIAGE

    async def test_deep_dive_triggers_triage(self):
        """Test that 'deep dive' keywords trigger triage routing."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "DEEP_TRIAGE"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="Go deep on this issue",
                context={"instance_id": "test-instance"},
            )

            assert result == AgentType.REDIS_TRIAGE

    async def test_full_health_check_routes_to_chat(self):
        """Test that 'full health check' (without deep keywords) routes to chat.

        The chat agent has all the same tools and can handle comprehensive requests.
        Only explicit 'deep' keywords should trigger triage.
        """
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "CHAT"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="Run a full health check on my Redis",
                context={"instance_id": "test-instance"},
            )

            assert result == AgentType.REDIS_CHAT

    async def test_unexpected_llm_response_defaults_to_chat(self):
        """Test that unexpected LLM responses default to chat when instance exists."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "UNEXPECTED_VALUE"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="Some query",
                context={"instance_id": "test-instance"},
            )

            # Should default to CHAT when unexpected value with instance
            assert result == AgentType.REDIS_CHAT

    async def test_support_package_routes_to_triage(self):
        """Test that queries with support_package_path route to triage agent.

        Regression test: support packages require diagnostic tools that are
        only available in the triage agent, not the knowledge agent.
        """
        # No LLM should be called - support package takes precedence
        result = await route_to_appropriate_agent(
            query="What databases are in this package?",
            context={"support_package_path": "/tmp/extracted/package-123"},
        )

        assert result == AgentType.REDIS_TRIAGE

    async def test_support_package_with_instance_routes_to_triage(self):
        """Test that queries with both instance and support package route to triage."""
        # No LLM should be called - support package takes precedence
        result = await route_to_appropriate_agent(
            query="Compare current memory with package snapshot",
            context={
                "instance_id": "test-instance",
                "support_package_path": "/tmp/extracted/package-123",
            },
        )

        assert result == AgentType.REDIS_TRIAGE

    async def test_cluster_context_with_quick_query_routes_to_chat(self):
        """Cluster-scoped queries should use the same LLM triage/chat split as instance scope."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "CHAT"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="Check cluster health",
                context={"cluster_id": "cluster-prod-1"},
            )

            assert result == AgentType.REDIS_CHAT

    async def test_cluster_context_with_db_diagnostic_query_auto_upgrades_to_triage(self):
        """Cluster-scoped DB diagnostic queries should auto-upgrade to triage."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "CHAT"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="check memory and clients for this cluster",
                context={"cluster_id": "cluster-prod-1"},
            )

            assert result == AgentType.REDIS_TRIAGE

    async def test_cluster_context_with_db_word_auto_upgrades_to_triage(self):
        """A standalone 'db' term should trigger cluster diagnostic auto-upgrade."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "CHAT"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="check db health for this cluster",
                context={"cluster_id": "cluster-prod-1"},
            )

            assert result == AgentType.REDIS_TRIAGE

    async def test_cluster_context_with_db_substring_does_not_auto_upgrade(self):
        """Words containing 'db' as a substring should not trigger auto-upgrade."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "CHAT"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="share feedback on this cluster",
                context={"cluster_id": "cluster-prod-1"},
            )

            assert result == AgentType.REDIS_CHAT

    async def test_cluster_context_with_deep_request_routes_to_triage(self):
        """Cluster-scoped deep triage requests should route to triage."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "DEEP_TRIAGE"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="Do a deep triage on this cluster",
                context={"cluster_id": "cluster-prod-1"},
            )

            assert result == AgentType.REDIS_TRIAGE

    async def test_cluster_context_llm_error_uses_context_for_auto_upgrade(self):
        """LLM-failure fallback should still auto-upgrade based on conversation context."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_create.side_effect = Exception("LLM unavailable")

            result = await route_to_appropriate_agent(
                query="yes, check that",
                context={"cluster_id": "cluster-prod-1"},
                conversation_history=[
                    HumanMessage(content="check memory and clients for this cluster")
                ],
            )

            assert result == AgentType.REDIS_TRIAGE

    async def test_cluster_context_user_preference_respected(self):
        """Cluster-scoped queries should honor preferred_agent like instance-scoped queries."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            # LLM should not be called when preference is set
            mock_create.return_value = MagicMock()

            result = await route_to_appropriate_agent(
                query="check cluster",
                context={"cluster_id": "cluster-prod-1"},
                user_preferences={"preferred_agent": "redis_triage"},
            )

            assert result == AgentType.REDIS_TRIAGE

    async def test_conversation_history_passed_to_llm(self):
        """Test that conversation history is included in the routing decision."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "CHAT"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            conversation_history = [
                HumanMessage(content="Check the Redis config files"),
                AIMessage(content="I found app/db.py and config/redis.py"),
            ]

            result = await route_to_appropriate_agent(
                query="sure, check them out",
                context={"instance_id": "test-instance"},
                conversation_history=conversation_history,
            )

            # Verify the LLM was called with context
            mock_llm.ainvoke.assert_called_once()
            call_args = mock_llm.ainvoke.call_args[0][0]
            # The HumanMessage should contain conversation context
            human_msg = call_args[1]
            assert "sure, check them out" in human_msg.content
            assert "Recent conversation context" in human_msg.content
            assert "Check the Redis config files" in human_msg.content

            assert result == AgentType.REDIS_CHAT


class TestFormatConversationContext:
    """Test the format_conversation_context helper function."""

    def test_empty_history_returns_empty_string(self):
        """Test that empty history returns empty string."""
        assert format_conversation_context(None) == ""
        assert format_conversation_context([]) == ""

    def test_formats_messages_correctly(self):
        """Test that messages are formatted with User/Assistant labels."""
        history = [
            HumanMessage(content="What is Redis?"),
            AIMessage(content="Redis is an in-memory database."),
        ]
        result = format_conversation_context(history)

        assert "Recent conversation context" in result
        assert "User: What is Redis?" in result
        assert "Assistant: Redis is an in-memory database." in result

    def test_limits_to_max_messages(self):
        """Test that only the last N messages are included."""
        history = [
            HumanMessage(content="Message 1"),
            AIMessage(content="Response 1"),
            HumanMessage(content="Message 2"),
            AIMessage(content="Response 2"),
            HumanMessage(content="Message 3"),
            AIMessage(content="Response 3"),
        ]
        # Default max is 4 messages
        result = format_conversation_context(history, max_messages=4)

        assert "Message 1" not in result
        assert "Response 1" not in result
        assert "Message 2" in result
        assert "Response 2" in result
        assert "Message 3" in result
        assert "Response 3" in result

    def test_truncates_long_messages(self):
        """Test that very long messages are truncated."""
        long_content = "x" * 1000
        history = [HumanMessage(content=long_content)]
        result = format_conversation_context(history)

        # Should be truncated to 500 chars + "..."
        assert "..." in result
        assert len(result) < 1000

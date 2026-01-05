"""Unit tests for the agent router."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.agent.router import AgentType, route_to_appropriate_agent


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

    async def test_instance_with_triage_request_routes_to_triage(self):
        """Test that triage requests with instance route to triage agent."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "TRIAGE"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="Run a full health check on my Redis",
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

    async def test_comprehensive_triggers_triage(self):
        """Test that 'comprehensive' keyword triggers triage routing."""
        with patch("redis_sre_agent.agent.router.create_nano_llm") as mock_create:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "TRIAGE"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_llm

            result = await route_to_appropriate_agent(
                query="Give me a comprehensive analysis",
                context={"instance_id": "test-instance"},
            )

            assert result == AgentType.REDIS_TRIAGE

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

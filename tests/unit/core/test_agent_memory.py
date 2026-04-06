"""Unit tests for Redis Agent Memory Server integration helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.agent_memory import AgentMemoryService, TurnMemoryContext


@pytest.fixture
def memory_settings(monkeypatch):
    monkeypatch.setattr("redis_sre_agent.core.agent_memory.settings.agent_memory_enabled", True)
    monkeypatch.setattr(
        "redis_sre_agent.core.agent_memory.settings.agent_memory_base_url",
        "http://memory.local",
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.agent_memory.settings.agent_memory_namespace",
        "redis-sre-agent-user",
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.agent_memory.settings.agent_memory_asset_namespace",
        "redis-sre-agent-asset",
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.agent_memory.settings.agent_memory_model_name",
        "gpt-5-mini",
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.agent_memory.settings.agent_memory_retrieval_limit",
        5,
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.agent_memory.settings.agent_memory_recent_message_limit",
        8,
    )


class TestPrepareTurnContext:
    @pytest.mark.asyncio
    async def test_returns_disabled_when_feature_off(self, monkeypatch):
        monkeypatch.setattr("redis_sre_agent.core.agent_memory.settings.agent_memory_enabled", False)
        service = AgentMemoryService()

        result = await service.prepare_turn_context(
            query="hello",
            session_id="session-1",
            user_id="user-1",
        )

        assert isinstance(result, TurnMemoryContext)
        assert result.status == "disabled"
        assert result.system_prompt is None

    @pytest.mark.asyncio
    async def test_loads_user_and_asset_memory_when_both_scopes_present(self, memory_settings):
        mock_client = AsyncMock()
        mock_client.get_or_create_working_memory = AsyncMock(
            side_effect=[
                (False, SimpleNamespace(context="User prefers remediation-first answers")),
                (False, SimpleNamespace(context="Cluster failover history summary")),
            ]
        )
        mock_client.search_long_term_memory = AsyncMock(
            side_effect=[
                SimpleNamespace(
                    memories=[
                        SimpleNamespace(
                            text="User prefers remediation-first answers",
                            memory_type="semantic",
                        )
                    ]
                ),
                SimpleNamespace(
                    memories=[
                        SimpleNamespace(
                            text="Cluster had a failover during backups",
                            memory_type="episodic",
                        )
                    ]
                ),
            ]
        )
        mock_emitter = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("redis_sre_agent.core.agent_memory.MemoryAPIClient", return_value=mock_client):
            service = AgentMemoryService()
            result = await service.prepare_turn_context(
                query="What happened during backups?",
                session_id="session-1",
                user_id="user-1",
                cluster_id="cluster-1",
                emitter=SimpleNamespace(emit=mock_emitter),
            )

        assert result.status == "loaded"
        assert result.long_term_count == 2
        assert "User prefers remediation-first answers" in (result.system_prompt or "")
        assert "Cluster had a failover during backups" in (result.system_prompt or "")
        assert mock_client.search_long_term_memory.await_count == 2
        assert mock_client.get_or_create_working_memory.await_count == 2
        mock_emitter.assert_awaited()

    @pytest.mark.asyncio
    async def test_asset_only_fallback_without_user_id(self, memory_settings):
        mock_client = AsyncMock()
        mock_client.get_or_create_working_memory = AsyncMock(
            return_value=(False, SimpleNamespace(context="Operator prefers concise replies"))
        )
        mock_client.search_long_term_memory = AsyncMock(
            return_value=SimpleNamespace(
                memories=[
                    SimpleNamespace(
                        text="User prefers concise replies",
                        memory_type="semantic",
                    ),
                    SimpleNamespace(
                        text="Instance hit OOM last week",
                        memory_type="episodic",
                    )
                ]
            )
        )
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("redis_sre_agent.core.agent_memory.MemoryAPIClient", return_value=mock_client):
            service = AgentMemoryService()
            result = await service.prepare_turn_context(
                query="What happened before?",
                session_id="session-1",
                user_id=None,
                instance_id="instance-1",
            )

        assert result.status == "loaded"
        assert "Instance hit OOM last week" in (result.system_prompt or "")
        assert "Operator prefers concise replies" not in (result.system_prompt or "")
        assert "User prefers concise replies" not in (result.system_prompt or "")
        assert mock_client.get_or_create_working_memory.await_count == 1
        assert mock_client.search_long_term_memory.await_count == 1


class TestPersistTurn:
    @pytest.mark.asyncio
    async def test_persist_turn_is_fail_open(self, memory_settings):
        mock_client = AsyncMock()
        mock_client.get_or_create_working_memory = AsyncMock(side_effect=RuntimeError("boom"))
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_emitter = AsyncMock()

        with patch("redis_sre_agent.core.agent_memory.MemoryAPIClient", return_value=mock_client):
            service = AgentMemoryService()
            await service.persist_turn(
                session_id="session-1",
                user_id="user-1",
                user_message="hello",
                assistant_message="hi",
                emitter=SimpleNamespace(emit=mock_emitter),
            )

        mock_emitter.assert_awaited()

    @pytest.mark.asyncio
    async def test_persist_turn_writes_recent_messages(self, memory_settings):
        user_working_memory = SimpleNamespace(messages=[], memories=[], data={}, context=None)
        asset_working_memory = SimpleNamespace(messages=[], memories=[], data={}, context=None)
        mock_client = AsyncMock()
        mock_client.put_working_memory = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("redis_sre_agent.core.agent_memory.MemoryAPIClient", return_value=mock_client):
            service = AgentMemoryService()
            await service.persist_turn(
                session_id="session-1",
                user_id="user-1",
                user_message="hello",
                assistant_message="hi",
                user_working_memory=user_working_memory,
                asset_working_memory=asset_working_memory,
                instance_id="instance-1",
                thread_id="thread-1",
            )

        assert mock_client.put_working_memory.await_count == 2

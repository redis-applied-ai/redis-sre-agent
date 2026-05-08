"""Unit tests for Redis Agent Memory Server integration helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.agent_memory import (
    AgentMemoryService,
    TurnMemoryContext,
    prepare_agent_turn_memory,
)
from redis_sre_agent.core.turn_scope import TurnScope


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
    def test_user_strategy_prompt_excludes_asset_facts(self):
        service = AgentMemoryService()
        strategy = service._strategy()
        prompt = strategy.config["custom_prompt"]

        assert "explicit user preferences" in prompt
        assert "user-specific workflow habits" in prompt
        assert "asset configuration or environment facts" in prompt
        assert "request narration" in prompt
        assert "If content is mixed or ambiguous, do not persist it." in prompt
        assert "stable Redis environment facts" not in prompt

    def test_filter_asset_memories_keeps_operational_memories_with_common_adjectives(self):
        memories = [
            SimpleNamespace(text="Detailed OOM analysis revealed backup conflicts"),
            SimpleNamespace(text="Instance logs showed concise replication error trace"),
            SimpleNamespace(text="Operator prefers concise replies"),
        ]

        filtered = AgentMemoryService._filter_asset_memories(memories)

        assert [memory.text for memory in filtered] == [
            "Detailed OOM analysis revealed backup conflicts",
            "Instance logs showed concise replication error trace",
        ]

    @pytest.mark.asyncio
    async def test_returns_disabled_when_feature_off(self, monkeypatch):
        monkeypatch.setattr(
            "redis_sre_agent.core.agent_memory.settings.agent_memory_enabled", False
        )
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
        assert "Current user query:" not in (result.system_prompt or "")
        assert mock_client.search_long_term_memory.await_count == 2
        assert mock_client.get_or_create_working_memory.await_count == 2
        user_search_kwargs = mock_client.search_long_term_memory.await_args_list[0].kwargs
        asset_search_kwargs = mock_client.search_long_term_memory.await_args_list[1].kwargs
        assert "entities" not in user_search_kwargs or user_search_kwargs["entities"] is None
        assert asset_search_kwargs["entities"] is not None
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
                    ),
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
                user_message="Jamie prefers executive-summary-first updates when investigating service-12345 latency.",
                assistant_message="service-12345 had latency and replica lag during backups.",
                user_working_memory=user_working_memory,
                asset_working_memory=asset_working_memory,
                instance_id="instance-1",
                thread_id="thread-1",
            )

        assert mock_client.put_working_memory.await_count == 2
        user_memory = mock_client.put_working_memory.await_args_list[0].args[1]
        asset_memory = mock_client.put_working_memory.await_args_list[1].args[1]

        assert user_memory.namespace == "redis-sre-agent-user"
        assert asset_memory.namespace == "redis-sre-agent-asset"
        assert [message.content for message in user_memory.messages] == [
            "Jamie prefers executive-summary-first updates"
        ]
        assert [message.content for message in asset_memory.messages] == [
            "investigating service-12345 latency",
            "service-12345 had latency and replica lag during backups."
        ]

    @pytest.mark.asyncio
    async def test_persist_turn_excludes_asset_only_facts_from_user_scope(self, memory_settings):
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
                user_message="service-12345 had an OOM incident in production.",
                assistant_message="The Redis cluster had memory pressure during backups.",
                user_working_memory=user_working_memory,
                asset_working_memory=asset_working_memory,
                instance_id="instance-1",
                thread_id="thread-1",
            )

        assert mock_client.put_working_memory.await_count == 1
        asset_memory = mock_client.put_working_memory.await_args_list[0].args[1]
        assert asset_memory.namespace == "redis-sre-agent-asset"
        assert all("prefers" not in message.content for message in asset_memory.messages)

    @pytest.mark.asyncio
    async def test_persist_turn_excludes_preferences_from_asset_scope(self, memory_settings):
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
                user_message="Jamie prefers an interactive session with emphasis on metrics.",
                assistant_message="I can present an executive-summary-first report.",
                user_working_memory=user_working_memory,
                asset_working_memory=asset_working_memory,
                instance_id="instance-1",
                thread_id="thread-1",
            )

        assert mock_client.put_working_memory.await_count == 1
        user_memory = mock_client.put_working_memory.await_args_list[0].args[1]
        assert user_memory.namespace == "redis-sre-agent-user"
        assert all("redis" not in message.content.lower() for message in user_memory.messages)

    @pytest.mark.asyncio
    async def test_persist_turn_drops_ambiguous_mixed_sentence(self, memory_settings):
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
                user_message="Jamie investigated service-12345 latency on April 15.",
                assistant_message="We reviewed the situation.",
                user_working_memory=user_working_memory,
                asset_working_memory=asset_working_memory,
                instance_id="instance-1",
                thread_id="thread-1",
            )

        assert mock_client.put_working_memory.await_count == 1
        asset_memory = mock_client.put_working_memory.await_args_list[0].args[1]
        assert [message.content for message in asset_memory.messages] == [
            "Jamie investigated service-12345 latency on April 15."
        ]

    @pytest.mark.asyncio
    async def test_persist_turn_drops_inseparable_mixed_sentence(self, memory_settings):
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
                user_message="Jamie prefers service-12345 latency investigations.",
                assistant_message="okay",
                user_working_memory=user_working_memory,
                asset_working_memory=asset_working_memory,
                instance_id="instance-1",
                thread_id="thread-1",
            )

        assert mock_client.put_working_memory.await_count == 0

    @pytest.mark.asyncio
    async def test_persist_turn_deduplicates_existing_context_lines(self, memory_settings):
        existing_context = "\n".join(
            [
                "Target instance: instance-1",
                "Thread ID: thread-1",
                "User ID: user-1",
                "Prior durable note",
            ]
        )
        user_working_memory = SimpleNamespace(
            messages=[],
            memories=[],
            data={},
            context=existing_context,
        )
        mock_client = AsyncMock()
        mock_client.put_working_memory = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("redis_sre_agent.core.agent_memory.MemoryAPIClient", return_value=mock_client):
            service = AgentMemoryService()
            await service.persist_turn(
                session_id="session-1",
                user_id="user-1",
                user_message="Jamie prefers executive-summary-first updates.",
                assistant_message="I will keep updates concise and summary-first.",
                user_working_memory=user_working_memory,
                instance_id="instance-1",
                thread_id="thread-1",
            )

        _, updated_memory = mock_client.put_working_memory.await_args.args[:2]
        assert updated_memory.context == "\n".join(
            [
                "Target instance: instance-1",
                "Thread ID: thread-1",
                "User ID: user-1",
                "Prior durable note",
            ]
        )


class TestPrepareAgentTurnMemory:
    @pytest.mark.asyncio
    async def test_prepare_agent_turn_memory_forwards_cluster_context(self):
        memory_service = MagicMock()
        turn_context = TurnMemoryContext(
            system_prompt="Cluster summary",
            user_working_memory=None,
            asset_working_memory=None,
        )
        memory_service.prepare_turn_context = AsyncMock(return_value=turn_context)

        with patch(
            "redis_sre_agent.core.agent_memory.AgentMemoryService",
            return_value=memory_service,
        ):
            prepared = await prepare_agent_turn_memory(
                query="hello",
                session_id="session-1",
                user_id="user-1",
                context={"cluster_id": "cluster-1"},
                emitter=None,
            )

        memory_service.prepare_turn_context.assert_awaited_once_with(
            query="hello",
            session_id="session-1",
            user_id="user-1",
            instance_id=None,
            cluster_id="cluster-1",
            emitter=None,
        )
        assert prepared.cluster_id == "cluster-1"
        assert prepared.instance_id is None
        assert prepared.memory_context is turn_context

    @pytest.mark.asyncio
    async def test_prepare_agent_turn_memory_uses_single_bound_target_when_legacy_ids_missing(self):
        memory_service = MagicMock()
        turn_context = TurnMemoryContext(
            system_prompt="Instance summary",
            user_working_memory=None,
            asset_working_memory=None,
        )
        memory_service.prepare_turn_context = AsyncMock(return_value=turn_context)

        with patch(
            "redis_sre_agent.core.agent_memory.AgentMemoryService",
            return_value=memory_service,
        ):
            prepared = await prepare_agent_turn_memory(
                query="hello",
                session_id="session-1",
                user_id="user-1",
                context={
                    "target_bindings": [
                        {
                            "target_handle": "tgt_01",
                            "target_kind": "instance",
                            "resource_id": "instance-1",
                            "display_name": "instance-1",
                            "capabilities": ["redis"],
                        }
                    ]
                },
                emitter=None,
            )

        memory_service.prepare_turn_context.assert_awaited_once_with(
            query="hello",
            session_id="session-1",
            user_id="user-1",
            instance_id="instance-1",
            cluster_id=None,
            emitter=None,
        )
        assert prepared.instance_id == "instance-1"
        assert prepared.cluster_id is None

    @pytest.mark.asyncio
    async def test_prepare_agent_turn_memory_uses_single_bound_cluster_when_legacy_ids_missing(
        self,
    ):
        memory_service = MagicMock()
        turn_context = TurnMemoryContext(
            system_prompt="Cluster summary",
            user_working_memory=None,
            asset_working_memory=None,
        )
        memory_service.prepare_turn_context = AsyncMock(return_value=turn_context)

        with patch(
            "redis_sre_agent.core.agent_memory.AgentMemoryService",
            return_value=memory_service,
        ):
            prepared = await prepare_agent_turn_memory(
                query="hello",
                session_id="session-1",
                user_id="user-1",
                context={
                    "target_bindings": [
                        {
                            "target_handle": "tgt_01",
                            "target_kind": "cluster",
                            "resource_id": "cluster-1",
                            "display_name": "cluster-1",
                            "capabilities": ["admin"],
                        }
                    ]
                },
                emitter=None,
            )

        memory_service.prepare_turn_context.assert_awaited_once_with(
            query="hello",
            session_id="session-1",
            user_id="user-1",
            instance_id=None,
            cluster_id="cluster-1",
            emitter=None,
        )
        assert prepared.instance_id is None
        assert prepared.cluster_id == "cluster-1"

    @pytest.mark.asyncio
    async def test_prepare_agent_turn_memory_reuses_serialized_turn_scope(self):
        memory_service = MagicMock()
        turn_context = TurnMemoryContext(
            system_prompt="Instance summary",
            user_working_memory=None,
            asset_working_memory=None,
        )
        memory_service.prepare_turn_context = AsyncMock(return_value=turn_context)
        serialized_turn_scope = TurnScope.from_context(
            {
                "target_bindings": [
                    {
                        "target_handle": "tgt_01",
                        "target_kind": "instance",
                        "resource_id": "instance-1",
                        "display_name": "instance-1",
                        "capabilities": ["redis"],
                    }
                ]
            },
            session_id="session-1",
        ).model_dump(mode="json")

        with (
            patch(
                "redis_sre_agent.core.agent_memory.AgentMemoryService",
                return_value=memory_service,
            ),
            patch(
                "redis_sre_agent.core.agent_memory.TurnScope.from_context",
                side_effect=AssertionError("should not rebuild turn scope"),
            ),
        ):
            prepared = await prepare_agent_turn_memory(
                query="hello",
                session_id="session-1",
                user_id="user-1",
                context={"turn_scope": serialized_turn_scope},
                emitter=None,
            )

        memory_service.prepare_turn_context.assert_awaited_once_with(
            query="hello",
            session_id="session-1",
            user_id="user-1",
            instance_id="instance-1",
            cluster_id=None,
            emitter=None,
        )
        assert prepared.instance_id == "instance-1"
        assert prepared.cluster_id is None

    @pytest.mark.asyncio
    async def test_persist_response_fail_open(self):
        memory_service = MagicMock()
        memory_service.prepare_turn_context = AsyncMock(
            return_value=TurnMemoryContext(
                system_prompt=None,
                user_working_memory=None,
                asset_working_memory=None,
            )
        )
        memory_service.persist_turn = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(
            "redis_sre_agent.core.agent_memory.AgentMemoryService",
            return_value=memory_service,
        ):
            prepared = await prepare_agent_turn_memory(
                query="hello",
                session_id="session-1",
                user_id=None,
                context={"instance_id": "instance-1"},
                emitter=None,
            )
            await prepared.persist_response_fail_open("hi")

        memory_service.persist_turn.assert_awaited_once()

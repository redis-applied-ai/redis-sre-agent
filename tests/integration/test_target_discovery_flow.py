"""Redis-backed integration coverage for natural-language target discovery."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redisvl.index import AsyncSearchIndex
from redisvl.schema import IndexSchema

from redis_sre_agent.agent.router import AgentType
from redis_sre_agent.core.docket_tasks import process_agent_turn
from redis_sre_agent.core.instances import RedisInstance, save_instances
from redis_sre_agent.core.redis import (
    SRE_CLUSTERS_SCHEMA,
    SRE_INSTANCES_SCHEMA,
    SRE_TARGETS_SCHEMA,
)
from redis_sre_agent.core.tasks import TaskManager
from redis_sre_agent.core.threads import ThreadManager
from redis_sre_agent.tools.manager import ToolManager


def _build_index(redis_client, schema_dict: dict) -> AsyncSearchIndex:
    return AsyncSearchIndex(schema=IndexSchema.from_dict(schema_dict), redis_client=redis_client)


@pytest.fixture
def redis_backed_target_state(monkeypatch, async_redis_client):
    """Patch storage helpers so instance/target state uses the test Redis client."""

    async def _instances_index() -> AsyncSearchIndex:
        return _build_index(async_redis_client, SRE_INSTANCES_SCHEMA)

    async def _clusters_index() -> AsyncSearchIndex:
        return _build_index(async_redis_client, SRE_CLUSTERS_SCHEMA)

    async def _targets_index() -> AsyncSearchIndex:
        return _build_index(async_redis_client, SRE_TARGETS_SCHEMA)

    monkeypatch.setenv(
        "REDIS_SRE_MASTER_KEY",
        base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii"),
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.instances.get_redis_client", lambda: async_redis_client
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.clusters.get_redis_client", lambda: async_redis_client
    )
    monkeypatch.setattr("redis_sre_agent.core.targets.get_redis_client", lambda: async_redis_client)
    monkeypatch.setattr(
        "redis_sre_agent.core.docket_tasks.get_redis_client", lambda: async_redis_client
    )
    monkeypatch.setattr("redis_sre_agent.core.instances.get_instances_index", _instances_index)
    monkeypatch.setattr("redis_sre_agent.core.clusters.get_clusters_index", _clusters_index)
    monkeypatch.setattr("redis_sre_agent.core.targets.get_targets_index", _targets_index)


@pytest.mark.asyncio
async def test_target_discovery_tool_attaches_tools_and_reloads_from_thread(
    async_redis_client,
    redis_url,
    redis_backed_target_state,
):
    """A resolved target should attach live tools and survive a new ToolManager session."""

    instance = RedisInstance(
        id="redis-prod-checkout-cache",
        name="checkout-cache-prod",
        connection_url=redis_url,
        environment="production",
        usage="cache",
        description="Primary checkout cache",
        instance_type="oss_single",
        extension_data={"target_discovery": {"aliases": ["checkout cache", "checkout"]}},
    )
    await save_instances([instance])

    thread_manager = ThreadManager(redis_client=async_redis_client)
    thread_id = await thread_manager.create_thread(
        user_id="test-user",
        session_id="test-session",
        initial_context={},
    )

    async with ToolManager(thread_id=thread_id, user_id="test-user") as mgr:
        resolve_tool = next(t.name for t in mgr.get_tools() if "resolve_redis_targets" in t.name)
        resolution = await mgr.resolve_tool_call(
            resolve_tool,
            {
                "query": "prod checkout cache",
                "attach_tools": True,
            },
        )

        assert resolution["status"] == "resolved"
        assert resolution["attached_target_handles"]
        handle = resolution["attached_target_handles"][0]
        assert mgr.get_toolset_generation() >= 2

        redis_info_tools = [
            t.name
            for t in mgr.get_tools()
            if "redis_command_" in t.name
            and t.name.endswith("_info")
            and "cluster_info" not in t.name
            and "replication_info" not in t.name
            and "search_index_info" not in t.name
        ]
        assert len([t for t in mgr.get_tools() if "redis_command_" in t.name]) == 11
        assert len(redis_info_tools) == 1

        info_tool = redis_info_tools[0]
        info_result = await mgr.resolve_tool_call(info_tool, {"section": "server"})
        assert info_result["status"] == "success"
        assert info_result["section"] == "server"
        assert "redis_version" in info_result["data"]

    thread_state = await thread_manager.get_thread(thread_id)
    assert thread_state is not None
    assert thread_state.context["attached_target_handles"] == [handle]
    assert thread_state.context["active_target_handle"] == handle
    assert thread_state.context["instance_id"] == instance.id

    async with ToolManager(thread_id=thread_id, user_id="test-user") as mgr:
        reloaded_info_tools = [
            t.name
            for t in mgr.get_tools()
            if "redis_command_" in t.name
            and t.name.endswith("_info")
            and "cluster_info" not in t.name
            and "replication_info" not in t.name
            and "search_index_info" not in t.name
        ]
        assert len([t for t in mgr.get_tools() if "redis_command_" in t.name]) == 11
        assert len(reloaded_info_tools) == 1

        memory_result = await mgr.resolve_tool_call(reloaded_info_tools[0], {"section": "memory"})
        assert memory_result["status"] == "success"
        assert memory_result["section"] == "memory"
        assert "used_memory" in memory_result["data"]


@pytest.mark.asyncio
async def test_target_discovery_tool_can_attach_multiple_targets(
    async_redis_client,
    redis_url,
    redis_backed_target_state,
):
    """Multi-target resolution should bind several handles and load tool variants for each."""

    instances = [
        RedisInstance(
            id="redis-prod-checkout-cache",
            name="checkout-cache-prod",
            connection_url=redis_url,
            environment="production",
            usage="cache",
            description="Checkout traffic cache",
            instance_type="oss_single",
            extension_data={"target_discovery": {"aliases": ["checkout cache"]}},
        ),
        RedisInstance(
            id="redis-prod-session-cache",
            name="session-cache-prod",
            connection_url=redis_url,
            environment="production",
            usage="cache",
            description="Session state cache",
            instance_type="oss_single",
            extension_data={"target_discovery": {"aliases": ["session cache"]}},
        ),
    ]
    await save_instances(instances)

    thread_manager = ThreadManager(redis_client=async_redis_client)
    thread_id = await thread_manager.create_thread(
        user_id="test-user",
        session_id="test-session",
        initial_context={},
    )

    async with ToolManager(thread_id=thread_id, user_id="test-user") as mgr:
        resolve_tool = next(t.name for t in mgr.get_tools() if "resolve_redis_targets" in t.name)
        resolution = await mgr.resolve_tool_call(
            resolve_tool,
            {
                "query": "prod cache",
                "allow_multiple": True,
                "attach_tools": True,
                "max_results": 5,
            },
        )

        handles = resolution["attached_target_handles"]
        assert resolution["status"] == "resolved"
        assert len(handles) == 2

        loaded_tool_names = [tool.name for tool in mgr.get_tools()]
        redis_info_tools = [
            name
            for name in loaded_tool_names
            if "redis_command_" in name
            and name.endswith("_info")
            and "cluster_info" not in name
            and "replication_info" not in name
            and "search_index_info" not in name
        ]
        assert len([name for name in loaded_tool_names if "redis_command_" in name]) == 22
        assert len(redis_info_tools) == 2

        for info_tool in redis_info_tools:
            info_result = await mgr.resolve_tool_call(info_tool, {"section": "server"})
            assert info_result["status"] == "success"
            assert "redis_version" in info_result["data"]

    thread_state = await thread_manager.get_thread(thread_id)
    assert thread_state is not None
    assert thread_state.context["attached_target_handles"] == handles
    assert len(thread_state.context["target_bindings"]) == 2


@pytest.mark.asyncio
async def test_process_agent_turn_pre_resolves_target_scope_for_deep_triage(
    async_redis_client,
    redis_url,
    redis_backed_target_state,
):
    """Deep-triage entry should persist resolved scope before the heavy agent runs."""

    instance = RedisInstance(
        id="redis-prod-orders-cache",
        name="orders-cache-prod",
        connection_url=redis_url,
        environment="production",
        usage="cache",
        description="Orders cache",
        instance_type="oss_single",
        extension_data={"target_discovery": {"aliases": ["orders cache"]}},
    )
    await save_instances([instance])

    thread_manager = ThreadManager(redis_client=async_redis_client)
    task_manager = TaskManager(redis_client=async_redis_client)
    thread_id = await thread_manager.create_thread(
        user_id="test-user",
        session_id="test-session",
        initial_context={},
    )

    fake_agent_result = {
        "response": "triage complete",
        "search_results": [],
        "tool_envelopes": [],
        "metadata": {"iterations": 1},
    }

    with (
        patch(
            "redis_sre_agent.core.docket_tasks.route_to_appropriate_agent",
            new=AsyncMock(return_value=AgentType.REDIS_TRIAGE),
        ),
        patch(
            "redis_sre_agent.core.docket_tasks.run_agent_with_progress",
            new=AsyncMock(return_value=fake_agent_result),
        ),
        patch(
            "redis_sre_agent.core.docket_tasks.get_sre_agent",
            return_value=MagicMock(),
        ),
    ):
        result = await process_agent_turn(
            thread_id=thread_id,
            message="Do a deep triage on the prod orders cache",
        )

    thread_state = await thread_manager.get_thread(thread_id)
    assert thread_state is not None
    assert thread_state.context["instance_id"] == instance.id
    assert thread_state.context["attached_target_handles"]
    assert (
        thread_state.context["active_target_handle"]
        in thread_state.context["attached_target_handles"]
    )

    task_state = await task_manager.get_task_state(result["task_id"])
    assert task_state is not None
    assert any(update.update_type == "target_resolution" for update in task_state.updates)
    target_update = next(
        update for update in task_state.updates if update.update_type == "target_resolution"
    )
    assert target_update.metadata["match_count"] == 1

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
    SRE_TARGETS_INDEX,
    SRE_TARGETS_SCHEMA,
)
from redis_sre_agent.core.targets import TargetCatalogDoc
from redis_sre_agent.core.tasks import TaskManager
from redis_sre_agent.core.threads import ThreadManager
from redis_sre_agent.targets import get_target_handle_store
from redis_sre_agent.targets.contracts import (
    BindingRequest,
    BindingResult,
    DiscoveryCandidate,
    DiscoveryRequest,
    DiscoveryResponse,
    ProviderLoadRequest,
    PublicTargetBinding,
    PublicTargetMatch,
)
from redis_sre_agent.targets.registry import TargetIntegrationRegistry
from redis_sre_agent.tools.manager import ToolManager
from redis_sre_agent.tools.models import ToolCapability, ToolDefinition
from redis_sre_agent.tools.protocols import ToolProvider


def _build_index(redis_client, schema_dict: dict) -> AsyncSearchIndex:
    return AsyncSearchIndex(schema=IndexSchema.from_dict(schema_dict), redis_client=redis_client)


class FakePluggableToolProvider(ToolProvider):
    @property
    def provider_name(self) -> str:
        return "fake_pluggable"

    @property
    def requires_redis_instance(self) -> bool:
        return True

    async def probe(self) -> dict:
        return {
            "status": "success",
            "target_handle": getattr(self.redis_instance, "id", None),
            "name": getattr(self.redis_instance, "name", None),
        }

    def create_tool_schemas(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=self._make_tool_name("probe"),
                description="Probe a mocked pluggable target binding.",
                capability=ToolCapability.UTILITIES,
                parameters={"type": "object", "properties": {}},
            )
        ]


class MockIntegrationDiscoveryBackend:
    backend_name = "mock_backend"

    async def resolve(self, request: DiscoveryRequest) -> DiscoveryResponse:
        public_match = PublicTargetMatch(
            target_kind="instance",
            display_name="mock-cache-prod",
            environment="test",
            target_type="oss_single",
            capabilities=["redis"],
            confidence=0.99,
            match_reasons=["mocked backend"],
            public_metadata={"environment": "test"},
            resource_id="mock-private-id",
        )
        candidate = DiscoveryCandidate(
            public_match=public_match,
            binding_strategy="mock_strategy",
            binding_subject="mock-private-id",
            private_binding_ref={"source": "mock"},
            discovery_backend=self.backend_name,
            score=9.5,
            confidence=0.99,
        )
        return DiscoveryResponse(
            status="resolved",
            matches=[public_match],
            selected_matches=[candidate],
        )


class MockIntegrationBindingStrategy:
    strategy_name = "mock_strategy"

    async def bind(self, request: BindingRequest) -> BindingResult:
        from redis_sre_agent.core.instances import RedisInstance

        handle = request.handle_record.target_handle
        instance = RedisInstance(
            id=handle,
            name="mock-cache-prod",
            connection_url="redis://mock.invalid:6379",
            environment="test",
            usage="cache",
            description="Synthetic mocked target",
            instance_type="oss_single",
        )
        return BindingResult(
            public_summary=PublicTargetBinding(
                target_handle=handle,
                target_kind="instance",
                display_name="mock-cache-prod",
                capabilities=["redis"],
                public_metadata={"environment": "test"},
            ),
            provider_loads=[
                ProviderLoadRequest(
                    provider_path=f"{__name__}.FakePluggableToolProvider",
                    provider_key=f"target:{handle}:fake_pluggable",
                    target_handle=handle,
                    provider_context={"redis_instance_override": instance},
                )
            ],
        )


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
        "redis_sre_agent.targets.handle_store.get_redis_client", lambda: async_redis_client
    )
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
    assert thread_state.context.get("instance_id", "") in {"", None}
    handle_record = await get_target_handle_store().get_record(handle)
    assert handle_record is not None
    assert handle_record.binding_subject == instance.id

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
async def test_target_inventory_tool_lists_known_targets_before_resolution(
    async_redis_client,
    redis_url,
    redis_backed_target_state,
):
    """Inventory listing should work at zero scope before resolving and attaching one target."""

    instances = [
        RedisInstance(
            id="redis-prod-checkout-cache",
            name="checkout-cache-prod",
            connection_url=redis_url,
            environment="production",
            usage="cache",
            description="Primary checkout cache",
            instance_type="oss_single",
            extension_data={"target_discovery": {"aliases": ["checkout cache"]}},
        ),
        RedisInstance(
            id="redis-prod-session-cache",
            name="session-cache-prod",
            connection_url=redis_url,
            environment="production",
            usage="cache",
            description="Primary session cache",
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
        list_tool = next(t.name for t in mgr.get_tools() if "list_known_redis_targets" in t.name)
        inventory = await mgr.resolve_tool_call(list_tool, {"include_aliases": True})

        assert inventory["status"] == "ok"
        assert inventory["total_known_targets"] == 2
        assert {target["display_name"] for target in inventory["targets"]} == {
            "checkout-cache-prod",
            "session-cache-prod",
        }

        resolve_tool = next(t.name for t in mgr.get_tools() if "resolve_redis_targets" in t.name)
        resolution = await mgr.resolve_tool_call(
            resolve_tool,
            {
                "query": "checkout cache",
                "attach_tools": True,
            },
        )

        assert resolution["status"] == "resolved"
        assert len(resolution["attached_target_handles"]) == 1

        info_tool = next(
            t.name
            for t in mgr.get_tools()
            if "redis_command_" in t.name
            and t.name.endswith("_info")
            and "cluster_info" not in t.name
            and "replication_info" not in t.name
            and "search_index_info" not in t.name
        )
        info_result = await mgr.resolve_tool_call(info_tool, {"section": "server"})
        assert info_result["status"] == "success"
        assert "redis_version" in info_result["data"]


@pytest.mark.asyncio
async def test_target_discovery_tool_repairs_stale_catalog_from_authoritative_instances(
    async_redis_client,
    redis_url,
    redis_backed_target_state,
):
    """Discovery should self-heal when the target index drifts from stored instances."""

    instance = RedisInstance(
        id="redis-development-demo2",
        name="demo2",
        connection_url=redis_url,
        environment="development",
        usage="cache",
        description="Demo Redis instance",
        instance_type="oss_single",
    )
    await save_instances([instance])

    cursor = 0
    while True:
        cursor, batch = await async_redis_client.scan(cursor=cursor, match=f"{SRE_TARGETS_INDEX}:*")
        for key in batch or []:
            await async_redis_client.delete(key)
        if cursor == 0:
            break

    stale_doc = TargetCatalogDoc(
        target_id="instance:redis-1",
        target_kind="instance",
        resource_id="redis-1",
        display_name="New Instance",
        name="New Instance",
        environment="development",
        status="unknown",
        target_type="oss_single",
        usage="cache",
        search_text="new instance development cache",
        capabilities=["redis", "diagnostics", "metrics", "logs"],
    )
    await async_redis_client.hset(
        f"{SRE_TARGETS_INDEX}:{stale_doc.target_id}",
        mapping={
            "target_id": stale_doc.target_id,
            "target_kind": stale_doc.target_kind,
            "resource_id": stale_doc.resource_id,
            "display_name": stale_doc.display_name,
            "name": stale_doc.name,
            "environment": stale_doc.environment or "",
            "status": stale_doc.status or "",
            "target_type": stale_doc.target_type or "",
            "usage": stale_doc.usage or "",
            "cluster_id": "",
            "repo_slug": "",
            "monitoring_identifier": "",
            "logging_identifier": "",
            "redis_cloud_subscription_id": "",
            "redis_cloud_database_id": "",
            "redis_cloud_database_name": "",
            "search_aliases": "",
            "capabilities": ",".join(stale_doc.capabilities),
            "updated_at": 1,
            "created_at": 1,
            "search_text": stale_doc.search_text,
            "user_id": "",
            "data": stale_doc.model_dump_json(),
        },
    )

    thread_manager = ThreadManager(redis_client=async_redis_client)
    thread_id = await thread_manager.create_thread(
        user_id="test-user",
        session_id="test-session",
        initial_context={},
    )

    async with ToolManager(thread_id=thread_id, user_id="test-user") as mgr:
        list_tool = next(t.name for t in mgr.get_tools() if "list_known_redis_targets" in t.name)
        inventory = await mgr.resolve_tool_call(list_tool, {})
        assert inventory["status"] == "ok"
        assert inventory["total_known_targets"] == 1
        assert inventory["targets"][0]["display_name"] == "demo2"

        resolve_tool = next(t.name for t in mgr.get_tools() if "resolve_redis_targets" in t.name)
        resolution = await mgr.resolve_tool_call(
            resolve_tool,
            {
                "query": "demo2",
                "attach_tools": False,
            },
        )

        assert resolution["status"] == "resolved"
        assert resolution["matches"][0]["display_name"] == "demo2"
        assert resolution["matches"][0]["environment"] == "development"


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
    assert thread_state.context["attached_target_handles"]
    assert (
        thread_state.context["active_target_handle"]
        in thread_state.context["attached_target_handles"]
    )
    active_handle = thread_state.context["active_target_handle"]
    assert thread_state.context.get("instance_id", "") in {"", None}
    handle_record = await get_target_handle_store().get_record(active_handle)
    assert handle_record is not None
    assert handle_record.binding_subject == instance.id

    task_state = await task_manager.get_task_state(result["task_id"])
    assert task_state is not None


@pytest.mark.asyncio
async def test_target_discovery_and_tool_manager_support_alternate_pluggable_path(
    async_redis_client,
    redis_backed_target_state,
):
    registry = TargetIntegrationRegistry(
        default_discovery_backend="mock_backend",
        default_binding_strategy="mock_strategy",
    )
    registry.register_discovery_backend(MockIntegrationDiscoveryBackend())
    registry.register_binding_strategy(MockIntegrationBindingStrategy())

    thread_manager = ThreadManager(redis_client=async_redis_client)
    thread_id = await thread_manager.create_thread(
        user_id="test-user",
        session_id="test-session",
        initial_context={},
    )

    with (
        patch(
            "redis_sre_agent.targets.services.get_target_integration_registry",
            return_value=registry,
        ),
        patch(
            "redis_sre_agent.tools.manager.get_target_integration_registry", return_value=registry
        ),
    ):
        async with ToolManager(thread_id=thread_id, user_id="test-user") as mgr:
            resolve_tool = next(
                t.name for t in mgr.get_tools() if "resolve_redis_targets" in t.name
            )
            resolution = await mgr.resolve_tool_call(
                resolve_tool,
                {
                    "query": "mock cache",
                    "attach_tools": True,
                },
            )

            assert resolution["status"] == "resolved"
            assert resolution["attached_target_handles"]
            handle = resolution["attached_target_handles"][0]

            fake_probe_tools = [
                t.name
                for t in mgr.get_tools()
                if "fake_pluggable_" in t.name and t.name.endswith("_probe")
            ]
            assert len(fake_probe_tools) == 1

            probe_result = await mgr.resolve_tool_call(fake_probe_tools[0], {})
            assert probe_result["status"] == "success"
            assert probe_result["target_handle"] == handle

        thread_state = await thread_manager.get_thread(thread_id)
        assert thread_state is not None
        handle_record = await get_target_handle_store().get_record(handle)
        assert handle_record is not None
        assert handle_record.binding_strategy == "mock_strategy"
        assert handle_record.binding_subject == "mock-private-id"

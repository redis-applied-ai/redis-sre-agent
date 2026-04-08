"""Unit tests for the natural-language target discovery provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.targets import BoundTargetScope, ResolvedTargetMatch, TargetBinding
from redis_sre_agent.tools.target_discovery.provider import TargetDiscoveryToolProvider


@pytest.mark.asyncio
async def test_resolve_redis_targets_uses_shared_binding_contract():
    provider = TargetDiscoveryToolProvider()
    manager = MagicMock()
    manager.thread_id = "thread-1"
    manager.task_id = "task-1"
    manager.user_id = "user-1"
    manager.get_toolset_generation.return_value = 2
    provider._manager = manager

    resolution = MagicMock()
    resolution.selected_matches = [
        ResolvedTargetMatch(
            target_kind="instance",
            resource_id="redis-prod-checkout-cache",
            display_name="checkout-cache-prod",
            environment="production",
            target_type="oss_single",
            capabilities=["redis", "diagnostics"],
            confidence=0.94,
            match_reasons=["matched environment=production"],
        )
    ]
    resolution.model_dump.return_value = {
        "status": "resolved",
        "clarification_required": False,
        "matches": [],
        "attached_target_handles": [],
        "toolset_generation": 0,
    }
    bound_scope = BoundTargetScope(
        bindings=[
            TargetBinding(
                target_handle="tgt_01",
                target_kind="instance",
                resource_id="redis-prod-checkout-cache",
                display_name="checkout-cache-prod",
                capabilities=["redis", "diagnostics"],
                thread_id="thread-1",
                task_id="task-1",
            )
        ],
        toolset_generation=7,
        context_updates={
            "attached_target_handles": ["tgt_01"],
            "target_toolset_generation": 7,
            "target_bindings": [
                {
                    "target_handle": "tgt_01",
                    "target_kind": "instance",
                    "resource_id": "redis-prod-checkout-cache",
                    "display_name": "checkout-cache-prod",
                    "capabilities": ["redis", "diagnostics"],
                    "thread_id": "thread-1",
                    "task_id": "task-1",
                }
            ],
            "instance_id": "redis-prod-checkout-cache",
            "cluster_id": "",
        },
    )

    with (
        patch(
            "redis_sre_agent.tools.target_discovery.provider.resolve_target_query",
            new=AsyncMock(return_value=resolution),
        ) as mock_resolve,
        patch(
            "redis_sre_agent.tools.target_discovery.provider.bind_target_matches",
            new=AsyncMock(return_value=bound_scope),
        ) as mock_bind,
    ):
        payload = await provider.resolve_redis_targets(
            query="prod checkout cache",
            allow_multiple=False,
            max_results=5,
            attach_tools=True,
            preferred_capabilities=["diagnostics"],
        )

    mock_resolve.assert_awaited_once_with(
        query="prod checkout cache",
        user_id="user-1",
        allow_multiple=False,
        max_results=5,
        preferred_capabilities=["diagnostics"],
    )
    mock_bind.assert_awaited_once_with(
        matches=resolution.selected_matches,
        thread_id="thread-1",
        task_id="task-1",
        replace_existing=True,
        manager=manager,
    )
    assert payload["attached_target_handles"] == ["tgt_01"]
    assert payload["toolset_generation"] == 7


@pytest.mark.asyncio
async def test_resolve_redis_targets_without_attachment_uses_existing_toolset_generation():
    provider = TargetDiscoveryToolProvider()
    manager = MagicMock()
    manager.thread_id = "thread-1"
    manager.task_id = "task-1"
    manager.user_id = "user-1"
    manager.get_toolset_generation.return_value = 4
    provider._manager = manager

    resolution = MagicMock()
    resolution.selected_matches = []
    resolution.model_dump.return_value = {
        "status": "clarification_required",
        "clarification_required": True,
        "matches": [],
        "attached_target_handles": [],
        "toolset_generation": 0,
    }

    with (
        patch(
            "redis_sre_agent.tools.target_discovery.provider.resolve_target_query",
            new=AsyncMock(return_value=resolution),
        ) as mock_resolve,
        patch(
            "redis_sre_agent.tools.target_discovery.provider.bind_target_matches",
            new=AsyncMock(),
        ) as mock_bind,
    ):
        payload = await provider.resolve_redis_targets(
            query="checkout",
            attach_tools=False,
        )

    mock_resolve.assert_awaited_once()
    mock_bind.assert_not_awaited()
    assert payload["attached_target_handles"] == []
    assert payload["toolset_generation"] == 4

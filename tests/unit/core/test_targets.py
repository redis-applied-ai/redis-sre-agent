"""Tests for unified target discovery and safe thread binding state."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core import targets as target_module
from redis_sre_agent.core.clusters import RedisCluster
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.core.targets import (
    MaterializedTargetScope,
    ResolvedTargetMatch,
    TargetCatalogDoc,
    attach_target_matches,
    bind_target_matches,
    build_attached_target_prompt_loader,
    build_attached_target_scope_prompt,
    build_bound_target_scope_context,
    build_ephemeral_target_bindings,
    build_target_doc_from_cluster,
    build_target_doc_from_instance,
    get_attached_target_handles_from_context,
    get_target_bindings_from_context,
    materialize_bound_target_scope,
    resolve_target_query,
    sync_target_catalog,
)
from redis_sre_agent.core.threads import Thread, ThreadMetadata


def test_build_target_doc_from_instance_excludes_secrets_and_includes_aliases():
    instance = RedisInstance(
        id="redis-prod-checkout-cache",
        name="checkout-cache-prod",
        connection_url="redis://user:secret@cache.internal:6379/0",
        environment="production",
        usage="cache",
        description="Primary checkout cache",
        notes="Handles checkout sessions",
        repo_url="https://github.com/acme/checkout-service",
        monitoring_identifier="checkout-cache-prod",
        logging_identifier="checkout-cache",
        instance_type="oss_single",
        extension_data={"target_discovery": {"aliases": ["checkout", "cart cache"]}},
    )

    doc = build_target_doc_from_instance(instance)

    assert "secret" not in doc.search_text
    assert "cache.internal" not in doc.search_text
    assert "checkout" in doc.search_aliases
    assert "cart cache" in doc.search_aliases
    assert doc.repo_slug == "acme/checkout-service"


def test_build_target_doc_from_instance_normalizes_environment_aliases():
    instance = RedisInstance(
        id="redis-prod-checkout-cache",
        name="checkout-cache-prod",
        connection_url="redis://cache.internal:6379/0",
        environment="prod",
        usage="cache",
        description="Primary checkout cache",
        instance_type="oss_single",
    )

    doc = build_target_doc_from_instance(instance)

    assert doc.environment == "production"


def test_build_target_doc_from_cluster_includes_base_capabilities():
    cluster = RedisCluster(
        id="cluster-prod-checkout",
        name="checkout-cluster-prod",
        cluster_type="oss_cluster",
        environment="production",
        description="Checkout Redis cluster",
    )

    doc = build_target_doc_from_cluster(cluster)

    assert "redis" in doc.capabilities
    assert "diagnostics" in doc.capabilities
    assert "metrics" in doc.capabilities
    assert "logs" in doc.capabilities


@pytest.mark.asyncio
async def test_resolve_target_query_ranks_matching_environment_and_detects_ambiguity():
    prod = TargetCatalogDoc(
        target_id="instance:redis-prod-checkout-cache",
        target_kind="instance",
        resource_id="redis-prod-checkout-cache",
        display_name="checkout-cache-prod",
        name="checkout-cache-prod",
        environment="production",
        usage="cache",
        target_type="oss_single",
        capabilities=["redis", "diagnostics"],
        search_text="checkout cache prod production cache",
        search_aliases=["checkout"],
    )
    stage = TargetCatalogDoc(
        target_id="instance:redis-stage-checkout-cache",
        target_kind="instance",
        resource_id="redis-stage-checkout-cache",
        display_name="checkout-cache-stage",
        name="checkout-cache-stage",
        environment="staging",
        usage="cache",
        target_type="oss_single",
        capabilities=["redis", "diagnostics"],
        search_text="checkout cache stage staging cache",
        search_aliases=["checkout"],
    )

    with patch(
        "redis_sre_agent.core.targets.get_target_catalog",
        new=AsyncMock(return_value=[prod, stage]),
    ):
        resolved = await resolve_target_query(query="prod checkout cache", allow_multiple=False)
        ambiguous = await resolve_target_query(query="checkout cache", allow_multiple=False)

    assert resolved.status == "resolved"
    assert not resolved.clarification_required
    assert len(resolved.selected_matches) == 1
    assert resolved.selected_matches[0].resource_id == "redis-prod-checkout-cache"

    assert ambiguous.status == "clarification_required"
    assert ambiguous.clarification_required is True
    assert len(ambiguous.matches) == 2
    assert len(ambiguous.selected_matches) == 2
    assert [match.resource_id for match in ambiguous.selected_matches] == [
        "redis-prod-checkout-cache",
        "redis-stage-checkout-cache",
    ]


@pytest.mark.asyncio
async def test_resolve_target_query_resolves_single_included_candidate_below_three_points():
    low_score_match = TargetCatalogDoc(
        target_id="instance:redis-prod-checkout-cache",
        target_kind="instance",
        resource_id="redis-prod-checkout-cache",
        display_name="checkout-prod",
        name="checkout-prod",
        environment="production",
        usage="cache",
        target_type="oss_single",
        capabilities=["redis"],
        search_text="",
        search_aliases=[],
    )

    with patch(
        "redis_sre_agent.core.targets.get_target_catalog",
        new=AsyncMock(return_value=[low_score_match]),
    ):
        resolved = await resolve_target_query(query="cache", allow_multiple=False)

    assert resolved.status == "resolved"
    assert resolved.clarification_required is False
    assert len(resolved.selected_matches) == 1
    assert resolved.selected_matches[0].resource_id == "redis-prod-checkout-cache"


@pytest.mark.asyncio
async def test_resolve_target_query_parses_hints_once_and_avoids_alias_substring_matches():
    ambiguous_alias = TargetCatalogDoc(
        target_id="instance:alias-only",
        target_kind="instance",
        resource_id="alias-only",
        display_name="alias-only",
        name="alias-only",
        environment=None,
        usage=None,
        target_type=None,
        capabilities=["redis"],
        search_text="unrelated target",
        search_aliases=["a"],
    )
    real_match = TargetCatalogDoc(
        target_id="instance:checkout-cache",
        target_kind="instance",
        resource_id="checkout-cache",
        display_name="checkout-cache-prod",
        name="checkout-cache-prod",
        environment="production",
        usage="cache",
        target_type="oss_single",
        capabilities=["redis"],
        search_text="checkout cache prod production cache",
        search_aliases=["checkout"],
    )

    with (
        patch(
            "redis_sre_agent.core.targets.get_target_catalog",
            new=AsyncMock(return_value=[ambiguous_alias, real_match]),
        ),
        patch(
            "redis_sre_agent.core.targets._parse_query_hints",
            wraps=target_module._parse_query_hints,
        ) as parse_hints,
    ):
        resolved = await resolve_target_query(query="checkout cache", allow_multiple=False)

    assert parse_hints.call_count == 1
    assert resolved.status == "resolved"
    assert len(resolved.selected_matches) == 1
    assert resolved.selected_matches[0].resource_id == "checkout-cache"
    assert all(match.resource_id != "alias-only" for match in resolved.matches)


@pytest.mark.asyncio
async def test_resolve_target_query_keeps_token_overlap_from_all_aliases():
    target = TargetCatalogDoc(
        target_id="instance:prod-cache",
        target_kind="instance",
        resource_id="prod-cache",
        display_name="prod-cache",
        name="prod-cache",
        environment="production",
        usage=None,
        target_type="oss_single",
        capabilities=["redis"],
        search_text="primary production target",
        search_aliases=["alpha", "checkout cache"],
    )

    with patch(
        "redis_sre_agent.core.targets.get_target_catalog",
        new=AsyncMock(return_value=[target]),
    ):
        resolved = await resolve_target_query(query="checkout cache", allow_multiple=False)

    assert resolved.status == "resolved"
    assert resolved.selected_matches[0].resource_id == "prod-cache"
    assert any(
        reason == "matched tokens=checkout" for reason in resolved.selected_matches[0].match_reasons
    )


@pytest.mark.asyncio
async def test_resolve_target_query_excludes_hint_tokens_from_token_overlap():
    target = TargetCatalogDoc(
        target_id="instance:enterprise-cache",
        target_kind="instance",
        resource_id="enterprise-cache",
        display_name="enterprise-cache",
        name="enterprise-cache",
        environment="production",
        usage="cache",
        target_type="redis_enterprise",
        capabilities=["redis"],
        search_text="production cache enterprise instance",
        search_aliases=[],
    )

    with patch(
        "redis_sre_agent.core.targets.get_target_catalog",
        new=AsyncMock(return_value=[target]),
    ):
        resolved = await resolve_target_query(
            query="prod cache instance enterprise",
            allow_multiple=False,
        )

    assert resolved.status == "resolved"
    assert resolved.selected_matches[0].resource_id == "enterprise-cache"
    assert all(
        not reason.startswith("matched tokens=")
        for reason in resolved.selected_matches[0].match_reasons
    )


@pytest.mark.asyncio
async def test_attach_target_matches_persists_safe_thread_context():
    match = ResolvedTargetMatch(
        target_kind="instance",
        resource_id="redis-prod-checkout-cache",
        display_name="checkout-cache-prod",
        environment="production",
        target_type="oss_single",
        capabilities=["redis", "diagnostics"],
        confidence=0.94,
        match_reasons=["matched environment=production"],
    )
    mock_thread_manager = AsyncMock()
    mock_thread_manager.get_thread = AsyncMock(
        return_value=Thread(
            thread_id="thread-1", messages=[], context={}, metadata=ThreadMetadata()
        )
    )
    mock_thread_manager.update_thread_context = AsyncMock(return_value=True)

    with patch(
        "redis_sre_agent.core.targets.ThreadManager",
        return_value=mock_thread_manager,
    ):
        bindings, generation = await attach_target_matches(
            thread_id="thread-1",
            matches=[match],
            task_id="task-1",
            replace_existing=False,
        )

    assert len(bindings) == 1
    assert bindings[0].target_handle.startswith("tgt_")
    assert generation == 2

    update_payload = mock_thread_manager.update_thread_context.await_args.args[1]
    assert update_payload["instance_id"] == ""
    assert update_payload["cluster_id"] == ""
    assert update_payload["attached_target_handles"] == [bindings[0].target_handle]
    assert "connection_url" not in str(update_payload)
    assert "secret" not in str(update_payload)


@pytest.mark.asyncio
async def test_attach_target_matches_append_mode_clears_singular_scope_ids_for_multi_target():
    matches = [
        ResolvedTargetMatch(
            target_kind="cluster",
            resource_id="cluster-a",
            display_name="cluster-a",
            environment="production",
            target_type="redis_enterprise",
            capabilities=["admin"],
            confidence=0.91,
            match_reasons=["matched name=cluster-a"],
        ),
        ResolvedTargetMatch(
            target_kind="cluster",
            resource_id="cluster-b",
            display_name="cluster-b",
            environment="production",
            target_type="redis_enterprise",
            capabilities=["admin"],
            confidence=0.9,
            match_reasons=["matched name=cluster-b"],
        ),
    ]
    mock_thread_manager = AsyncMock()
    mock_thread_manager.get_thread = AsyncMock(
        return_value=Thread(
            thread_id="thread-1",
            messages=[],
            context={"instance_id": "redis-prod-checkout-cache", "cluster_id": ""},
            metadata=ThreadMetadata(),
        )
    )
    mock_thread_manager.update_thread_context = AsyncMock(return_value=True)

    with patch(
        "redis_sre_agent.core.targets.ThreadManager",
        return_value=mock_thread_manager,
    ):
        bindings, generation = await attach_target_matches(
            thread_id="thread-1",
            matches=matches,
            task_id="task-1",
            replace_existing=False,
        )

    assert len(bindings) == 2
    assert generation == 2

    update_payload = mock_thread_manager.update_thread_context.await_args.args[1]
    assert update_payload["instance_id"] == ""
    assert update_payload["cluster_id"] == ""
    assert len(update_payload["attached_target_handles"]) == 2


def test_build_bound_target_scope_context_clears_legacy_scope_ids_for_single_target():
    binding = target_module.TargetBinding(
        target_handle="tgt_01",
        target_kind="instance",
        resource_id="redis-prod-checkout-cache",
        display_name="checkout-cache-prod",
        capabilities=["redis", "diagnostics"],
    )

    context_updates = build_bound_target_scope_context([binding], generation=3)

    assert context_updates["attached_target_handles"] == ["tgt_01"]
    assert context_updates["active_target_handle"] == "tgt_01"
    assert context_updates["instance_id"] == ""
    assert context_updates["cluster_id"] == ""


def test_build_bound_target_scope_context_clears_singular_scope_ids_for_multi_target():
    bindings = [
        target_module.TargetBinding(
            target_handle="tgt_01",
            target_kind="instance",
            resource_id="redis-prod-checkout-cache",
            display_name="checkout-cache-prod",
            capabilities=["redis", "diagnostics"],
        ),
        target_module.TargetBinding(
            target_handle="tgt_02",
            target_kind="cluster",
            resource_id="cluster-prod-checkout",
            display_name="checkout-cluster-prod",
            capabilities=["admin"],
        ),
    ]

    context_updates = build_bound_target_scope_context(bindings, generation=4)

    assert context_updates["attached_target_handles"] == ["tgt_01", "tgt_02"]
    assert context_updates["instance_id"] == ""
    assert context_updates["cluster_id"] == ""


@pytest.mark.asyncio
async def test_bind_target_matches_without_thread_uses_ephemeral_bindings_and_manager():
    match = ResolvedTargetMatch(
        target_kind="instance",
        resource_id="redis-prod-checkout-cache",
        display_name="checkout-cache-prod",
        environment="production",
        target_type="oss_single",
        capabilities=["redis", "diagnostics"],
        confidence=0.94,
        match_reasons=["matched environment=production"],
    )
    manager = MagicMock()
    manager.attach_bound_targets = AsyncMock()
    manager.get_toolset_generation.return_value = 7

    scope = await bind_target_matches(
        matches=[match],
        thread_id=None,
        task_id="task-1",
        replace_existing=False,
        manager=manager,
    )

    manager.attach_bound_targets.assert_awaited_once()
    assert len(scope.bindings) == 1
    assert scope.bindings[0].thread_id is None
    assert scope.toolset_generation == 7
    assert scope.context_updates["attached_target_handles"] == [scope.bindings[0].target_handle]
    assert scope.context_updates["instance_id"] == ""


@pytest.mark.asyncio
async def test_bind_target_matches_with_thread_returns_materialized_attached_scope():
    existing_binding = target_module.TargetBinding(
        target_handle="tgt_existing",
        target_kind="instance",
        resource_id="redis-prod-checkout-cache",
        display_name="checkout-cache-prod",
        capabilities=["redis", "diagnostics"],
        thread_id="thread-1",
        task_id="task-existing",
    )
    new_match = ResolvedTargetMatch(
        target_kind="cluster",
        resource_id="cluster-prod-checkout",
        display_name="checkout-cluster-prod",
        environment="production",
        target_type="redis_enterprise",
        capabilities=["admin"],
        confidence=0.9,
        match_reasons=["matched name=checkout-cluster-prod"],
    )
    updated_context = build_bound_target_scope_context(
        [
            existing_binding,
            target_module.TargetBinding(
                target_handle="tgt_new",
                target_kind="cluster",
                resource_id="cluster-prod-checkout",
                display_name="checkout-cluster-prod",
                capabilities=["admin"],
                thread_id="thread-1",
                task_id="task-1",
            ),
        ],
        generation=3,
        active_handle="tgt_new",
    )
    mock_thread_manager = AsyncMock()
    mock_thread_manager.get_thread = AsyncMock(
        side_effect=[
            Thread(
                thread_id="thread-1",
                messages=[],
                context=build_bound_target_scope_context([existing_binding], generation=2),
                metadata=ThreadMetadata(),
            ),
            Thread(
                thread_id="thread-1",
                messages=[],
                context=updated_context,
                metadata=ThreadMetadata(),
            ),
        ]
    )
    mock_thread_manager.update_thread_context = AsyncMock(return_value=True)

    with (
        patch("redis_sre_agent.core.targets.ThreadManager", return_value=mock_thread_manager),
        patch("redis_sre_agent.core.targets.ULID", return_value="new"),
    ):
        scope = await bind_target_matches(
            matches=[new_match],
            thread_id="thread-1",
            task_id="task-1",
            replace_existing=False,
        )

    assert [binding.target_handle for binding in scope.bindings] == ["tgt_existing", "tgt_new"]
    assert scope.toolset_generation == 3
    assert scope.context_updates["attached_target_handles"] == ["tgt_existing", "tgt_new"]
    assert scope.context_updates["active_target_handle"] == "tgt_new"
    assert scope.context_updates["instance_id"] == ""
    assert scope.context_updates["cluster_id"] == ""


@pytest.mark.asyncio
async def test_materialize_bound_target_scope_reloads_full_thread_state_after_attach():
    selected_binding = target_module.TargetBinding(
        target_handle="tgt_new",
        target_kind="instance",
        resource_id="redis-prod-checkout-cache",
        display_name="checkout-cache-prod",
        capabilities=["redis", "diagnostics"],
        thread_id="thread-1",
        task_id="task-1",
    )
    existing_binding = target_module.TargetBinding(
        target_handle="tgt_existing",
        target_kind="cluster",
        resource_id="cluster-prod-checkout",
        display_name="checkout-cluster-prod",
        capabilities=["admin"],
        thread_id="thread-1",
        task_id="task-1",
    )
    matches = [
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

    with (
        patch(
            "redis_sre_agent.core.targets.attach_target_matches",
            new=AsyncMock(return_value=([selected_binding], 3)),
        ),
        patch(
            "redis_sre_agent.core.targets.get_thread_target_state",
            new=AsyncMock(
                return_value=target_module.ThreadTargetState(
                    attached_target_handles=["tgt_existing", "tgt_new"],
                    active_target_handle="tgt_new",
                    target_toolset_generation=3,
                    target_bindings=[existing_binding, selected_binding],
                )
            ),
        ),
    ):
        scope = await materialize_bound_target_scope(
            matches=matches,
            thread_id="thread-1",
            task_id="task-1",
            replace_existing=False,
        )

    assert [binding.target_handle for binding in scope.selected_bindings] == ["tgt_new"]
    assert [binding.target_handle for binding in scope.attached_bindings] == [
        "tgt_existing",
        "tgt_new",
    ]
    assert scope.target_toolset_generation == 3
    assert scope.context_updates["attached_target_handles"] == ["tgt_existing", "tgt_new"]
    assert scope.context_updates["active_target_handle"] == "tgt_new"
    assert scope.context_updates["instance_id"] == ""
    assert scope.context_updates["cluster_id"] == ""


@pytest.mark.asyncio
async def test_bind_target_matches_attaches_full_materialized_scope_to_manager():
    selected_binding = target_module.TargetBinding(
        target_handle="tgt_new",
        target_kind="instance",
        resource_id="redis-prod-checkout-cache",
        display_name="checkout-cache-prod",
        capabilities=["redis", "diagnostics"],
        thread_id="thread-1",
        task_id="task-1",
    )
    existing_binding = target_module.TargetBinding(
        target_handle="tgt_existing",
        target_kind="cluster",
        resource_id="cluster-prod-checkout",
        display_name="checkout-cluster-prod",
        capabilities=["admin"],
        thread_id="thread-1",
        task_id="task-1",
    )
    materialized_scope = MaterializedTargetScope(
        selected_bindings=[selected_binding],
        attached_bindings=[existing_binding, selected_binding],
        target_toolset_generation=3,
        context_updates={
            "attached_target_handles": ["tgt_existing", "tgt_new"],
            "active_target_handle": "tgt_new",
            "target_toolset_generation": 3,
            "target_bindings": [
                existing_binding.model_dump(mode="json"),
                selected_binding.model_dump(mode="json"),
            ],
            "instance_id": "",
            "cluster_id": "",
        },
    )
    manager = MagicMock()
    manager.attach_bound_targets = AsyncMock()
    manager.get_toolset_generation.return_value = 7
    matches = [
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

    with patch(
        "redis_sre_agent.core.targets.materialize_bound_target_scope",
        new=AsyncMock(return_value=materialized_scope),
    ):
        scope = await bind_target_matches(
            matches=matches,
            thread_id="thread-1",
            task_id="task-1",
            replace_existing=False,
            manager=manager,
        )

    manager.attach_bound_targets.assert_awaited_once_with(
        [existing_binding, selected_binding],
        generation=3,
    )
    assert [binding.target_handle for binding in scope.bindings] == ["tgt_existing", "tgt_new"]
    assert scope.toolset_generation == 7
    assert scope.context_updates["attached_target_handles"] == ["tgt_existing", "tgt_new"]
    assert scope.context_updates["target_toolset_generation"] == 7


@pytest.mark.asyncio
async def test_bind_target_matches_awaits_async_toolset_generation():
    match = ResolvedTargetMatch(
        target_kind="instance",
        resource_id="redis-prod-checkout-cache",
        display_name="checkout-cache-prod",
        environment="production",
        target_type="oss_single",
        capabilities=["redis", "diagnostics"],
        confidence=0.94,
        match_reasons=["matched environment=production"],
    )
    manager = MagicMock()
    manager.attach_bound_targets = AsyncMock()
    manager.get_toolset_generation = AsyncMock(return_value=9)

    scope = await bind_target_matches(
        matches=[match],
        thread_id=None,
        task_id="task-1",
        replace_existing=False,
        manager=manager,
    )

    assert scope.toolset_generation == 9


def test_get_attached_target_handles_from_context_rejects_non_list_values():
    assert get_attached_target_handles_from_context(None) == []
    assert get_attached_target_handles_from_context({"attached_target_handles": "tgt_01"}) == []


def test_get_target_bindings_from_context_skips_invalid_bindings():
    bindings = get_target_bindings_from_context(
        {
            "target_bindings": [
                {
                    "target_handle": "tgt_valid",
                    "target_kind": "instance",
                    "resource_id": "redis-prod-checkout-cache",
                    "display_name": "checkout-cache-prod",
                },
                {"display_name": "invalid"},
            ]
        }
    )

    assert len(bindings) == 1
    assert bindings[0].target_handle == "tgt_valid"
    assert get_target_bindings_from_context({"target_bindings": "invalid"}) == []
    assert get_target_bindings_from_context(None) == []


@pytest.mark.asyncio
async def test_build_attached_target_scope_prompt_returns_none_without_scope():
    assert await build_attached_target_scope_prompt({}) is None


@pytest.mark.asyncio
async def test_build_attached_target_scope_prompt_handles_binding_edge_cases():
    cluster = RedisCluster(
        id="cluster-prod-1",
        name="cluster-prod-1",
        cluster_type="oss_cluster",
        environment="production",
        description="Production cluster",
    )
    context = {
        "attached_target_handles": [
            "tgt_meta_only",
            "tgt_instance_missing",
            "tgt_cluster_found",
            "tgt_cluster_missing",
            "tgt_unknown",
        ],
        "target_bindings": [
            {
                "target_handle": "tgt_instance_missing",
                "target_kind": "instance",
                "resource_id": "redis-missing",
                "display_name": "missing-instance",
                "capabilities": ["redis"],
            },
            {
                "target_handle": "tgt_cluster_found",
                "target_kind": "cluster",
                "resource_id": "cluster-prod-1",
                "display_name": "prod-cluster",
                "capabilities": ["admin"],
            },
            {
                "target_handle": "tgt_cluster_missing",
                "target_kind": "cluster",
                "resource_id": "cluster-missing",
                "display_name": "missing-cluster",
                "capabilities": ["admin"],
            },
            {
                "target_handle": "tgt_unknown",
                "target_kind": "custom",
                "resource_id": "custom-1",
                "display_name": "custom-target",
                "capabilities": ["custom"],
            },
            {
                "target_handle": "tgt_extra",
                "target_kind": "instance",
                "resource_id": "redis-extra",
                "display_name": "extra-instance",
                "capabilities": ["redis"],
            },
        ],
    }

    async def _get_instance(instance_id: str):
        return None

    async def _get_cluster(cluster_id: str):
        return cluster if cluster_id == "cluster-prod-1" else None

    with (
        patch("redis_sre_agent.core.targets.get_instance_by_id", new=_get_instance),
        patch("redis_sre_agent.core.targets.get_cluster_by_id", new=_get_cluster),
    ):
        prompt = await build_attached_target_scope_prompt(context)

    assert prompt is not None
    assert "handle=tgt_meta_only [metadata unavailable]" in prompt
    assert "missing-instance" in prompt and "state=missing" in prompt
    assert "prod-cluster" in prompt and "cluster_id=cluster-prod-1" in prompt
    assert "missing-cluster" in prompt and "cluster_id=cluster-missing" in prompt
    assert "custom-target" in prompt and "kind=custom" in prompt
    assert "extra-instance" in prompt


@pytest.mark.asyncio
async def test_build_attached_target_scope_prompt_single_target_uses_single_target_instruction():
    instance = RedisInstance(
        id="redis-prod-checkout-cache",
        name="checkout-cache-prod",
        connection_url="redis://localhost:6379",
        environment="production",
        usage="cache",
        description="Checkout cache",
        instance_type="oss_single",
    )
    context = {
        "attached_target_handles": ["tgt_01"],
        "target_bindings": [
            {
                "target_handle": "tgt_01",
                "target_kind": "instance",
                "resource_id": "redis-prod-checkout-cache",
                "display_name": "checkout-cache-prod",
                "capabilities": ["redis", "diagnostics"],
            }
        ],
    }

    with patch(
        "redis_sre_agent.core.targets.get_instance_by_id",
        new=AsyncMock(return_value=instance),
    ):
        prompt = await build_attached_target_scope_prompt(context)

    assert prompt is not None
    assert "Use the target-scoped tools for the attached handle above" in prompt


@pytest.mark.asyncio
async def test_build_attached_target_prompt_loader_memoizes_none_results():
    prompt_builder = AsyncMock(return_value=None)
    loader = build_attached_target_prompt_loader({}, 1, prompt_builder)

    assert await loader() is None
    assert await loader() is None
    prompt_builder.assert_awaited_once_with({})


@pytest.mark.asyncio
async def test_build_attached_target_prompt_loader_snapshots_context():
    prompt_builder = AsyncMock(return_value="ATTACHED TARGET SCOPE")
    context = {"attached_target_handles": ["tgt_01"]}
    loader = build_attached_target_prompt_loader(context, 1, prompt_builder)

    context["attached_target_handles"].append("tgt_02")

    assert await loader() == "ATTACHED TARGET SCOPE"
    prompt_builder.assert_awaited_once_with({"attached_target_handles": ["tgt_01"]})


def test_build_ephemeral_target_bindings_generates_opaque_handles():
    matches = [
        ResolvedTargetMatch(
            target_kind="cluster",
            resource_id="cluster-1",
            display_name="prod-enterprise-cluster",
            environment="production",
            target_type="redis_enterprise",
            capabilities=["admin"],
            confidence=0.9,
            match_reasons=["matched kind=cluster"],
        )
    ]

    bindings = build_ephemeral_target_bindings(matches, thread_id="thread-1", task_id="task-1")

    assert len(bindings) == 1
    assert bindings[0].target_handle.startswith("tgt_")
    assert bindings[0].resource_id == "cluster-1"


@pytest.mark.asyncio
async def test_sync_target_catalog_scan_fallback_only_deletes_prefixed_stale_keys():
    instance = RedisInstance(
        id="redis-prod-checkout-cache",
        name="checkout-cache-prod",
        connection_url="redis://cache.internal:6379/0",
        environment="production",
        usage="cache",
        description="Primary checkout cache",
        instance_type="oss_single",
    )
    mock_client = AsyncMock()
    mock_client.scan = AsyncMock(
        side_effect=[
            (
                0,
                [
                    b"sre_targets:instance:stale-target",
                    b"sre_targets:instance:redis-prod-checkout-cache",
                    b"not-sre_targets:instance:should-not-delete",
                    b"sre_targets:",
                ],
            )
        ]
    )
    mock_client.delete = AsyncMock()

    with (
        patch("redis_sre_agent.core.targets.get_redis_client", return_value=mock_client),
        patch(
            "redis_sre_agent.core.targets._ensure_targets_index_exists",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "redis_sre_agent.core.targets.get_targets_index",
            new=AsyncMock(side_effect=RuntimeError("index unavailable")),
        ),
    ):
        result = await sync_target_catalog(instances=[instance], clusters=[])

    assert result is True
    deleted_keys = [call.args[0] for call in mock_client.delete.await_args_list]
    assert deleted_keys == ["sre_targets:instance:stale-target"]

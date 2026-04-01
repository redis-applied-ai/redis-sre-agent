"""Tests for unified target discovery and safe thread binding state."""

from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.core.targets import (
    ResolvedTargetMatch,
    TargetCatalogDoc,
    attach_target_matches,
    build_ephemeral_target_bindings,
    build_target_doc_from_instance,
    resolve_target_query,
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
    assert update_payload["instance_id"] == "redis-prod-checkout-cache"
    assert update_payload["cluster_id"] == ""
    assert update_payload["attached_target_handles"] == [bindings[0].target_handle]
    assert "connection_url" not in str(update_payload)
    assert "secret" not in str(update_payload)


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

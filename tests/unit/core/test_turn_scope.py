"""Tests for the normalized TurnScope contract."""

import pytest

from redis_sre_agent.core.targets import TargetBinding
from redis_sre_agent.core.turn_scope import TurnScope, build_legacy_target_scope_adapter


def test_turn_scope_from_context_defaults_to_zero_scope():
    scope = TurnScope.from_context(
        {},
        thread_id="thread-123",
        session_id="session-123",
    )

    assert scope.scope_kind == "zero_scope"
    assert scope.thread_id == "thread-123"
    assert scope.session_id == "session-123"
    assert scope.bindings == []
    assert scope.automation_mode == "interactive"
    assert scope.support_package_context == {}
    assert scope.target_count == 0


def test_turn_scope_from_context_detects_target_binding_scope():
    scope = TurnScope.from_context(
        {
            "thread_id": "thread-123",
            "session_id": "session-123",
            "target_toolset_generation": 4,
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
    )

    assert scope.scope_kind == "target_bindings"
    assert scope.thread_id == "thread-123"
    assert scope.session_id == "session-123"
    assert scope.toolset_generation == 4
    assert len(scope.bindings) == 1
    assert scope.bindings[0].target_handle == "tgt_01"


def test_turn_scope_from_context_detects_support_package_scope():
    scope = TurnScope.from_context(
        {
            "thread_id": "thread-123",
            "automated": True,
            "support_package_id": "pkg-1",
            "support_package_path": "/tmp/pkg-1",
            "resolution_policy": "require_target",
        }
    )

    assert scope.scope_kind == "support_package"
    assert scope.automation_mode == "automated"
    assert scope.resolution_policy == "require_target"
    assert scope.support_package_context == {
        "support_package_id": "pkg-1",
        "support_package_path": "/tmp/pkg-1",
    }


def test_turn_scope_to_thread_context_serializes_bindings_and_support_package():
    scope = TurnScope(
        thread_id="thread-123",
        session_id="session-123",
        scope_kind="target_bindings",
        bindings=[
            TargetBinding(
                target_handle="tgt_01",
                target_kind="instance",
                resource_id="redis-prod-checkout-cache",
                display_name="checkout-cache-prod",
                capabilities=["redis", "diagnostics"],
            )
        ],
        toolset_generation=5,
        automation_mode="automated",
        resolution_policy="allow_multiple",
        support_package_context={"support_package_id": "pkg-1"},
    )

    context = scope.to_thread_context()

    assert context["thread_id"] == "thread-123"
    assert context["session_id"] == "session-123"
    assert context["attached_target_handles"] == ["tgt_01"]
    assert context["target_toolset_generation"] == 5
    assert context["automated"] is True
    assert context["resolution_policy"] == "allow_multiple"
    assert context["support_package_id"] == "pkg-1"
    assert context["target_bindings"][0]["resource_id"] == "redis-prod-checkout-cache"


def test_turn_scope_to_thread_context_omits_empty_binding_fields_for_zero_scope():
    scope = TurnScope(
        thread_id="thread-123",
        session_id="session-123",
        scope_kind="zero_scope",
    )

    context = scope.to_thread_context()

    assert "attached_target_handles" not in context
    assert "target_bindings" not in context
    assert "target_toolset_generation" not in context


def test_turn_scope_from_context_falls_back_when_toolset_generation_invalid():
    scope = TurnScope.from_context({"target_toolset_generation": "invalid"})

    assert scope.toolset_generation == 0


def test_turn_scope_to_thread_context_keeps_generation_without_bindings():
    scope = TurnScope(
        thread_id="thread-123",
        session_id="session-123",
        scope_kind="zero_scope",
        toolset_generation=4,
    )

    context = scope.to_thread_context()

    assert context["target_toolset_generation"] == 4


def test_build_legacy_target_scope_adapter_wraps_instance_scope_in_turn_scope_context():
    scope, context = build_legacy_target_scope_adapter(
        instance_id="redis-prod-checkout-cache",
        thread_id="thread-123",
        session_id="session-123",
        resolution_policy="require_target",
    )

    assert scope.scope_kind == "target_bindings"
    assert scope.seed_hints == {"instance_id": "redis-prod-checkout-cache"}
    assert len(scope.bindings) == 1
    assert scope.bindings[0].target_kind == "instance"
    assert scope.bindings[0].resource_id == "redis-prod-checkout-cache"
    assert context["instance_id"] == "redis-prod-checkout-cache"
    assert context["attached_target_handles"] == [scope.bindings[0].target_handle]
    assert context["target_bindings"][0]["resource_id"] == "redis-prod-checkout-cache"
    assert context["turn_scope"]["bindings"][0]["resource_id"] == "redis-prod-checkout-cache"


def test_build_legacy_target_scope_adapter_supports_automated_support_package_scope():
    scope, context = build_legacy_target_scope_adapter(
        support_package_context={
            "support_package_id": "pkg-1",
            "support_package_path": "/tmp/pkg-1",
        },
        automation_mode="automated",
    )

    assert scope.scope_kind == "support_package"
    assert scope.automation_mode == "automated"
    assert context["automated"] is True
    assert context["support_package_id"] == "pkg-1"
    assert context["support_package_path"] == "/tmp/pkg-1"


def test_build_legacy_target_scope_adapter_rejects_instance_and_cluster():
    with pytest.raises(ValueError, match="Please provide only one of instance_id or cluster_id"):
        build_legacy_target_scope_adapter(instance_id="inst-1", cluster_id="cluster-1")

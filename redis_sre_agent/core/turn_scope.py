"""Normalized runtime scope contract for agent turns."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field
from ulid import ULID

from redis_sre_agent.core.targets import (
    TargetBinding,
    get_attached_target_handles_from_context,
    get_target_bindings_from_context,
)

TurnScopeKind = Literal["zero_scope", "target_bindings", "support_package"]
TurnScopeResolutionPolicy = Literal[
    "allow_zero_scope",
    "require_target",
    "require_exact",
    "allow_multiple",
]
TurnScopeAutomationMode = Literal["interactive", "automated"]


def _coerce_optional_str(value: Any) -> Optional[str]:
    """Normalize optional identifier values to strings for runtime compatibility."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


class TurnScope(BaseModel):
    """Normalized runtime execution scope for a single agent turn."""

    thread_id: Optional[str] = None
    session_id: Optional[str] = None
    scope_kind: TurnScopeKind = "zero_scope"
    attached_target_handles: list[str] = Field(default_factory=list)
    bindings: list[TargetBinding] = Field(default_factory=list)
    toolset_generation: int = 0
    prompt_context: dict[str, Any] = Field(default_factory=dict)
    seed_hints: dict[str, Any] = Field(default_factory=dict)
    resolution_policy: TurnScopeResolutionPolicy = "allow_zero_scope"
    automation_mode: TurnScopeAutomationMode = "interactive"
    support_package_context: dict[str, Any] = Field(default_factory=dict)

    @property
    def target_count(self) -> int:
        """Return the number of bound targets in scope."""
        return len(self.bindings)

    @property
    def single_binding(self) -> Optional[TargetBinding]:
        """Return the only bound target when scope is singular."""
        if len(self.bindings) != 1:
            return None
        return self.bindings[0]

    @property
    def single_binding_kind(self) -> Optional[str]:
        """Return the kind of the only bound target, if present."""
        binding = self.single_binding
        return binding.target_kind if binding else None

    @property
    def single_resource_id(self) -> Optional[str]:
        """Return the resource id of the only bound target, if present."""
        binding = self.single_binding
        return binding.resource_id if binding else None

    @classmethod
    def from_context(
        cls,
        context: Optional[Dict[str, Any]],
        *,
        thread_id: Optional[str] = None,
        session_id: Optional[str] = None,
        prompt_context: Optional[Dict[str, Any]] = None,
        seed_hints: Optional[Dict[str, Any]] = None,
    ) -> "TurnScope":
        """Build a TurnScope from a routing or thread context payload."""
        payload = context or {}
        attached_target_handles = get_attached_target_handles_from_context(payload)
        bindings = get_target_bindings_from_context(payload)
        support_package_context = {
            key: payload[key]
            for key in ("support_package_id", "support_package_path")
            if payload.get(key)
        }
        automated = bool(payload.get("automated"))
        resolution_policy = str(payload.get("resolution_policy") or "").strip() or None
        if resolution_policy not in {
            "allow_zero_scope",
            "require_target",
            "require_exact",
            "allow_multiple",
        }:
            resolution_policy = "allow_zero_scope"

        if bindings:
            scope_kind: TurnScopeKind = "target_bindings"
        elif support_package_context:
            scope_kind = "support_package"
        else:
            scope_kind = "zero_scope"

        try:
            toolset_generation = int(payload.get("target_toolset_generation") or 0)
        except Exception:
            toolset_generation = 0

        return cls(
            thread_id=_coerce_optional_str(thread_id or payload.get("thread_id")),
            session_id=_coerce_optional_str(session_id or payload.get("session_id")),
            scope_kind=scope_kind,
            attached_target_handles=attached_target_handles,
            bindings=bindings,
            toolset_generation=toolset_generation,
            prompt_context=dict(prompt_context or {}),
            seed_hints=dict(seed_hints or {}),
            resolution_policy=resolution_policy,
            automation_mode="automated" if automated else "interactive",
            support_package_context=support_package_context,
        )

    def to_thread_context(self) -> dict[str, Any]:
        """Serialize the scope to thread-compatible context fields."""
        context: dict[str, Any] = {
            "thread_id": self.thread_id or "",
            "session_id": self.session_id or "",
            "automated": self.automation_mode == "automated",
            "resolution_policy": self.resolution_policy,
            "attached_target_handles": list(self.attached_target_handles),
            "target_bindings": [],
            "target_toolset_generation": self.toolset_generation,
        }
        if self.bindings:
            context["attached_target_handles"] = [
                binding.target_handle for binding in self.bindings
            ]
            context["target_bindings"] = [
                binding.model_dump(mode="json") for binding in self.bindings
            ]
        context.update(self.support_package_context)
        return context


def build_legacy_target_scope_adapter(
    *,
    instance_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    session_id: Optional[str] = None,
    support_package_context: Optional[Dict[str, Any]] = None,
    automation_mode: TurnScopeAutomationMode = "interactive",
    resolution_policy: TurnScopeResolutionPolicy = "allow_zero_scope",
    prompt_context: Optional[Dict[str, Any]] = None,
    seed_hints: Optional[Dict[str, Any]] = None,
    include_legacy_ids: bool = True,
) -> tuple[TurnScope, dict[str, Any]]:
    """Build a TurnScope plus thread context from legacy single-target inputs."""
    normalized_instance_id = _coerce_optional_str(instance_id)
    normalized_cluster_id = _coerce_optional_str(cluster_id)
    if normalized_instance_id and normalized_cluster_id:
        raise ValueError("Please provide only one of instance_id or cluster_id")

    bindings: list[TargetBinding] = []
    if normalized_instance_id:
        bindings.append(
            TargetBinding(
                target_handle=f"tgt_{ULID()}",
                target_kind="instance",
                resource_id=normalized_instance_id,
                display_name=normalized_instance_id,
                capabilities=["redis"],
                thread_id=_coerce_optional_str(thread_id),
            )
        )
    elif normalized_cluster_id:
        bindings.append(
            TargetBinding(
                target_handle=f"tgt_{ULID()}",
                target_kind="cluster",
                resource_id=normalized_cluster_id,
                display_name=normalized_cluster_id,
                capabilities=["admin"],
                thread_id=_coerce_optional_str(thread_id),
            )
        )

    normalized_support_package_context = {
        key: value
        for key, value in (support_package_context or {}).items()
        if _coerce_optional_str(value) is not None
    }
    if bindings:
        scope_kind: TurnScopeKind = "target_bindings"
    elif normalized_support_package_context:
        scope_kind = "support_package"
    else:
        scope_kind = "zero_scope"

    combined_seed_hints = dict(seed_hints or {})
    if normalized_instance_id:
        combined_seed_hints.setdefault("instance_id", normalized_instance_id)
    if normalized_cluster_id:
        combined_seed_hints.setdefault("cluster_id", normalized_cluster_id)

    scope = TurnScope(
        thread_id=_coerce_optional_str(thread_id),
        session_id=_coerce_optional_str(session_id),
        scope_kind=scope_kind,
        bindings=bindings,
        toolset_generation=0,
        prompt_context=dict(prompt_context or {}),
        seed_hints=combined_seed_hints,
        resolution_policy=resolution_policy,
        automation_mode=automation_mode,
        support_package_context=normalized_support_package_context,
    )
    context = scope.to_thread_context()
    if include_legacy_ids:
        if normalized_instance_id:
            context["instance_id"] = normalized_instance_id
        if normalized_cluster_id:
            context["cluster_id"] = normalized_cluster_id
    context["turn_scope"] = scope.model_dump(mode="json")
    return scope, context

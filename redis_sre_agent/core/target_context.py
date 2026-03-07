"""Helpers for validating turn target context (instance_id / cluster_id)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Optional


@dataclass(frozen=True)
class TurnTarget:
    """Normalized target identifiers provided for a turn."""

    instance_id: Optional[str]
    cluster_id: Optional[str]

    def has_any(self) -> bool:
        return bool(self.instance_id or self.cluster_id)

    def has_both(self) -> bool:
        return bool(self.instance_id and self.cluster_id)


def normalize_target_id(value: Any) -> Optional[str]:
    """Normalize a target identifier to a stripped string or None."""
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    normalized = str(value).strip()
    return normalized or None


def extract_turn_target(context: Optional[Mapping[str, Any]]) -> TurnTarget:
    """Extract normalized target identifiers from a context mapping."""
    return TurnTarget(
        instance_id=normalize_target_id((context or {}).get("instance_id")),
        cluster_id=normalize_target_id((context or {}).get("cluster_id")),
    )


def require_at_most_one_target(target: TurnTarget) -> None:
    """Ensure callers provide at most one target identifier."""
    if target.has_both():
        raise ValueError(
            "Provide only one target: instance_id or cluster_id, not both."
        )


def require_exactly_one_target_for_new_turn(target: TurnTarget) -> None:
    """Ensure a new turn is target-scoped."""
    if not target.has_any():
        raise ValueError(
            "New turns require exactly one target: provide instance_id or cluster_id."
        )


async def require_continuation_target_compatibility(
    *,
    provided_target: TurnTarget,
    thread_target: TurnTarget,
    get_instance_by_id: Callable[[str], Awaitable[Any]],
) -> None:
    """Validate continuation target overrides against saved thread target context.

    Rules:
    - If no target is provided for continuation, it's always valid.
    - If a target is provided, the thread must already be target-scoped.
    - provided instance_id must match thread instance_id when present.
    - provided cluster_id must match thread cluster_id when present.
    - Cross-field equivalence is allowed when one side is missing from thread context:
      - provided instance_id must belong to thread cluster_id
      - provided cluster_id must match thread instance_id's linked cluster_id
    """
    if not provided_target.has_any():
        return

    if not thread_target.has_any():
        raise ValueError(
            "Thread has no saved target context. Start a new thread to specify instance_id or cluster_id."
        )

    if provided_target.instance_id:
        if thread_target.instance_id and provided_target.instance_id != thread_target.instance_id:
            raise ValueError(
                "Thread target mismatch: this thread is locked to "
                f"instance_id={thread_target.instance_id}. Start a new thread to switch targets."
            )

        if thread_target.cluster_id:
            provided_instance = await get_instance_by_id(provided_target.instance_id)
            if not provided_instance:
                raise ValueError(f"Instance not found: {provided_target.instance_id}")
            provided_cluster_id = normalize_target_id(getattr(provided_instance, "cluster_id", None))
            if provided_cluster_id != thread_target.cluster_id:
                raise ValueError(
                    "Thread target mismatch: provided instance_id="
                    f"{provided_target.instance_id} is not linked to "
                    f"thread cluster_id={thread_target.cluster_id}."
                )

    if provided_target.cluster_id:
        if thread_target.cluster_id and provided_target.cluster_id != thread_target.cluster_id:
            raise ValueError(
                "Thread target mismatch: this thread is locked to "
                f"cluster_id={thread_target.cluster_id}. Start a new thread to switch targets."
            )

        if thread_target.instance_id:
            thread_instance = await get_instance_by_id(thread_target.instance_id)
            if not thread_instance:
                raise ValueError(
                    "Thread target mismatch: this thread is locked to "
                    f"instance_id={thread_target.instance_id}, but that instance no longer exists."
                )
            thread_instance_cluster_id = normalize_target_id(getattr(thread_instance, "cluster_id", None))
            if thread_instance_cluster_id != provided_target.cluster_id:
                raise ValueError(
                    "Thread target mismatch: provided cluster_id="
                    f"{provided_target.cluster_id} does not match "
                    f"thread instance_id={thread_target.instance_id} "
                    f"(linked cluster_id={thread_instance_cluster_id or 'none'})."
                )

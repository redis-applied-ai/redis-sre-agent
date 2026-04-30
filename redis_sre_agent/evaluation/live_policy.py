"""Helpers for loading and enforcing scheduled live-eval policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from redis_sre_agent.evaluation.report_schema import EvalBaselinePolicy


def _normalize_policy_payload(
    payload: dict[str, Any],
    *,
    profile: str | None,
    policy_path: Path,
) -> dict[str, Any]:
    profiles = payload.get("profiles")
    if isinstance(profiles, dict):
        selected_profile = profile
        if not selected_profile:
            if "scheduled_live" in profiles:
                selected_profile = "scheduled_live"
            elif len(profiles) == 1:
                selected_profile = next(iter(profiles))
            else:
                available = ", ".join(sorted(profiles))
                raise ValueError(
                    f"baseline policy file requires a profile. Available profiles: {available}"
                )
        profile_payload = profiles.get(selected_profile)
        if not isinstance(profile_payload, dict):
            available = ", ".join(sorted(profiles))
            raise KeyError(
                f"unknown baseline policy profile '{selected_profile}'. Available: {available}"
            )
        return {"mode": selected_profile, **profile_payload}

    if profile:
        raise ValueError(
            f"baseline policy file does not define profiles but a profile was requested: {policy_path}"
        )
    return payload


def load_eval_baseline_policy(
    path: str | Path,
    *,
    profile: str | None = None,
) -> EvalBaselinePolicy:
    """Load a baseline policy file from YAML."""

    policy_path = Path(path).expanduser().resolve()
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"baseline policy file must deserialize to a mapping: {policy_path}")
    normalized = _normalize_policy_payload(payload, profile=profile, policy_path=policy_path)
    return EvalBaselinePolicy.model_validate(normalized)


def materialize_eval_baseline_policy(
    policy: EvalBaselinePolicy,
    *,
    event_name: str | None = None,
    update_baseline: bool = False,
) -> EvalBaselinePolicy:
    """Resolve event-aware baseline policy fields for one run."""

    normalized_event = str(event_name or "").strip()
    update_allowed = policy.update_allowed
    if normalized_event and policy.update_allowed_events:
        update_allowed = normalized_event in policy.update_allowed_events
    if update_baseline and update_allowed is False:
        raise ValueError(
            "baseline update was requested but the active policy does not allow updates"
        )
    return policy.model_copy(update={"update_allowed": update_allowed})


def ensure_live_eval_allowed(
    policy: EvalBaselinePolicy,
    *,
    event_name: str | None = None,
) -> None:
    """Raise when a live eval is attempted outside the allowed triggers."""

    normalized_event = str(event_name or "").strip()
    if normalized_event == "manual":
        normalized_event = "workflow_dispatch"
    allowed = [trigger for trigger in policy.allowed_triggers if str(trigger).strip()]
    if normalized_event and allowed and normalized_event not in allowed:
        allowed_list = ", ".join(allowed)
        raise ValueError(
            f"live evals are restricted to these triggers: {allowed_list}; got {normalized_event}"
        )


__all__ = [
    "ensure_live_eval_allowed",
    "load_eval_baseline_policy",
    "materialize_eval_baseline_policy",
]

"""Scenario-backed tool execution virtualization for eval runs."""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from redis_sre_agent.evaluation.injection import EvalToolDispatchResult, EvalToolRuntime
from redis_sre_agent.evaluation.scenarios import (
    EvalScenario,
    EvalToolBehavior,
    EvalToolFailure,
    EvalToolFailureKind,
    EvalToolResponder,
)
from redis_sre_agent.evaluation.tool_identity import ToolIdentityCatalog, normalize_provider_family


def _normalize_operation(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _normalize_target_handle(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return normalized or None


def _value_matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, Mapping):
            return False
        return all(_value_matches(value, actual.get(key)) for key, value in expected.items())
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) > len(actual):
            return False
        return all(_value_matches(value, actual[index]) for index, value in enumerate(expected))
    return actual == expected


def _load_fixture_payload(path: Path) -> Any:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix in {".yaml", ".yml"}:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


def _merge_state(target: dict[str, Any], updates: Mapping[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _merge_state(target[key], value)
            continue
        target[key] = copy.deepcopy(value)


@dataclass
class FixtureBehaviorState:
    """Shared mutable mock state for one eval scenario run."""

    state: dict[str, Any] = field(default_factory=dict)
    call_counts: dict[tuple[str, str, str | None, str | None], int] = field(default_factory=dict)


class FixtureBehaviorResolver:
    """Resolve one logical mock behavior while sharing scenario state."""

    def __init__(
        self,
        *,
        scenario: EvalScenario,
        behaviors: Mapping[tuple[str, str, str | None, str | None], EvalToolBehavior],
        state: FixtureBehaviorState | None = None,
    ) -> None:
        self._scenario = scenario
        self._behaviors = dict(behaviors)
        self._state = state or FixtureBehaviorState()

    def _lookup_behavior(
        self,
        *,
        provider_family: str,
        operation: str,
        target_handle: str | None = None,
        server_name: str | None = None,
    ) -> EvalToolBehavior | None:
        return self._behaviors.get(
            (
                provider_family,
                operation,
                _normalize_target_handle(target_handle),
                server_name,
            )
        ) or self._behaviors.get(
            (provider_family, operation, None, server_name)
        ) or self._behaviors.get(
            (
                provider_family,
                operation,
                _normalize_target_handle(target_handle),
                None,
            )
        ) or self._behaviors.get((provider_family, operation, None, None))

    def _materialize_fixture_value(self, value: Any) -> Any:
        if not isinstance(value, str):
            return copy.deepcopy(value)

        fixture_path = self._scenario.resolve_fixture_path(value)
        if fixture_path.is_file():
            return _load_fixture_payload(fixture_path)
        return value

    def _when_matches(
        self,
        responder: EvalToolResponder,
        *,
        args: dict[str, Any],
        call_count: int,
    ) -> bool:
        when = responder.when
        if when is None:
            return True
        if when.call_count is not None and when.call_count != call_count:
            return False
        if when.args_contains and not _value_matches(when.args_contains, args):
            return False
        if when.state_contains and not _value_matches(when.state_contains, self._state.state):
            return False
        return True

    def _apply_state_updates(self, updates: Mapping[str, Any]) -> None:
        if not updates:
            return
        _merge_state(self._state.state, updates)

    def _resolve_failure_result(
        self,
        *,
        failure: EvalToolFailure,
        result: Any,
    ) -> Any:
        if failure.kind is EvalToolFailureKind.PARTIAL_DATA:
            if failure.result is not None:
                return self._materialize_fixture_value(failure.result)
            if result is not None:
                return self._materialize_fixture_value(result)
            return {}
        if failure.kind is EvalToolFailureKind.EMPTY_RESULT:
            if failure.result is not None:
                return self._materialize_fixture_value(failure.result)
            return {}
        return None

    def _raise_failure(
        self,
        *,
        failure: EvalToolFailure,
        provider_family: str,
        operation: str,
    ) -> None:
        message = failure.message or (
            f"Injected {failure.kind.value} failure for {provider_family}.{operation}"
        )
        if failure.kind is EvalToolFailureKind.TIMEOUT:
            raise asyncio.TimeoutError(message)
        if failure.kind is EvalToolFailureKind.AUTH_ERROR:
            raise PermissionError(message)
        if failure.kind is EvalToolFailureKind.RATE_LIMIT:
            raise RuntimeError(message)
        raise RuntimeError(message)

    def _resolve_behavior_result(
        self,
        *,
        behavior: EvalToolBehavior,
        args: dict[str, Any],
        call_count: int,
        provider_family: str,
        operation: str,
    ) -> Any:
        selected_responder = next(
            (
                responder
                for responder in behavior.responders
                if self._when_matches(responder, args=args, call_count=call_count)
            ),
            None,
        )

        if selected_responder is not None:
            self._apply_state_updates(selected_responder.state_updates)
            if selected_responder.failure is not None:
                resolved = self._resolve_failure_result(
                    failure=selected_responder.failure,
                    result=selected_responder.result,
                )
                if selected_responder.failure.kind in {
                    EvalToolFailureKind.PARTIAL_DATA,
                    EvalToolFailureKind.EMPTY_RESULT,
                }:
                    return resolved
                self._raise_failure(
                    failure=selected_responder.failure,
                    provider_family=provider_family,
                    operation=operation,
                )
            return self._materialize_fixture_value(selected_responder.result)

        self._apply_state_updates(behavior.state_updates)
        if behavior.failure is not None:
            resolved = self._resolve_failure_result(
                failure=behavior.failure,
                result=behavior.result,
            )
            if behavior.failure.kind in {
                EvalToolFailureKind.PARTIAL_DATA,
                EvalToolFailureKind.EMPTY_RESULT,
            }:
                return resolved
            self._raise_failure(
                failure=behavior.failure,
                provider_family=provider_family,
                operation=operation,
            )

        if behavior.result is not None:
            return self._materialize_fixture_value(behavior.result)

        raise ValueError(
            "No eval tool responder matched the call and no default result was configured"
        )

    def resolve(
        self,
        *,
        provider_family: str,
        operation: str,
        args: dict[str, Any],
        target_handle: str | None = None,
        server_name: str | None = None,
    ) -> Any:
        behavior = self._lookup_behavior(
            provider_family=provider_family,
            operation=operation,
            target_handle=target_handle,
            server_name=server_name,
        )
        if behavior is None:
            raise KeyError(
                f"No eval behavior configured for {provider_family}.{operation}"
                + (f" on MCP server {server_name}" if server_name else "")
            )

        identity_key = (provider_family, operation, target_handle, server_name)
        call_count = self._state.call_counts.get(identity_key, 0) + 1
        self._state.call_counts[identity_key] = call_count
        return self._resolve_behavior_result(
            behavior=behavior,
            args=args,
            call_count=call_count,
            provider_family=provider_family,
            operation=operation,
        )


class FixtureToolRuntime(EvalToolRuntime):
    """Resolve logical scenario tool behaviors against loaded runtime tools."""

    def __init__(
        self,
        *,
        scenario: EvalScenario,
        provider_behaviors: Mapping[tuple[str, str, str | None, str | None], EvalToolBehavior],
        state: FixtureBehaviorState | None = None,
    ) -> None:
        self._resolver = FixtureBehaviorResolver(
            scenario=scenario,
            behaviors=provider_behaviors,
            state=state,
        )
        self._declared_provider_keys = {
            (provider_family, server_name)
            for provider_family, _operation, _target_handle, server_name in provider_behaviors
        }

    def _lookup_behavior(
        self,
        *,
        provider_family: str,
        operation: str,
        target_handle: str | None = None,
    ) -> EvalToolBehavior | None:
        return self._resolver._lookup_behavior(
            provider_family=provider_family,
            operation=operation,
            target_handle=target_handle,
        )

    async def dispatch_tool_call(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        tool_by_name: Mapping[str, Any],
        routing_table: Mapping[str, Any],
    ) -> EvalToolDispatchResult | None:
        catalog = ToolIdentityCatalog.from_runtime_tables(tool_by_name, routing_table)
        try:
            identity = catalog.get(tool_name)
        except KeyError:
            return None

        behavior = self._lookup_behavior(
            provider_family=identity.provider_family,
            operation=identity.operation,
            target_handle=identity.target_handle,
        )
        if behavior is None:
            if (identity.provider_family, identity.server_name) in self._declared_provider_keys:
                return EvalToolDispatchResult(
                    result={
                        "error": (f"Tool '{tool_name}' is not configured for this eval scenario")
                    }
                )
            return None

        return EvalToolDispatchResult(
            result=self._resolver.resolve(
                provider_family=identity.provider_family,
                operation=identity.operation,
                target_handle=identity.target_handle,
                server_name=identity.server_name,
                args=args,
            )
        )


def build_fixture_tool_runtime(
    scenario: EvalScenario,
    *,
    state: FixtureBehaviorState | None = None,
) -> FixtureToolRuntime | None:
    """Build a scenario-backed provider override registry, if the scenario declares one."""

    provider_behaviors: dict[tuple[str, str, str | None, str | None], EvalToolBehavior] = {}
    for provider_family, operation_map in scenario.tools.providers.items():
        normalized_provider_family = normalize_provider_family(provider_family)
        for operation, behavior in operation_map.items():
            provider_behaviors[
                (normalized_provider_family, _normalize_operation(operation), None, None)
            ] = behavior
            for target_handle, target_behavior in behavior.target_overrides.items():
                provider_behaviors[
                    (
                        normalized_provider_family,
                        _normalize_operation(operation),
                        _normalize_target_handle(target_handle),
                        None,
                    )
                ] = target_behavior

    if not provider_behaviors:
        return None

    return FixtureToolRuntime(
        scenario=scenario,
        provider_behaviors=provider_behaviors,
        state=state,
    )


__all__ = [
    "FixtureBehaviorResolver",
    "FixtureBehaviorState",
    "FixtureToolRuntime",
    "build_fixture_tool_runtime",
]

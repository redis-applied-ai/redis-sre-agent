"""Top-level eval runner dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from redis_sre_agent.evaluation.runtime import (
    EvalFullTurnResult,
    EvalRunResult,
    EvalRuntime,
    load_eval_scenario,
    run_full_turn_scenario,
)
from redis_sre_agent.evaluation.scenarios import EvalScenario, ExecutionLane
from redis_sre_agent.targets import TargetBindingService


class EvalRunner:
    """Minimal scenario runner that dispatches to the full-turn harness."""

    def __init__(
        self,
        *,
        redis_client: Any = None,
        target_binding_service: TargetBindingService | None = None,
    ) -> None:
        self._redis_client = redis_client
        self._target_binding_service = target_binding_service

    async def run_scenario(
        self,
        scenario: EvalScenario,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        context_overrides: dict[str, Any] | None = None,
    ) -> EvalFullTurnResult:
        if scenario.execution.lane is not ExecutionLane.FULL_TURN:
            raise NotImplementedError("agent_only eval runs are owned by a separate Phase 1 task")

        return await run_full_turn_scenario(
            scenario,
            user_id=user_id,
            session_id=session_id,
            redis_client=self._redis_client,
            target_binding_service=self._target_binding_service,
            context_overrides=context_overrides,
        )


async def run_eval_scenario(
    scenario_or_path: EvalScenario | str | Path,
    *,
    runtime: EvalRuntime | None = None,
    user_id: str | None = None,
    extra_context: dict[str, Any] | None = None,
) -> EvalRunResult:
    """Load and run one eval scenario through the configured runtime."""
    scenario = load_eval_scenario(scenario_or_path)
    active_runtime = runtime or EvalRuntime()
    return await active_runtime.run(
        scenario,
        user_id=user_id,
        extra_context=extra_context,
    )


__all__ = ["EvalRunner", "run_eval_scenario"]

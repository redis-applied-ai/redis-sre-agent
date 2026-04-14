"""Full-turn eval harness around the production turn entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from redis_sre_agent.core.targets import build_bound_target_scope_context
from redis_sre_agent.core.tasks import TaskManager
from redis_sre_agent.core.threads import ThreadManager, _build_initial_context
from redis_sre_agent.core.turn_scope import TurnScope
from redis_sre_agent.evaluation.fake_mcp import build_fixture_mcp_runtime
from redis_sre_agent.evaluation.injection import eval_injection_scope
from redis_sre_agent.evaluation.knowledge_backend import build_fixture_knowledge_backend
from redis_sre_agent.evaluation.runtime_overrides import (
    EvalRuntimeOverrides,
)
from redis_sre_agent.evaluation.scenarios import EvalScenario, ExecutionLane
from redis_sre_agent.evaluation.tool_runtime import FixtureBehaviorState, build_fixture_tool_runtime
from redis_sre_agent.targets import TargetBindingService
from redis_sre_agent.targets.contracts import PublicTargetBinding, PublicTargetMatch

_REQUESTED_AGENT_TYPES = {
    "chat": "chat",
    "knowledge": "knowledge",
    "knowledge_only": "knowledge",
    "redis_chat": "chat",
    "redis_triage": "triage",
    "triage": "triage",
}


class EvalFullTurnResult(BaseModel):
    """Captured output from one production-path eval turn."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    scenario_name: str | None = None
    scenario_provenance: dict[str, Any] = Field(default_factory=dict)
    execution_lane: ExecutionLane
    thread_id: str
    task_id: str
    task_status: str | None = None
    initial_context: dict[str, Any] = Field(default_factory=dict)
    turn_context: dict[str, Any] = Field(default_factory=dict)
    turn_result: dict[str, Any] = Field(default_factory=dict)


EvalRunResult = EvalFullTurnResult


async def _default_turn_processor(**kwargs: Any) -> dict[str, Any]:
    """Call the production turn processor."""

    from redis_sre_agent.core.docket_tasks import process_agent_turn

    return await process_agent_turn(**kwargs)


def _normalize_requested_agent_type(agent_name: str | None) -> str:
    normalized = str(agent_name or "").strip().lower()
    if not normalized:
        raise ValueError("full_turn scenarios that bypass the router must set execution.agent")
    try:
        return _REQUESTED_AGENT_TYPES[normalized]
    except KeyError as exc:
        available = ", ".join(sorted(_REQUESTED_AGENT_TYPES))
        raise KeyError(
            f"Unsupported full_turn agent '{agent_name}'. Available agents: {available}"
        ) from exc


def _build_catalog_matches(
    scenario: EvalScenario,
    *,
    thread_id: str,
    task_id: str,
) -> tuple[list[PublicTargetMatch], dict[tuple[str, str], PublicTargetBinding]]:
    catalog_by_handle = {entry.handle: entry for entry in scenario.scope.target_catalog}
    matches: list[PublicTargetMatch] = []
    existing_by_subject: dict[tuple[str, str], PublicTargetBinding] = {}

    for handle in scenario.scope.bound_targets:
        entry = catalog_by_handle[handle]
        binding_subject = entry.resource_id or entry.handle
        public_metadata = dict(entry.public_metadata)
        environment = public_metadata.get("environment")
        target_type = public_metadata.get("target_type") or entry.cluster_type
        matches.append(
            PublicTargetMatch(
                target_kind=entry.kind,
                display_name=entry.display_name,
                environment=str(environment) if environment else None,
                target_type=str(target_type) if target_type else None,
                capabilities=list(entry.capabilities),
                confidence=1.0,
                public_metadata=public_metadata,
                resource_id=entry.resource_id,
            )
        )
        existing_by_subject[(entry.kind, binding_subject)] = PublicTargetBinding(
            target_handle=entry.handle,
            target_kind=entry.kind,
            display_name=entry.display_name,
            capabilities=list(entry.capabilities),
            public_metadata=public_metadata,
            thread_id=thread_id,
            task_id=task_id,
            resource_id=entry.resource_id,
        )

    return matches, existing_by_subject


async def build_full_turn_context(
    scenario: EvalScenario,
    *,
    thread_id: str,
    task_id: str,
    session_id: str,
    target_binding_service: TargetBindingService | None = None,
    context_overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], TurnScope]:
    """Compile scenario scope into the production turn context payload."""

    binding_service = target_binding_service or TargetBindingService()
    bindings: list[PublicTargetBinding] = []
    if scenario.scope.bound_targets:
        matches, existing_by_subject = _build_catalog_matches(
            scenario,
            thread_id=thread_id,
            task_id=task_id,
        )
        bindings = await binding_service.build_and_persist_records(
            matches,
            thread_id=thread_id,
            task_id=task_id,
            existing_by_subject=existing_by_subject,
        )

    generation = 1 if bindings else 0
    turn_scope = TurnScope(
        thread_id=thread_id,
        session_id=session_id,
        scope_kind="target_bindings" if bindings else "zero_scope",
        bindings=bindings,
        toolset_generation=generation,
        resolution_policy=scenario.scope.turn_scope.resolution_policy,
        automation_mode=scenario.scope.turn_scope.automation_mode,
    )
    context = dict(context_overrides or {})
    context.update(turn_scope.to_thread_context())
    if bindings:
        context.update(
            build_bound_target_scope_context(
                bindings,
                generation=generation,
                active_handle=bindings[0].target_handle,
            )
        )
    if scenario.execution.route_via_router is False:
        context["requested_agent_type"] = _normalize_requested_agent_type(scenario.execution.agent)
    context["turn_scope"] = turn_scope.model_dump(mode="json")
    return context, turn_scope


def load_eval_scenario(scenario_or_path: EvalScenario | str | Path) -> EvalScenario:
    """Return an EvalScenario from an in-memory model or fixture path."""

    if isinstance(scenario_or_path, EvalScenario):
        return scenario_or_path
    return EvalScenario.from_file(scenario_or_path)


def _scenario_runtime_context(scenario: EvalScenario) -> dict[str, Any]:
    provenance = scenario.provenance.model_dump(mode="json")
    return {
        "eval_scenario_id": scenario.id,
        "eval_scenario_name": scenario.name,
        "eval_scenario_provenance": provenance,
        "eval_source_pack": provenance.get("source_pack"),
        "eval_source_pack_version": provenance.get("source_pack_version"),
    }


def _llm_mode_name(mode: Any) -> str:
    value = getattr(mode, "value", mode)
    return str(value)


async def run_full_turn_scenario(
    scenario: EvalScenario,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    redis_client: Any = None,
    target_binding_service: TargetBindingService | None = None,
    context_overrides: dict[str, Any] | None = None,
    turn_processor: Any = None,
    runtime_overrides: EvalRuntimeOverrides | None = None,
    allow_live_llm: bool = False,
) -> EvalFullTurnResult:
    """Run one scenario through the real thread/task orchestration path."""

    if scenario.execution.lane is not ExecutionLane.FULL_TURN:
        raise ValueError("run_full_turn_scenario only supports full_turn scenarios")
    if _llm_mode_name(scenario.execution.llm_mode) == "live" and not allow_live_llm:
        raise PermissionError(
            "Live-model eval scenarios require explicit opt-in via allow_live_llm=True"
        )
    effective_overrides = runtime_overrides or EvalRuntimeOverrides()
    behavior_state = FixtureBehaviorState()
    knowledge_backend = effective_overrides.knowledge_backend or build_fixture_knowledge_backend(
        scenario
    )
    mcp_runtime = effective_overrides.mcp_runtime or build_fixture_mcp_runtime(
        scenario,
        state=behavior_state,
    )
    tool_runtime = effective_overrides.tool_runtime or build_fixture_tool_runtime(
        scenario,
        state=behavior_state,
    )
    mcp_servers = effective_overrides.mcp_servers
    if mcp_servers is None and mcp_runtime is not None:
        mcp_servers = mcp_runtime.get_server_configs()
    with eval_injection_scope(
        knowledge_backend=knowledge_backend,
        mcp_servers=mcp_servers,
        mcp_runtime=mcp_runtime,
        tool_runtime=tool_runtime,
    ):
        thread_manager = ThreadManager(redis_client=redis_client)
        task_manager = TaskManager(redis_client=redis_client)
        initial_context = await _build_initial_context(
            query=scenario.execution.query,
            base_context={
                **_scenario_runtime_context(scenario),
                **dict(context_overrides or {}),
            },
        )
        thread_id = await thread_manager.create_thread(
            user_id=user_id,
            session_id=session_id,
            initial_context=initial_context,
        )
        await thread_manager.set_thread_subject(thread_id, scenario.execution.query)

        task_id = await task_manager.create_task(
            thread_id=thread_id,
            user_id=user_id,
            subject=scenario.execution.query,
        )
        effective_session_id = session_id or thread_id
        turn_context, _ = await build_full_turn_context(
            scenario,
            thread_id=thread_id,
            task_id=task_id,
            session_id=effective_session_id,
            target_binding_service=target_binding_service,
            context_overrides=initial_context,
        )
        await thread_manager.update_thread_context(thread_id, turn_context, merge=False)

        active_turn_processor = turn_processor or _default_turn_processor
        turn_result = await active_turn_processor(
            thread_id=thread_id,
            message=scenario.execution.query,
            context=turn_context,
            task_id=task_id,
            redis_client=redis_client,
        )

        task_state = await task_manager.get_task_state(task_id)
        task_status = None
        if task_state is not None:
            status = getattr(task_state, "status", None)
            task_status = (
                status.value if hasattr(status, "value") else str(status) if status else None
            )

        return EvalFullTurnResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            scenario_provenance=scenario.provenance.model_dump(mode="json"),
            execution_lane=scenario.execution.lane,
            thread_id=thread_id,
            task_id=task_id,
            task_status=task_status,
            initial_context=initial_context,
            turn_context=turn_context,
            turn_result=turn_result,
        )


class EvalRuntime:
    """Minimal runtime wrapper for executing full-turn eval scenarios."""

    def __init__(
        self,
        *,
        redis_client: Any = None,
        target_binding_service: TargetBindingService | None = None,
        session_id: str | None = None,
        runtime_overrides: EvalRuntimeOverrides | None = None,
        allow_live_llm: bool = False,
    ) -> None:
        self._redis_client = redis_client
        self._target_binding_service = target_binding_service
        self._session_id = session_id
        self._runtime_overrides = runtime_overrides
        self._allow_live_llm = allow_live_llm

    async def run(
        self,
        scenario_or_path: EvalScenario | str | Path,
        *,
        user_id: str | None = None,
        extra_context: dict[str, Any] | None = None,
        session_id: str | None = None,
        runtime_overrides: EvalRuntimeOverrides | None = None,
        allow_live_llm: bool | None = None,
    ) -> EvalRunResult:
        """Load and execute one eval scenario through the full-turn harness."""

        scenario = load_eval_scenario(scenario_or_path)
        if scenario.execution.lane is not ExecutionLane.FULL_TURN:
            raise NotImplementedError("agent_only eval runs are owned by a separate Phase 1 task")
        run_kwargs: dict[str, Any] = {
            "user_id": user_id,
            "session_id": session_id or self._session_id,
            "redis_client": self._redis_client,
            "target_binding_service": self._target_binding_service,
            "context_overrides": extra_context,
            "runtime_overrides": runtime_overrides or self._runtime_overrides,
        }
        effective_allow_live_llm = (
            self._allow_live_llm if allow_live_llm is None else allow_live_llm
        )
        if effective_allow_live_llm:
            run_kwargs["allow_live_llm"] = True
        return await run_full_turn_scenario(
            scenario,
            **run_kwargs,
        )


__all__ = [
    "EvalFullTurnResult",
    "EvalRunResult",
    "EvalRuntime",
    "build_full_turn_context",
    "load_eval_scenario",
    "run_full_turn_scenario",
]

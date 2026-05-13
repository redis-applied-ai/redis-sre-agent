"""Full-turn eval harness around the production turn entrypoint."""

from __future__ import annotations

from contextlib import ExitStack, nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field

from redis_sre_agent.agent.models import AgentResponse
from redis_sre_agent.core.targets import (
    TargetCatalogDoc,
    _confidence_from_score,
    _parse_query_hints,
    _score_target_doc,
    build_bound_target_scope_context,
    build_public_match_from_doc,
)
from redis_sre_agent.core.tasks import TaskManager
from redis_sre_agent.core.threads import ThreadManager, _build_initial_context
from redis_sre_agent.core.turn_scope import TurnScope
from redis_sre_agent.evaluation.fake_mcp import build_fixture_mcp_runtime
from redis_sre_agent.evaluation.fake_memory import inject_memory_fixture
from redis_sre_agent.evaluation.injection import eval_injection_scope
from redis_sre_agent.evaluation.knowledge_backend import build_fixture_knowledge_backend
from redis_sre_agent.evaluation.runtime_overrides import (
    EvalRuntimeOverrides,
)
from redis_sre_agent.evaluation.scenarios import EvalScenario, ExecutionLane
from redis_sre_agent.evaluation.tool_runtime import FixtureBehaviorState, build_fixture_tool_runtime
from redis_sre_agent.targets import TargetBindingService
from redis_sre_agent.targets.contracts import (
    DiscoveryCandidate,
    DiscoveryRequest,
    DiscoveryResponse,
    PublicTargetBinding,
    PublicTargetMatch,
)
from redis_sre_agent.targets.registry import (
    TargetIntegrationRegistry,
    get_target_integration_registry,
)

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

    from redis_sre_agent.core.docket_tasks import _process_agent_turn_impl

    return await _process_agent_turn_impl(**kwargs)


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


def _infer_eval_instance_type(entry: Any) -> str:
    """Infer a synthetic Redis instance type from public target metadata."""

    deployment = (
        str(
            entry.public_metadata.get("deployment")
            or entry.public_metadata.get("target_type")
            or entry.cluster_type
            or ""
        )
        .strip()
        .lower()
    )
    if deployment in {"redis_enterprise", "enterprise"}:
        return "redis_enterprise"
    if deployment in {"redis_cloud", "cloud"}:
        return "redis_cloud"
    if deployment in {"oss_cluster", "cluster"}:
        return "oss_cluster"
    return "oss_single"


def _build_eval_target_private_ref(entry: Any, *, binding_subject: str) -> dict[str, Any]:
    """Attach synthetic private target seed data for eval-only target bindings."""

    environment = str(entry.public_metadata.get("environment") or "test")
    if entry.kind == "cluster":
        cluster_type = str(entry.cluster_type or "redis_enterprise").strip().lower()
        seed: dict[str, Any] = {
            "seed_kind": "cluster",
            "id": binding_subject,
            "name": entry.display_name,
            "cluster_type": cluster_type,
            "environment": environment,
            "description": f"Eval target seed for {entry.display_name}",
        }
        if cluster_type == "redis_enterprise":
            seed.update(
                {
                    "admin_url": "https://eval-target.invalid:9443",
                    "admin_username": "eval",
                    "admin_password": "eval-password",
                }
            )
        return {"target_kind": entry.kind, "eval_target_seed": seed}

    instance_type = _infer_eval_instance_type(entry)
    seed = {
        "seed_kind": "instance",
        "id": binding_subject,
        "name": entry.display_name,
        "connection_url": "redis://eval-target.invalid:6379/0",
        "environment": environment,
        "usage": "custom",
        "description": f"Eval target seed for {entry.display_name}",
        "instance_type": instance_type,
    }
    if instance_type == "redis_enterprise":
        seed.update(
            {
                "cluster_id": binding_subject,
                "admin_url": "https://eval-target.invalid:9443",
                "admin_username": "eval",
                "admin_password": "eval-password",
            }
        )
    elif instance_type == "redis_cloud":
        seed.update(
            {
                "redis_cloud_subscription_id": 1,
                "redis_cloud_database_id": 1,
                "redis_cloud_subscription_type": "pro",
                "redis_cloud_database_name": entry.display_name,
            }
        )
    return {"target_kind": entry.kind, "eval_target_seed": seed}


def _build_catalog_matches(
    scenario: EvalScenario,
    *,
    thread_id: str,
    task_id: str,
) -> tuple[list[DiscoveryCandidate], dict[tuple[str, str], PublicTargetBinding]]:
    catalog_by_handle = {entry.handle: entry for entry in scenario.scope.target_catalog}
    matches: list[DiscoveryCandidate] = []
    existing_by_subject: dict[tuple[str, str], PublicTargetBinding] = {}

    for handle in scenario.scope.bound_targets:
        entry = catalog_by_handle[handle]
        binding_subject = entry.resource_id or entry.handle
        public_metadata = dict(entry.public_metadata)
        environment = public_metadata.get("environment")
        target_type = public_metadata.get("target_type") or entry.cluster_type
        public_match = PublicTargetMatch(
            target_kind=entry.kind,
            display_name=entry.display_name,
            environment=str(environment) if environment else None,
            target_type=str(target_type) if target_type else None,
            capabilities=list(entry.capabilities),
            confidence=1.0,
            public_metadata=public_metadata,
            resource_id=entry.resource_id,
        )
        matches.append(
            DiscoveryCandidate.from_public_match(
                public_match,
                binding_subject=binding_subject,
                private_binding_ref=_build_eval_target_private_ref(
                    entry,
                    binding_subject=binding_subject,
                ),
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


def _build_eval_target_catalog_doc(entry: Any) -> TargetCatalogDoc:
    """Translate a scenario target entry into a safe discovery document."""

    public_metadata = dict(entry.public_metadata or {})
    target_type = public_metadata.get("target_type") or entry.cluster_type
    aliases = public_metadata.get("aliases") or public_metadata.get("search_aliases") or []
    if not isinstance(aliases, list):
        aliases = [aliases]

    search_parts = [
        entry.display_name,
        public_metadata.get("environment"),
        public_metadata.get("usage"),
        public_metadata.get("status"),
        public_metadata.get("description"),
        public_metadata.get("notes"),
        public_metadata.get("monitoring_identifier"),
        public_metadata.get("logging_identifier"),
        *(str(alias) for alias in aliases if alias not in (None, "")),
    ]
    search_text = " ".join(str(part) for part in search_parts if part not in (None, ""))

    return TargetCatalogDoc(
        target_id=entry.handle,
        target_kind=entry.kind,
        resource_id=entry.resource_id or entry.handle,
        display_name=entry.display_name,
        name=entry.display_name,
        environment=public_metadata.get("environment"),
        status=public_metadata.get("status"),
        target_type=str(target_type) if target_type else None,
        usage=public_metadata.get("usage"),
        description=public_metadata.get("description"),
        notes=public_metadata.get("notes"),
        repo_url=public_metadata.get("repo_url"),
        repo_slug=public_metadata.get("repo_slug"),
        monitoring_identifier=public_metadata.get("monitoring_identifier"),
        logging_identifier=public_metadata.get("logging_identifier"),
        cluster_id=public_metadata.get("cluster_id"),
        redis_cloud_subscription_id=public_metadata.get("redis_cloud_subscription_id"),
        redis_cloud_database_id=public_metadata.get("redis_cloud_database_id"),
        redis_cloud_database_name=public_metadata.get("redis_cloud_database_name"),
        search_text=search_text,
        search_aliases=[str(alias) for alias in aliases if alias not in (None, "")],
        capabilities=list(entry.capabilities or []),
    )


class _EvalTargetCatalogDiscoveryBackend:
    """Scenario-backed discovery backend for eval runs."""

    backend_name = "eval_target_catalog"

    def __init__(
        self,
        *,
        scenario: EvalScenario,
        binding_strategy: str,
    ) -> None:
        self._scenario = scenario
        self._binding_strategy = binding_strategy
        self._catalog_docs = {
            entry.handle: _build_eval_target_catalog_doc(entry)
            for entry in scenario.scope.target_catalog
        }

    async def resolve(self, request: DiscoveryRequest) -> DiscoveryResponse:
        ranked: list[DiscoveryCandidate] = []
        hints = _parse_query_hints(request.query)

        for entry in self._scenario.scope.target_catalog:
            doc = self._catalog_docs[entry.handle]
            score, reasons = _score_target_doc(
                request.query,
                doc,
                preferred_capabilities=request.preferred_capabilities,
                hints=hints,
            )
            if score < 2.5:
                continue

            public_match = build_public_match_from_doc(
                doc,
                confidence=_confidence_from_score(score),
                match_reasons=reasons,
                score=score,
            )
            ranked.append(
                DiscoveryCandidate(
                    public_match=public_match,
                    binding_strategy=self._binding_strategy,
                    binding_subject=doc.resource_id,
                    private_binding_ref=_build_eval_target_private_ref(
                        entry,
                        binding_subject=doc.resource_id,
                    ),
                    discovery_backend=self.backend_name,
                    score=score,
                    confidence=public_match.confidence,
                )
            )

        ranked.sort(key=lambda candidate: (candidate.score, candidate.confidence), reverse=True)
        limited = ranked[: max(1, min(request.max_results, 10))]
        if not limited:
            return DiscoveryResponse(status="no_match")

        top = limited[0]
        if request.allow_multiple:
            selected = [
                candidate for candidate in limited if candidate.score >= max(3.0, top.score - 1.5)
            ][: min(3, request.max_results)]
            return DiscoveryResponse(
                status="resolved",
                clarification_required=False,
                matches=[candidate.public_match for candidate in limited],
                selected_matches=selected,
            )

        clarification_required = len(limited) > 1 and limited[1].score >= top.score - 0.75
        selected = limited[: min(3, request.max_results)] if clarification_required else [top]
        return DiscoveryResponse(
            status="clarification_required" if clarification_required else "resolved",
            clarification_required=clarification_required,
            matches=[candidate.public_match for candidate in limited],
            selected_matches=selected,
        )


def _build_eval_target_catalog_docs(scenario: EvalScenario) -> list[TargetCatalogDoc]:
    """Return scenario-backed catalog docs for eval discovery and inventory tools."""

    return [_build_eval_target_catalog_doc(entry) for entry in scenario.scope.target_catalog]


def _build_eval_target_registry(scenario: EvalScenario) -> TargetIntegrationRegistry | None:
    """Install a scenario-backed discovery backend while reusing production binders."""

    if not scenario.scope.target_catalog:
        return None

    base_registry = get_target_integration_registry()
    registry = TargetIntegrationRegistry(
        default_discovery_backend=_EvalTargetCatalogDiscoveryBackend.backend_name,
        default_binding_strategy=base_registry.default_binding_strategy,
    )
    registry._discovery_backends.update(dict(base_registry._discovery_backends))
    registry._binding_strategies.update(dict(base_registry._binding_strategies))
    registry._client_factories.update(dict(base_registry._client_factories))
    registry.register_discovery_backend(
        _EvalTargetCatalogDiscoveryBackend(
            scenario=scenario,
            binding_strategy=registry.default_binding_strategy,
        )
    )
    return registry


def _target_registry_override_scope(
    scenario: EvalScenario,
) -> ExitStack | Any:
    """Patch target-registry call sites for discovery-first eval scenarios."""

    registry = _build_eval_target_registry(scenario)
    if registry is None:
        return nullcontext()

    catalog_docs = _build_eval_target_catalog_docs(scenario)

    async def _get_eval_target_catalog(*, user_id: str | None = None) -> list[TargetCatalogDoc]:
        if not user_id:
            return list(catalog_docs)
        return [doc for doc in catalog_docs if doc.user_id in {None, "", user_id}]

    stack = ExitStack()
    for target in (
        "redis_sre_agent.targets.services.get_target_integration_registry",
        "redis_sre_agent.tools.manager.get_target_integration_registry",
        "redis_sre_agent.core.targets.get_target_integration_registry",
    ):
        stack.enter_context(patch(target, return_value=registry))
    stack.enter_context(
        patch("redis_sre_agent.core.targets.get_target_catalog", new=_get_eval_target_catalog)
    )
    return stack


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


def _enrich_turn_result_from_trace(
    turn_result: dict[str, Any],
    message_trace: dict[str, Any] | None,
) -> dict[str, Any]:
    """Backfill tool/citation evidence from the persisted assistant message trace."""

    if not message_trace:
        return turn_result

    enriched = dict(turn_result)
    tool_envelopes = list(message_trace.get("tool_envelopes") or [])
    if tool_envelopes and not enriched.get("tool_envelopes"):
        enriched["tool_envelopes"] = tool_envelopes
    if tool_envelopes and not enriched.get("search_results"):
        enriched["search_results"] = AgentResponse(
            response=str(enriched.get("response") or ""),
            tool_envelopes=tool_envelopes,
        ).search_results
    return enriched


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
    if mcp_servers is None:
        mcp_servers = mcp_runtime.get_server_configs() if mcp_runtime is not None else {}
    async with inject_memory_fixture(scenario):
        with _target_registry_override_scope(scenario):
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
                assistant_message_id = str(turn_result.get("message_id") or "").strip()
                if assistant_message_id:
                    message_trace = await thread_manager.get_message_trace(assistant_message_id)
                    turn_result = _enrich_turn_result_from_trace(turn_result, message_trace)

                task_state = await task_manager.get_task_state(task_id)
                task_status = None
                if task_state is not None:
                    status = getattr(task_state, "status", None)
                    task_status = (
                        status.value
                        if hasattr(status, "value")
                        else str(status)
                        if status
                        else None
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

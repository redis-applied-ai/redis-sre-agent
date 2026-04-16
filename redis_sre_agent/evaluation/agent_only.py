"""Direct agent runtime helpers for narrow eval scenarios."""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol, Sequence

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict, Field

from redis_sre_agent.agent.chat_agent import get_chat_agent
from redis_sre_agent.agent.knowledge_agent import get_knowledge_agent
from redis_sre_agent.agent.langgraph_agent import get_sre_agent
from redis_sre_agent.core.turn_scope import TurnScope
from redis_sre_agent.evaluation.scenarios import EvalScenario, ExecutionLane
from redis_sre_agent.targets.contracts import PublicTargetBinding


class SupportsProcessQuery(Protocol):
    """Agent interface used by the eval agent_only harness."""

    async def process_query(
        self,
        query: str,
        session_id: str,
        user_id: Optional[str],
        max_iterations: int = 10,
        context: Optional[dict[str, Any]] = None,
        progress_emitter: Any = None,
        conversation_history: Optional[Sequence[BaseMessage]] = None,
    ) -> Any: ...


AgentFactory = Callable[[], SupportsProcessQuery]

_AGENT_ALIASES = {
    "chat": "redis_chat",
    "knowledge": "knowledge_only",
    "knowledge_only": "knowledge_only",
    "redis_chat": "redis_chat",
    "redis_triage": "redis_triage",
    "triage": "redis_triage",
}


def _default_agent_factories() -> dict[str, AgentFactory]:
    return {
        "redis_chat": get_chat_agent,
        "knowledge_only": get_knowledge_agent,
        "redis_triage": get_sre_agent,
    }


def _agent_iteration_budget(scenario: EvalScenario) -> int:
    """Reserve one final synthesis turn beyond the tool-step budget.

    Eval scenarios define `max_tool_steps`, but the direct agent entrypoints take
    `max_iterations`, which counts LLM turns. Agent-only live evals need one
    extra turn after the last tool call so the model can produce a final answer.
    """

    return int(scenario.execution.max_tool_steps) + 1


def _normalize_agent_name(agent_name: str) -> str:
    normalized = str(agent_name or "").strip().lower()
    if not normalized:
        raise ValueError("agent_only scenarios must set execution.agent")
    return _AGENT_ALIASES.get(normalized, normalized)


def _build_bound_target_bindings(
    scenario: EvalScenario,
    *,
    thread_id: str,
) -> list[PublicTargetBinding]:
    catalog_by_handle = {entry.handle: entry for entry in scenario.scope.target_catalog}
    bindings: list[PublicTargetBinding] = []
    for handle in scenario.scope.bound_targets:
        entry = catalog_by_handle[handle]
        bindings.append(
            PublicTargetBinding(
                target_handle=entry.handle,
                target_kind=entry.kind,
                display_name=entry.display_name,
                capabilities=list(entry.capabilities),
                public_metadata=dict(entry.public_metadata),
                resource_id=entry.resource_id,
                thread_id=thread_id,
            )
        )
    return bindings


def build_agent_only_context(
    scenario: EvalScenario,
    *,
    session_id: str,
    thread_id: str | None = None,
    base_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compile scenario scope into the direct-agent context payload."""

    effective_thread_id = thread_id or session_id
    scope = TurnScope(
        thread_id=effective_thread_id,
        session_id=session_id,
        scope_kind="target_bindings" if scenario.scope.bound_targets else "zero_scope",
        bindings=_build_bound_target_bindings(scenario, thread_id=effective_thread_id),
        resolution_policy=scenario.scope.turn_scope.resolution_policy,
        automation_mode=scenario.scope.turn_scope.automation_mode,
    )
    context = dict(base_context or {})
    context.update(scope.to_thread_context())
    context["turn_scope"] = scope.model_dump(mode="json")
    return context


class AgentOnlyHarnessResult(BaseModel):
    """Captured output from one direct agent_only eval run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_name: str
    session_id: str
    context: dict[str, Any] = Field(default_factory=dict)
    response: Any


def resolve_agent_only_factory(
    agent_name: str,
    *,
    agent_factories: Optional[dict[str, AgentFactory]] = None,
) -> AgentFactory:
    """Resolve an agent_only scenario agent name to a factory."""

    normalized_name = _normalize_agent_name(agent_name)
    registry = dict(_default_agent_factories())
    if agent_factories:
        registry.update(agent_factories)
    try:
        return registry[normalized_name]
    except KeyError as exc:
        available = ", ".join(sorted(registry))
        raise KeyError(
            f"Unsupported agent_only agent '{agent_name}'. Available agents: {available}"
        ) from exc


async def run_agent_only_scenario(
    scenario: EvalScenario,
    *,
    session_id: str,
    user_id: str | None,
    thread_id: str | None = None,
    base_context: Optional[dict[str, Any]] = None,
    progress_emitter: Any = None,
    conversation_history: Optional[Sequence[BaseMessage]] = None,
    agent_factories: Optional[dict[str, AgentFactory]] = None,
) -> AgentOnlyHarnessResult:
    """Execute an eval scenario through a direct agent process_query path."""

    if scenario.execution.lane is not ExecutionLane.AGENT_ONLY:
        raise ValueError("run_agent_only_scenario only supports agent_only scenarios")

    agent_name = _normalize_agent_name(scenario.execution.agent or "")
    factory = resolve_agent_only_factory(agent_name, agent_factories=agent_factories)
    context = build_agent_only_context(
        scenario,
        session_id=session_id,
        thread_id=thread_id,
        base_context=base_context,
    )
    agent = factory()
    response = await agent.process_query(
        query=scenario.execution.query,
        session_id=session_id,
        user_id=user_id,
        max_iterations=_agent_iteration_budget(scenario),
        context=context,
        progress_emitter=progress_emitter,
        conversation_history=list(conversation_history or []) or None,
    )
    return AgentOnlyHarnessResult(
        agent_name=agent_name,
        session_id=session_id,
        context=context,
        response=response,
    )


__all__ = [
    "AgentOnlyHarnessResult",
    "build_agent_only_context",
    "resolve_agent_only_factory",
    "run_agent_only_scenario",
]

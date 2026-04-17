from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from redis_sre_agent.evaluation.agent_only import (
    build_agent_only_context,
    resolve_agent_only_factory,
    run_agent_only_scenario,
)
from redis_sre_agent.evaluation.scenarios import EvalScenario


def _agent_only_payload() -> dict:
    return {
        "id": "enterprise-node-maintenance",
        "name": "Redis Enterprise node maintenance incident",
        "provenance": {
            "source_kind": "redis_docs",
            "source_pack": "redis-docs-curated",
            "source_pack_version": "2026-04-01",
            "golden": {
                "expectation_basis": "human_from_docs",
                "review_status": "approved",
            },
        },
        "execution": {
            "lane": "agent_only",
            "agent": "redis_triage",
            "query": "Investigate failovers on the prod enterprise cluster.",
            "max_tool_steps": 6,
            "llm_mode": "replay",
        },
        "scope": {
            "turn_scope": {
                "resolution_policy": "require_target",
                "automation_mode": "interactive",
            },
            "target_catalog": [
                {
                    "handle": "tgt_cluster_prod_east",
                    "kind": "cluster",
                    "resource_id": "cluster-prod-east",
                    "display_name": "prod-east cluster",
                    "capabilities": ["admin", "metrics"],
                    "public_metadata": {"environment": "production"},
                }
            ],
            "bound_targets": ["tgt_cluster_prod_east"],
        },
    }


class _FakeAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def process_query(
        self,
        query: str,
        session_id: str,
        user_id: str | None,
        max_iterations: int = 10,
        context: dict | None = None,
        progress_emitter=None,
        conversation_history=None,
    ) -> SimpleNamespace:
        self.calls.append(
            {
                "query": query,
                "session_id": session_id,
                "user_id": user_id,
                "max_iterations": max_iterations,
                "context": context,
                "progress_emitter": progress_emitter,
                "conversation_history": conversation_history,
            }
        )
        return SimpleNamespace(response="ok", tool_envelopes=[])


def test_build_agent_only_context_compiles_scope_into_thread_context():
    scenario = EvalScenario.model_validate(_agent_only_payload())

    context = build_agent_only_context(
        scenario,
        session_id="sess-1",
        thread_id="thread-1",
        base_context={"extra": "value"},
    )

    assert context["extra"] == "value"
    assert context["thread_id"] == "thread-1"
    assert context["session_id"] == "sess-1"
    assert context["resolution_policy"] == "require_target"
    assert context["attached_target_handles"] == ["tgt_cluster_prod_east"]
    assert context["target_bindings"][0]["display_name"] == "prod-east cluster"
    assert context["turn_scope"]["scope_kind"] == "target_bindings"


@pytest.mark.asyncio
async def test_run_agent_only_scenario_calls_selected_agent_with_prebuilt_context():
    scenario = EvalScenario.model_validate(_agent_only_payload())
    fake_agent = _FakeAgent()
    history = [HumanMessage(content="Previous turn")]
    progress_emitter = object()

    result = await run_agent_only_scenario(
        scenario,
        session_id="sess-2",
        thread_id="thread-2",
        user_id="user-1",
        base_context={"task_id": "task-1"},
        progress_emitter=progress_emitter,
        conversation_history=history,
        agent_factories={"redis_triage": lambda: fake_agent},
    )

    assert result.agent_name == "redis_triage"
    assert result.response.response == "ok"
    assert result.context["task_id"] == "task-1"
    assert result.context["tool_call_budget_override"] == 7
    assert result.context["turn_scope"]["thread_id"] == "thread-2"
    assert fake_agent.calls == [
        {
            "query": "Investigate failovers on the prod enterprise cluster.",
            "session_id": "sess-2",
            "user_id": "user-1",
            "max_iterations": 7,
            "context": result.context,
            "progress_emitter": progress_emitter,
            "conversation_history": history,
        }
    ]


@pytest.mark.asyncio
async def test_run_agent_only_scenario_rejects_non_agent_only_lane():
    payload = _agent_only_payload()
    payload["execution"]["lane"] = "full_turn"
    payload["execution"]["route_via_router"] = True
    scenario = EvalScenario.model_validate(payload)

    with pytest.raises(ValueError, match="only supports agent_only scenarios"):
        await run_agent_only_scenario(
            scenario,
            session_id="sess-3",
            user_id="user-1",
            agent_factories={"redis_triage": lambda: _FakeAgent()},
        )


def test_resolve_agent_only_factory_accepts_agent_aliases():
    registry = {
        "redis_chat": lambda: _FakeAgent(),
        "knowledge_only": lambda: _FakeAgent(),
        "redis_triage": lambda: _FakeAgent(),
    }

    assert resolve_agent_only_factory("chat", agent_factories=registry) is registry["redis_chat"]
    assert (
        resolve_agent_only_factory("knowledge", agent_factories=registry)
        is registry["knowledge_only"]
    )

    with pytest.raises(KeyError, match="Unsupported agent_only agent"):
        resolve_agent_only_factory("unknown-agent", agent_factories=registry)

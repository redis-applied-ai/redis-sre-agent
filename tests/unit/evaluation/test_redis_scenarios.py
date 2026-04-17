import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from redis_sre_agent.evaluation.fixture_layout import (
    golden_assertions_path,
    golden_expected_response_path,
    golden_metadata_path,
    scenario_manifest_path,
)
from redis_sre_agent.evaluation.knowledge_backend import build_fixture_knowledge_backend
from redis_sre_agent.evaluation.runtime import build_full_turn_context
from redis_sre_agent.evaluation.scenarios import EvalScenario, ExecutionLane
from redis_sre_agent.targets.contracts import PublicTargetBinding

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_committed_scenario(scenario_id: str) -> EvalScenario:
    return EvalScenario.from_file(REPO_ROOT / scenario_manifest_path("redis", scenario_id))


def _binding(
    *,
    handle: str,
    kind: str,
    display_name: str,
    resource_id: str,
    capabilities: list[str],
    public_metadata: dict[str, str],
) -> PublicTargetBinding:
    return PublicTargetBinding(
        target_handle=handle,
        target_kind=kind,
        display_name=display_name,
        capabilities=capabilities,
        public_metadata=public_metadata,
        thread_id="thread-123",
        task_id="task-123",
        resource_id=resource_id,
    )


def test_committed_redis_scenarios_load_with_goldens_and_refs():
    memory = _load_committed_scenario("memory-pressure-oss")
    slowlog = _load_committed_scenario("slowlog-anti-pattern")
    maintenance = _load_committed_scenario("enterprise-maintenance-mode")
    cluster = _load_committed_scenario("enterprise-cluster-health-vs-info-misread")

    assert memory.execution.lane is ExecutionLane.FULL_TURN
    assert memory.execution.agent == "redis_chat"
    assert memory.scope.bound_targets == ["tgt_instance_orders_cache"]
    assert memory.resolve_fixture_path("fixtures/tools/info-memory.json").exists()

    assert slowlog.execution.lane is ExecutionLane.FULL_TURN
    assert slowlog.execution.agent == "redis_chat"
    assert slowlog.scope.bound_targets == ["tgt_instance_sessions_cache"]
    assert slowlog.resolve_fixture_path("fixtures/tools/slowlog.json").exists()

    assert maintenance.execution.lane is ExecutionLane.FULL_TURN
    assert maintenance.execution.agent == "redis_triage"
    assert maintenance.scope.bound_targets == ["tgt_cluster_payments_east"]
    assert maintenance.resolve_fixture_path("fixtures/tools/list-nodes.json").exists()

    assert cluster.execution.lane is ExecutionLane.FULL_TURN
    assert cluster.execution.agent == "redis_triage"
    assert cluster.scope.bound_targets == ["tgt_cluster_checkout_global"]
    assert cluster.resolve_fixture_path("fixtures/tools/list-databases.json").exists()

    for scenario_id, scenario in (
        ("memory-pressure-oss", memory),
        ("slowlog-anti-pattern", slowlog),
        ("enterprise-maintenance-mode", maintenance),
        ("enterprise-cluster-health-vs-info-misread", cluster),
    ):
        metadata = yaml.safe_load(
            (REPO_ROOT / golden_metadata_path("redis", scenario_id)).read_text(encoding="utf-8")
        )
        expected = (REPO_ROOT / golden_expected_response_path("redis", scenario_id)).read_text(
            encoding="utf-8"
        )
        assertions = json.loads(
            (REPO_ROOT / golden_assertions_path("redis", scenario_id)).read_text(encoding="utf-8")
        )

        assert metadata["scenario_id"] == scenario.id
        assert metadata["review_status"] == scenario.provenance.golden.review_status.value
        assert metadata["source_pack"] == scenario.provenance.source_pack
        assert metadata["source_pack_version"] == scenario.provenance.source_pack_version
        assert expected.strip()
        assert assertions == scenario.expectations.model_dump(mode="json", exclude_none=True)


@pytest.mark.asyncio
async def test_committed_redis_scenarios_build_full_turn_context_for_instance_and_cluster():
    memory = _load_committed_scenario("memory-pressure-oss")
    maintenance = _load_committed_scenario("enterprise-maintenance-mode")

    memory_binding_service = AsyncMock()
    memory_binding_service.build_and_persist_records.return_value = [
        _binding(
            handle="tgt_instance_orders_cache",
            kind="instance",
            display_name="prod orders cache",
            resource_id="redis-prod-orders",
            capabilities=["diagnostics", "knowledge"],
            public_metadata={"environment": "production", "deployment": "oss"},
        )
    ]
    maintenance_binding_service = AsyncMock()
    maintenance_binding_service.build_and_persist_records.return_value = [
        _binding(
            handle="tgt_cluster_payments_east",
            kind="cluster",
            display_name="payments-east enterprise cluster",
            resource_id="re-cluster-payments-east",
            capabilities=["admin", "diagnostics", "knowledge"],
            public_metadata={"environment": "production", "deployment": "redis_enterprise"},
        )
    ]

    memory_context, memory_scope = await build_full_turn_context(
        memory,
        thread_id="thread-memory",
        task_id="task-memory",
        session_id="session-memory",
        target_binding_service=memory_binding_service,
    )
    maintenance_context, maintenance_scope = await build_full_turn_context(
        maintenance,
        thread_id="thread-maintenance",
        task_id="task-maintenance",
        session_id="session-maintenance",
        target_binding_service=maintenance_binding_service,
    )

    assert memory_context["requested_agent_type"] == "chat"
    assert memory_context["attached_target_handles"] == ["tgt_instance_orders_cache"]
    assert memory_scope.scope_kind == "target_bindings"

    assert maintenance_context["requested_agent_type"] == "triage"
    assert maintenance_context["attached_target_handles"] == ["tgt_cluster_payments_east"]
    assert maintenance_scope.scope_kind == "target_bindings"


@pytest.mark.asyncio
async def test_committed_redis_corpus_serves_docs_skills_and_tickets():
    memory = _load_committed_scenario("memory-pressure-oss")
    maintenance = _load_committed_scenario("enterprise-maintenance-mode")
    cluster = _load_committed_scenario("enterprise-cluster-health-vs-info-misread")

    memory_backend = build_fixture_knowledge_backend(memory)
    maintenance_backend = build_fixture_knowledge_backend(maintenance)
    cluster_backend = build_fixture_knowledge_backend(cluster)

    memory_runbook = await memory_backend.get_all_document_fragments(
        document_hash="memory-pressure-runbook",
        version="latest",
    )
    maintenance_skill = await maintenance_backend.get_skill(
        skill_name="redis-enterprise-maintenance-checklist",
        version="latest",
    )
    maintenance_ticket = await maintenance_backend.search_support_tickets(
        query="RET-5032",
        version="latest",
    )
    cluster_runbook = await cluster_backend.get_all_document_fragments(
        document_hash="cluster-health-triage",
        version="latest",
    )

    assert memory_runbook["document_hash"] == "memory-pressure-runbook"
    assert maintenance_skill["skill_name"] == "redis-enterprise-maintenance-checklist"
    assert maintenance_ticket["tickets"][0]["ticket_id"] == "RET-5032"
    assert cluster_runbook["document_hash"] == "cluster-health-triage"

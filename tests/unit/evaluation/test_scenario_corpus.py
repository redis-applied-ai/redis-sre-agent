import json

import pytest
import yaml

from redis_sre_agent.agent.knowledge_context import build_startup_knowledge_context
from redis_sre_agent.evaluation.fixture_layout import (
    golden_assertions_path,
    golden_expected_response_path,
    golden_metadata_path,
    scenario_manifest_path,
)
from redis_sre_agent.evaluation.knowledge_backend import build_fixture_knowledge_backend
from redis_sre_agent.evaluation.scenarios import EvalScenario, ExecutionLane, KnowledgeMode

_KNOWLEDGE_SCENARIOS = [
    (
        "disabled-live-access-handoff",
        KnowledgeMode.DISABLED,
        [],
    ),
    (
        "startup-only-maintenance-checklist",
        KnowledgeMode.STARTUP_ONLY,
        ["maintenance-mode-overview", "redis-enterprise-maintenance-checklist"],
    ),
    (
        "retrieval-only-ticket-guidance",
        KnowledgeMode.RETRIEVAL_ONLY,
        ["maintenance-mode-guidance", "redis-enterprise-maintenance-checklist", "RET-5032"],
    ),
    (
        "full-memory-evidence-following",
        KnowledgeMode.FULL,
        ["memory-pressure-runbook", "evidence-first-triage"],
    ),
]


@pytest.mark.parametrize(
    ("scenario_name", "expected_mode", "expected_sources"),
    _KNOWLEDGE_SCENARIOS,
)
def test_knowledge_ablation_scenarios_load_from_eval_tree(
    scenario_name: str,
    expected_mode: KnowledgeMode,
    expected_sources: list[str],
):
    scenario_path = scenario_manifest_path("knowledge", scenario_name)

    assert scenario_path.exists()

    scenario = EvalScenario.from_file(scenario_path)

    assert scenario.id == f"knowledge/{scenario_name}"
    assert scenario.execution.lane is ExecutionLane.AGENT_ONLY
    assert scenario.execution.agent == "knowledge"
    assert scenario.knowledge.mode is expected_mode
    assert scenario.expectations.required_sources == expected_sources
    assert scenario.source_path == scenario_path.resolve()


def test_knowledge_ablation_scenarios_cover_all_declared_modes():
    scenarios = [
        EvalScenario.from_file(scenario_manifest_path("knowledge", scenario_name))
        for scenario_name, _, _ in _KNOWLEDGE_SCENARIOS
    ]

    assert {scenario.knowledge.mode for scenario in scenarios} == {
        KnowledgeMode.DISABLED,
        KnowledgeMode.STARTUP_ONLY,
        KnowledgeMode.RETRIEVAL_ONLY,
        KnowledgeMode.FULL,
    }


@pytest.mark.asyncio
async def test_startup_only_knowledge_scenario_materializes_pinned_doc_and_skill():
    scenario = EvalScenario.from_file(
        scenario_manifest_path("knowledge", "startup-only-maintenance-checklist")
    )
    backend = build_fixture_knowledge_backend(scenario)

    startup_context = await build_startup_knowledge_context(
        query=scenario.execution.query,
        version=scenario.knowledge.version,
        available_tools=[],
        knowledge_backend=backend,
    )

    assert "maintenance-mode-overview" in startup_context
    assert "redis-enterprise-maintenance-checklist" in startup_context

    envelopes = {
        envelope["tool_key"]: envelope
        for envelope in getattr(startup_context, "internal_tool_envelopes", [])
    }
    assert set(envelopes) == {
        "knowledge.pinned_context",
        "knowledge.startup_skills_check",
    }
    assert (
        envelopes["knowledge.pinned_context"]["data"]["results"][0]["document_hash"]
        == "maintenance-mode-overview"
    )
    assert (
        envelopes["knowledge.startup_skills_check"]["data"]["results"][0]["document_hash"]
        == "redis-enterprise-maintenance-checklist"
    )


@pytest.mark.asyncio
async def test_retrieval_only_knowledge_scenario_surfaces_doc_skill_and_ticket_guidance():
    scenario = EvalScenario.from_file(
        scenario_manifest_path("knowledge", "retrieval-only-ticket-guidance")
    )
    backend = build_fixture_knowledge_backend(scenario)

    doc_results = await backend.search_knowledge_base(
        query=scenario.execution.query,
        version=scenario.knowledge.version,
    )
    skills = await backend.skills_check(
        query="maintenance checklist",
        version=scenario.knowledge.version,
    )
    tickets = await backend.search_support_tickets(
        query="maintenance failover churn",
        version=scenario.knowledge.version,
    )

    assert "maintenance-mode-guidance" in {
        result["document_hash"] for result in doc_results["results"]
    }
    assert skills["skills"][0]["document_hash"] == "redis-enterprise-maintenance-checklist"
    assert tickets["tickets"][0]["ticket_id"] == "RET-5032"


@pytest.mark.asyncio
async def test_full_knowledge_scenario_combines_pinned_runbook_and_retrieval_skill():
    scenario = EvalScenario.from_file(
        scenario_manifest_path("knowledge", "full-memory-evidence-following")
    )
    backend = build_fixture_knowledge_backend(scenario)

    pinned = await backend.get_pinned_documents(version=scenario.knowledge.version)
    skill = await backend.get_skill(
        skill_name="evidence-first-triage",
        version=scenario.knowledge.version,
    )

    assert "memory-pressure-runbook" in {row["document_hash"] for row in pinned["pinned_documents"]}
    assert skill["skill_name"] == "evidence-first-triage"
    assert "smallest decisive evidence set" in skill["full_content"]


def test_knowledge_ablation_scenarios_ship_goldens_matching_expectations():
    for scenario_name, _, _ in _KNOWLEDGE_SCENARIOS:
        scenario = EvalScenario.from_file(scenario_manifest_path("knowledge", scenario_name))
        metadata_path = golden_metadata_path("knowledge", scenario_name)
        expected_path = golden_expected_response_path("knowledge", scenario_name)
        assertions_path = golden_assertions_path("knowledge", scenario_name)

        assert metadata_path.exists()
        assert expected_path.exists()
        assert assertions_path.exists()

        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        assertions = json.loads(assertions_path.read_text(encoding="utf-8"))

        assert metadata["scenario_id"] == scenario.id
        assert metadata["source_pack"] == scenario.provenance.source_pack
        assert str(metadata["source_pack_version"]) == scenario.provenance.source_pack_version
        assert metadata["review_status"] == scenario.provenance.golden.review_status.value
        assert assertions == scenario.expectations.model_dump(mode="json", exclude_none=True)
        assert expected_path.read_text(encoding="utf-8").strip()

from __future__ import annotations

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
from redis_sre_agent.evaluation.runtime import load_eval_scenario
from redis_sre_agent.evaluation.scenarios import ExecutionLane, KnowledgeMode

KNOWLEDGE_SCENARIOS = [
    ("disabled-no-knowledge-evidence", "knowledge_only", KnowledgeMode.DISABLED, "prompt-core"),
    (
        "startup-pinned-runbook-and-skill",
        "chat",
        KnowledgeMode.STARTUP_ONLY,
        "prompt-core",
    ),
    (
        "retrieval-ticket-guidance",
        "knowledge_only",
        KnowledgeMode.RETRIEVAL_ONLY,
        "redis-docs-curated",
    ),
    (
        "full-maintenance-source-following",
        "knowledge_only",
        KnowledgeMode.FULL,
        "redis-docs-curated",
    ),
]


def _assert_knowledge_fixture_refs_exist(scenario) -> None:
    for ref in [*scenario.knowledge.pinned_documents, *scenario.knowledge.corpus]:
        assert scenario.resolve_fixture_path(ref).exists(), ref


@pytest.mark.parametrize(
    ("scenario_id", "expected_agent", "expected_mode", "expected_source_pack"),
    KNOWLEDGE_SCENARIOS,
)
def test_knowledge_ablation_scenarios_load_from_canonical_eval_tree(
    scenario_id: str,
    expected_agent: str,
    expected_mode: KnowledgeMode,
    expected_source_pack: str,
):
    manifest_path = scenario_manifest_path("knowledge", scenario_id)

    assert manifest_path.exists()

    scenario = load_eval_scenario(manifest_path)

    assert scenario.id == f"knowledge/{scenario_id}"
    assert scenario.execution.lane is ExecutionLane.AGENT_ONLY
    assert scenario.execution.agent == expected_agent
    assert scenario.knowledge.mode is expected_mode
    assert scenario.provenance.source_pack == expected_source_pack
    _assert_knowledge_fixture_refs_exist(scenario)


def test_knowledge_ablation_scenarios_ship_goldens_matching_expectations():
    for scenario_id, _, _, source_pack in KNOWLEDGE_SCENARIOS:
        scenario = load_eval_scenario(scenario_manifest_path("knowledge", scenario_id))
        metadata_path = golden_metadata_path("knowledge", scenario_id)
        expected_path = golden_expected_response_path("knowledge", scenario_id)
        assertions_path = golden_assertions_path("knowledge", scenario_id)

        assert metadata_path.exists()
        assert expected_path.exists()
        assert assertions_path.exists()

        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        assertions = json.loads(assertions_path.read_text(encoding="utf-8"))

        assert metadata["scenario_id"] == scenario.id
        assert metadata["source_pack"] == source_pack
        assert str(metadata["source_pack_version"]) == scenario.provenance.source_pack_version
        assert metadata["review_status"] == scenario.provenance.golden.review_status.value
        assert metadata["expectation_basis"] == scenario.provenance.golden.expectation_basis
        assert expected_path.read_text(encoding="utf-8").strip()
        assert assertions == scenario.expectations.model_dump(
            mode="json",
            exclude_none=True,
            exclude_defaults=True,
        )


@pytest.mark.asyncio
async def test_disabled_knowledge_scenario_exposes_no_fixture_results():
    scenario = load_eval_scenario(
        scenario_manifest_path("knowledge", "disabled-no-knowledge-evidence")
    )
    backend = build_fixture_knowledge_backend(scenario)

    pinned = await backend.get_pinned_documents(version=scenario.knowledge.version)
    skills = await backend.skills_check(query="memory", version=scenario.knowledge.version)
    tickets = await backend.search_support_tickets(
        query="checkout cache memory pressure",
        version=scenario.knowledge.version,
    )

    assert pinned["results_count"] == 0
    assert skills["results_count"] == 0
    assert tickets["results_count"] == 0


@pytest.mark.asyncio
async def test_startup_only_scenario_materializes_pinned_doc_and_skill_context():
    scenario = load_eval_scenario(
        scenario_manifest_path("knowledge", "startup-pinned-runbook-and-skill")
    )
    backend = build_fixture_knowledge_backend(scenario)

    startup_context = await build_startup_knowledge_context(
        query=scenario.execution.query,
        version=scenario.knowledge.version,
        available_tools=[],
        knowledge_backend=backend,
    )

    assert "iterative-diagnostics-runbook" in startup_context
    assert "iterative-memory-check" in startup_context
    skill_envelopes = [
        envelope
        for envelope in getattr(startup_context, "internal_tool_envelopes", [])
        if envelope.get("tool_key") == "knowledge.startup_skills_check"
    ]
    assert len(skill_envelopes) == 1
    assert skill_envelopes[0]["data"]["results_count"] >= 1
    assert {result["document_hash"] for result in skill_envelopes[0]["data"]["results"]} >= {
        "iterative-memory-check"
    }


@pytest.mark.asyncio
async def test_retrieval_only_scenario_surfaces_ticket_backed_guidance():
    scenario = load_eval_scenario(scenario_manifest_path("knowledge", "retrieval-ticket-guidance"))
    backend = build_fixture_knowledge_backend(scenario)

    docs = await backend.search_knowledge_base(
        query='"maintenance-mode-guidance"',
        version=scenario.knowledge.version,
    )
    tickets = await backend.search_support_tickets(
        query="maintenance failover churn replica verification",
        version=scenario.knowledge.version,
    )

    assert docs["results"][0]["document_hash"] == "maintenance-mode-guidance"
    assert tickets["results"][0]["document_hash"] == "RET-5032"


@pytest.mark.asyncio
async def test_full_knowledge_scenario_exposes_pinned_doc_skill_and_ticket():
    scenario = load_eval_scenario(
        scenario_manifest_path("knowledge", "full-maintenance-source-following")
    )
    backend = build_fixture_knowledge_backend(scenario)

    pinned = await backend.get_pinned_documents(version=scenario.knowledge.version)
    skill = await backend.get_skill(
        skill_name="redis-enterprise-maintenance-checklist",
        version=scenario.knowledge.version,
    )
    ticket = await backend.get_support_ticket(ticket_id="RET-5032")

    assert pinned["pinned_documents"][0]["document_hash"] == "maintenance-mode-overview"
    assert "replica health" in skill["full_content"]
    assert ticket["document_hash"] == "RET-5032"

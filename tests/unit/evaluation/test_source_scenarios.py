import json
from pathlib import Path

import pytest
import yaml

from redis_sre_agent.evaluation.fixture_layout import (
    golden_assertions_path,
    golden_expected_response_path,
    golden_metadata_path,
    scenario_manifest_path,
)
from redis_sre_agent.evaluation.knowledge_backend import build_fixture_knowledge_backend
from redis_sre_agent.evaluation.scenarios import EvalScenario, KnowledgeMode

SOURCE_SCENARIOS = [
    ("pinned-sev1-escalation-policy", KnowledgeMode.STARTUP_ONLY),
    ("retrieve-failover-skill-and-follow-it", KnowledgeMode.RETRIEVAL_ONLY),
    ("runbook-overrides-generic-advice", KnowledgeMode.FULL),
    ("no-knowledge-baseline", KnowledgeMode.DISABLED),
    ("legacy-knowledge-boundary-pack", KnowledgeMode.RETRIEVAL_ONLY),
]


@pytest.mark.parametrize(("scenario_name", "expected_mode"), SOURCE_SCENARIOS)
def test_source_following_scenarios_load_with_expected_knowledge_modes(
    scenario_name: str,
    expected_mode: KnowledgeMode,
):
    scenario = EvalScenario.from_file(scenario_manifest_path("sources", scenario_name))

    assert scenario.id == f"sources/{scenario_name}"
    assert scenario.knowledge.mode is expected_mode

    for reference in scenario.knowledge.pinned_documents + scenario.knowledge.corpus:
        assert scenario.resolve_fixture_path(reference).exists(), reference


@pytest.mark.parametrize(("scenario_name", "_"), SOURCE_SCENARIOS)
def test_source_following_scenarios_ship_goldens_matching_expectations(
    scenario_name: str,
    _,
):
    scenario = EvalScenario.from_file(scenario_manifest_path("sources", scenario_name))
    metadata = yaml.safe_load(golden_metadata_path("sources", scenario_name).read_text("utf-8"))
    expected = golden_expected_response_path("sources", scenario_name).read_text("utf-8").strip()
    assertions = json.loads(golden_assertions_path("sources", scenario_name).read_text("utf-8"))

    assert metadata["scenario_id"] == scenario.id
    assert metadata["review_status"] == scenario.provenance.golden.review_status.value
    assert expected
    assert assertions == scenario.expectations.model_dump(mode="json", exclude_none=True)


@pytest.mark.asyncio
async def test_pinned_sev1_policy_scenario_materializes_pinned_document():
    scenario = EvalScenario.from_file(
        scenario_manifest_path("sources", "pinned-sev1-escalation-policy")
    )
    backend = build_fixture_knowledge_backend(scenario)

    pinned = await backend.get_pinned_documents(
        version=scenario.knowledge.version,
        limit=5,
        content_char_budget=2000,
    )

    assert pinned["results_count"] == 1
    assert pinned["pinned_documents"][0]["document_hash"] == "sev1-escalation-policy"


@pytest.mark.asyncio
async def test_retrieval_only_skill_scenario_exposes_skill_and_ticket_sources():
    scenario = EvalScenario.from_file(
        scenario_manifest_path("sources", "retrieve-failover-skill-and-follow-it")
    )
    backend = build_fixture_knowledge_backend(scenario)

    skill = await backend.get_skill(skill_name="failover-investigation-skill")
    ticket = await backend.get_support_ticket(ticket_id="RET-5032")

    assert skill["skill_name"] == "failover-investigation-skill"
    assert ticket["document_hash"] == "RET-5032"


@pytest.mark.asyncio
async def test_retrieval_only_source_scenario_ranks_expected_skill_ticket_and_doc():
    scenario = EvalScenario.from_file(
        scenario_manifest_path("sources", "retrieve-failover-skill-and-follow-it")
    )
    backend = build_fixture_knowledge_backend(scenario)

    skills = await backend.skills_check(
        query="failover investigation checklist maintenance churn",
        version=scenario.knowledge.version,
    )
    docs = await backend.search_knowledge_base(
        query="failover investigation skill replica health maintenance state",
        version=scenario.knowledge.version,
    )
    tickets = await backend.search_support_tickets(
        query="maintenance failover churn previous incident replica verification",
        version=scenario.knowledge.version,
    )

    assert skills["skills"][0]["document_hash"] == "failover-investigation-skill"
    assert docs["results"][0]["document_hash"] == "maintenance-mode-guidance"
    assert docs["results"][0]["source_pack"] == "redis-docs-curated"
    assert docs["results"][0]["source_pack_version"] == "2026-04-01"
    assert tickets["tickets"][0]["ticket_id"] == "RET-5032"


@pytest.mark.asyncio
async def test_full_source_scenario_prefers_runbook_over_generic_advice():
    scenario = EvalScenario.from_file(
        scenario_manifest_path("sources", "runbook-overrides-generic-advice")
    )
    backend = build_fixture_knowledge_backend(scenario)

    pinned = await backend.get_pinned_documents(version=scenario.knowledge.version)
    docs = await backend.search_knowledge_base(
        query="quick fix maxmemory policy evidence steps",
        version=scenario.knowledge.version,
    )

    assert docs["results"][0]["document_hash"] == "runbook-overrides-generic-advice"
    assert docs["results"][0]["source_pack"] == "redis-docs-curated"
    assert docs["results"][0]["source_pack_version"] == "2026-04-01"
    assert {document["document_hash"] for document in pinned["pinned_documents"]} >= {
        "memory-pressure-runbook"
    }


@pytest.mark.asyncio
async def test_no_knowledge_baseline_returns_no_results_across_retrieval_paths():
    scenario = EvalScenario.from_file(scenario_manifest_path("sources", "no-knowledge-baseline"))
    backend = build_fixture_knowledge_backend(scenario)

    skills = await backend.skills_check(query="memory pressure", version=scenario.knowledge.version)
    docs = await backend.search_knowledge_base(
        query="memory pressure runbook",
        version=scenario.knowledge.version,
    )
    tickets = await backend.search_support_tickets(
        query="RET-5032",
        version=scenario.knowledge.version,
    )

    assert skills["results_count"] == 0
    assert docs["results_count"] == 0
    assert tickets["ticket_count"] == 0


@pytest.mark.asyncio
async def test_legacy_source_pack_variant_retrieves_boundary_doc_with_legacy_metadata():
    scenario = EvalScenario.from_file(
        scenario_manifest_path("sources", "legacy-knowledge-boundary-pack")
    )
    backend = build_fixture_knowledge_backend(scenario)

    docs = await backend.get_all_document_fragments(
        document_hash="knowledge-agent-boundary",
        version=scenario.knowledge.version,
    )

    assert docs["document_hash"] == "knowledge-agent-boundary"
    assert docs["metadata"]["source_pack"] == "prompt-core"
    assert docs["metadata"]["source_pack_version"] == "2026-04-01"
    assert docs["metadata"]["review_status"] == "approved"


def test_source_corpora_contain_policy_runbook_skill_and_ticket_assets():
    prompt_policy_root = Path("evals/corpora/prompt-policy-curated/2026-04-14")
    redis_docs_root = Path("evals/corpora/redis-docs-curated/2026-04-01")
    prompt_core_legacy_root = Path("evals/corpora/prompt-core/2026-04-01")

    assert (prompt_policy_root / "documents" / "sev1-escalation-policy.md").exists()
    assert (redis_docs_root / "skills" / "failover-investigation-skill.md").exists()
    assert (redis_docs_root / "documents" / "runbook-overrides-generic-advice.md").exists()
    assert (redis_docs_root / "tickets" / "RET-5032.yaml").exists()
    assert (prompt_core_legacy_root / "documents" / "knowledge-agent-boundary.md").exists()

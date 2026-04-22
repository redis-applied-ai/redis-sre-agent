from __future__ import annotations

import json

import pytest
import yaml

from redis_sre_agent.evaluation.fixture_layout import (
    golden_assertions_path,
    golden_expected_response_path,
    golden_metadata_path,
    scenario_manifest_path,
)
from redis_sre_agent.evaluation.knowledge_backend import build_fixture_knowledge_backend
from redis_sre_agent.evaluation.runtime import load_eval_scenario
from redis_sre_agent.evaluation.scenarios import ExecutionLane, KnowledgeMode

RETRIEVAL_SCENARIOS = [
    ("general-knowledge-core", KnowledgeMode.FULL),
    ("skills-core", KnowledgeMode.RETRIEVAL_ONLY),
    ("support-ticket-exact-match", KnowledgeMode.RETRIEVAL_ONLY),
]


@pytest.mark.parametrize(("scenario_id", "expected_mode"), RETRIEVAL_SCENARIOS)
def test_retrieval_scenarios_load_with_goldens_and_fixture_refs(
    scenario_id: str,
    expected_mode: KnowledgeMode,
):
    scenario = load_eval_scenario(scenario_manifest_path("retrieval", scenario_id))
    metadata = yaml.safe_load(golden_metadata_path("retrieval", scenario_id).read_text("utf-8"))
    expected = golden_expected_response_path("retrieval", scenario_id).read_text("utf-8").strip()
    assertions = json.loads(golden_assertions_path("retrieval", scenario_id).read_text("utf-8"))

    assert scenario.id == f"retrieval/{scenario_id}"
    assert scenario.execution.lane is ExecutionLane.AGENT_ONLY
    assert scenario.execution.agent == "knowledge_only"
    assert scenario.knowledge.mode is expected_mode

    for reference in scenario.knowledge.pinned_documents + scenario.knowledge.corpus:
        assert scenario.resolve_fixture_path(reference).exists(), reference

    assert metadata["scenario_id"] == scenario.id
    assert metadata["review_status"] == scenario.provenance.golden.review_status.value
    assert metadata["expectation_basis"] == scenario.provenance.golden.expectation_basis
    assert metadata["source_pack"] == scenario.provenance.source_pack
    assert str(metadata["source_pack_version"]) == scenario.provenance.source_pack_version
    assert expected
    assert assertions == scenario.expectations.model_dump(mode="json", exclude_none=True)


@pytest.mark.asyncio
async def test_general_knowledge_retrieval_scenario_covers_pinned_versions_and_pack_variants():
    scenario = load_eval_scenario(scenario_manifest_path("retrieval", "general-knowledge-core"))
    backend = build_fixture_knowledge_backend(scenario)

    pinned = await backend.get_pinned_documents(version="latest", limit=5, content_char_budget=4000)
    exact = await backend.search_knowledge_base(
        query='"iterative-diagnostics-runbook"',
        version="latest",
        limit=5,
    )
    pack_variants = await backend.search_knowledge_base(
        query='"knowledge-only-boundary"',
        version="latest",
        limit=5,
    )
    semantic = await backend.search_knowledge_base(
        query="fragmentation destructive remediation",
        version="latest",
        limit=5,
        distance_threshold=0.05,
    )
    legacy = await backend.search_knowledge_base(
        query="legacy eviction",
        version="7.8",
        limit=5,
    )
    latest_legacy = await backend.search_knowledge_base(
        query="legacy eviction",
        version="latest",
        limit=5,
    )

    assert pinned["results_count"] >= 1
    pinned_hashes = {document["document_hash"] for document in pinned["pinned_documents"]}
    assert "destructive-command-safety-policy" in pinned_hashes
    assert {
        (document["source_pack"], document["source_pack_version"])
        for document in pinned["pinned_documents"]
        if document["document_hash"] == "destructive-command-safety-policy"
    } == {("prompt-core", "2026-04-14")}

    assert any(
        result["document_hash"] == "iterative-diagnostics-runbook" for result in exact["results"]
    )

    assert pack_variants["results_count"] >= 2
    assert {
        result["source_pack"]
        for result in pack_variants["results"]
        if result["document_hash"] == "knowledge-only-boundary"
    } == {"prompt-core", "redis-docs-curated"}

    assert semantic["distance_threshold"] == 0.05
    assert any(result["document_hash"] == "fragmentation-triage" for result in semantic["results"])

    assert legacy["results_count"] >= 1
    assert any(
        result["document_hash"] == "legacy-eviction-guidance" for result in legacy["results"]
    )
    assert all(
        result["document_hash"] != "legacy-eviction-guidance" for result in latest_legacy["results"]
    )


@pytest.mark.asyncio
async def test_skills_retrieval_scenario_matches_prompt_and_redis_doc_skills():
    scenario = load_eval_scenario(scenario_manifest_path("retrieval", "skills-core"))
    backend = build_fixture_knowledge_backend(scenario)

    memory_skills = await backend.skills_check(
        query="memory pressure info memory", version="latest"
    )
    triage_search = await backend.search_knowledge_base(
        query="triage",
        version="latest",
        index_type="skills",
        include_special_document_types=True,
        limit=10,
    )
    failover_skill = await backend.get_skill(
        skill_name="failover-investigation-skill",
        version="latest",
    )
    maintenance_skill = await backend.search_knowledge_base(
        query='"redis enterprise maintenance checklist"',
        version="latest",
        index_type="skills",
        include_special_document_types=True,
        limit=5,
    )

    assert memory_skills["distance_threshold"] == 0.8
    assert memory_skills["results_count"] >= 1
    assert memory_skills["skills"][0]["document_hash"] == "iterative-memory-check"

    assert {
        result["source_pack"]
        for result in triage_search["results"]
        if result["document_hash"] in {"iterative-redis-triage", "evidence-first-triage"}
    } == {"prompt-core", "redis-docs-curated"}

    assert failover_skill["skill_name"] == "failover-investigation-skill"
    assert "failover posture" in failover_skill["full_content"]

    assert (
        maintenance_skill["results"][0]["document_hash"] == "redis-enterprise-maintenance-checklist"
    )
    assert maintenance_skill["results"][0]["source_pack"] == "redis-docs-curated"


@pytest.mark.asyncio
async def test_skills_retrieval_scenario_supports_discover_then_fetch_flow():
    scenario = load_eval_scenario(scenario_manifest_path("retrieval", "skills-core"))
    backend = build_fixture_knowledge_backend(scenario)

    discovered = await backend.skills_check(
        query="Redis Enterprise maintenance failover checklist",
        version="latest",
    )
    discovered_by_name = {skill["name"]: skill for skill in discovered["skills"]}
    selected_skill = discovered_by_name["redis-enterprise-maintenance-checklist"]
    fetched = await backend.get_skill(skill_name=selected_skill["name"], version="latest")

    assert "redis-enterprise-maintenance-checklist" in discovered_by_name
    assert selected_skill["document_hash"] == "redis-enterprise-maintenance-checklist"
    assert fetched["skill_name"] == selected_skill["name"]
    assert "replica health" in fetched["full_content"]


@pytest.mark.asyncio
async def test_support_ticket_retrieval_scenario_supports_exact_and_semantic_lookup():
    scenario = load_eval_scenario(scenario_manifest_path("retrieval", "support-ticket-exact-match"))
    backend = build_fixture_knowledge_backend(scenario)

    exact = await backend.search_support_tickets(query="RET-5032", version="latest", limit=5)
    semantic = await backend.search_support_tickets(
        query="maintenance window failover churn replica health",
        version="latest",
        limit=5,
    )
    prompt_ticket = await backend.search_support_tickets(
        query="checkout cache memory pressure live validation",
        version="latest",
        limit=5,
    )
    exact_prompt_ticket = await backend.search_support_tickets(
        query="RET-9001",
        version="latest",
        limit=5,
    )
    ticket = await backend.get_support_ticket(ticket_id="RET-5032")

    assert exact["ticket_count"] >= 1
    assert exact["tickets"][0]["ticket_id"] == "RET-5032"
    assert exact["doc_type_filter"] == "support_ticket"

    assert semantic["tickets"][0]["ticket_id"] == "RET-5032"
    assert prompt_ticket["tickets"][0]["ticket_id"] == "RET-9001"
    assert exact_prompt_ticket["tickets"][0]["ticket_id"] == "RET-9001"

    assert ticket["document_hash"] == "RET-5032"
    assert ticket["metadata"]["source_pack"] == "redis-docs-curated"
    assert ticket["metadata"]["source_pack_version"] == "2026-04-01"

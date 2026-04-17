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
from redis_sre_agent.evaluation.scenarios import EvalScenario, ExecutionLane, KnowledgeMode

_RETRIEVAL_MATRIX_SCENARIOS = [
    ("docs-maintenance-guidance", "doc", ["maintenance-mode-guidance"]),
    ("skill-maintenance-checklist", "skill", ["redis-enterprise-maintenance-checklist"]),
    ("ticket-ret-5032", "ticket", ["RET-5032"]),
    ("versioned-memory-guidance-latest", "doc", ["memory-policy-latest"]),
    ("versioned-memory-guidance-7-8", "doc", ["memory-policy-7-8"]),
    (
        "cross-pack-live-access",
        "doc",
        ["knowledge-only-boundary", "knowledge-only-access-policy"],
    ),
]


@pytest.mark.parametrize(
    ("scenario_name", "_kind", "required_sources"),
    _RETRIEVAL_MATRIX_SCENARIOS,
)
def test_retrieval_matrix_scenarios_load_from_eval_tree(
    scenario_name: str,
    _kind: str,
    required_sources: list[str],
):
    scenario = EvalScenario.from_file(scenario_manifest_path("retrieval", scenario_name))

    assert scenario.id == f"retrieval/{scenario_name}"
    assert scenario.execution.lane is ExecutionLane.AGENT_ONLY
    assert scenario.execution.agent == "knowledge"
    assert scenario.knowledge.mode is KnowledgeMode.RETRIEVAL_ONLY
    assert scenario.expectations.required_sources == required_sources


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario_name", "kind", "required_sources"),
    _RETRIEVAL_MATRIX_SCENARIOS,
)
async def test_retrieval_matrix_scenarios_return_expected_sources(
    scenario_name: str,
    kind: str,
    required_sources: list[str],
):
    scenario = EvalScenario.from_file(scenario_manifest_path("retrieval", scenario_name))
    backend = build_fixture_knowledge_backend(scenario)

    if kind == "skill":
        result = await backend.skills_check(
            query=scenario.execution.query,
            version=scenario.knowledge.version,
        )
        retrieved = [row["document_hash"] for row in result["skills"]]
    elif kind == "ticket":
        result = await backend.search_support_tickets(
            query=scenario.execution.query,
            version=scenario.knowledge.version,
        )
        retrieved = [row["document_hash"] for row in result["tickets"]]
    else:
        result = await backend.search_knowledge_base(
            query=scenario.execution.query,
            version=scenario.knowledge.version,
        )
        retrieved = [row["document_hash"] for row in result["results"]]

    assert all(source in retrieved for source in required_sources)

    if scenario_name == "cross-pack-live-access":
        assert {row["source_pack"] for row in result["results"]} == {
            "prompt-core",
            "redis-docs-curated",
        }


def test_retrieval_matrix_scenarios_ship_goldens_matching_expectations():
    for scenario_name, _, _ in _RETRIEVAL_MATRIX_SCENARIOS:
        scenario = EvalScenario.from_file(scenario_manifest_path("retrieval", scenario_name))
        metadata_path = golden_metadata_path("retrieval", scenario_name)
        expected_path = golden_expected_response_path("retrieval", scenario_name)
        assertions_path = golden_assertions_path("retrieval", scenario_name)

        assert metadata_path.exists()
        assert expected_path.exists()
        assert assertions_path.exists()

        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        assertions = json.loads(assertions_path.read_text(encoding="utf-8"))

        assert metadata["scenario_id"] == scenario.id
        assert metadata["source_pack"] == scenario.provenance.source_pack
        assert str(metadata["source_pack_version"]) == scenario.provenance.source_pack_version
        assert assertions == scenario.expectations.model_dump(mode="json", exclude_none=True)
        assert expected_path.read_text(encoding="utf-8").strip()


@pytest.mark.asyncio
async def test_retrieval_matrix_versioned_scenarios_honor_requested_version():
    latest = EvalScenario.from_file(
        scenario_manifest_path("retrieval", "versioned-memory-guidance-latest")
    )
    legacy = EvalScenario.from_file(
        scenario_manifest_path("retrieval", "versioned-memory-guidance-7-8")
    )

    latest_results = await build_fixture_knowledge_backend(latest).search_knowledge_base(
        query=latest.execution.query,
        version=latest.knowledge.version,
    )
    legacy_results = await build_fixture_knowledge_backend(legacy).search_knowledge_base(
        query=legacy.execution.query,
        version=legacy.knowledge.version,
    )

    assert latest_results["results"][0]["document_hash"] == "memory-policy-latest"
    assert all(row["document_hash"] != "memory-policy-7-8" for row in latest_results["results"])
    assert legacy_results["results"][0]["document_hash"] == "memory-policy-7-8"

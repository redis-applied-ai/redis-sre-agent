from pathlib import Path

import pytest
import yaml

from redis_sre_agent.evaluation.knowledge_backend import build_fixture_knowledge_backend
from redis_sre_agent.evaluation.scenarios import EvalScenario


def _write_fixture_scenario(tmp_path: Path) -> EvalScenario:
    fixtures_dir = tmp_path / "fixtures"
    corpus_root = fixtures_dir / "corpora" / "redis-docs-curated" / "2026-04-13"
    docs_dir = corpus_root / "documents"
    skills_dir = corpus_root / "skills"
    tickets_dir = corpus_root / "tickets"
    docs_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    tickets_dir.mkdir(parents=True)
    (corpus_root / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "source_kind": "redis_docs",
                "source_pack": "redis-docs-curated",
                "source_pack_version": "2026-04-13",
                "derived_from": ["redis-docs-batch-17"],
                "review_status": "reviewed",
                "reviewed_by": "sre-evals",
                "exemplar_sources": ["expected-answer-v1"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    (docs_dir / "maintenance-runbook.md").write_text(
        "\n".join(
            [
                "---",
                "name: maintenance-runbook",
                "title: Maintenance Runbook",
                "doc_type: runbook",
                "category: incident",
                "priority: critical",
                "pinned: true",
                "summary: Check maintenance mode before failover triage.",
                "source: fixture://docs/maintenance-runbook.md",
                "---",
                "Check maintenance mode before failover triage.",
            ]
        ),
        encoding="utf-8",
    )
    (docs_dir / "legacy-runbook.md").write_text(
        "\n".join(
            [
                "---",
                "name: legacy-runbook",
                "title: Legacy Runbook",
                "doc_type: runbook",
                "category: incident",
                "priority: high",
                "pinned: true",
                "version: 7.8",
                "summary: Legacy maintenance guidance for Redis 7.8.",
                "source: fixture://docs/legacy-runbook.md",
                "---",
                "Legacy maintenance guidance for Redis 7.8 clusters.",
            ]
        ),
        encoding="utf-8",
    )
    (docs_dir / "failover-guide.md").write_text(
        "\n".join(
            [
                "---",
                "document_hash: failover-guide",
                "name: failover-guide",
                "title: Failover Guide",
                "doc_type: knowledge",
                "category: incident",
                "priority: high",
                "summary: Investigate maintenance mode before any failover.",
                "source: fixture://docs/failover-guide.md",
                "product_labels:",
                "  - redis-enterprise",
                "---",
                "Investigate maintenance mode before any failover on enterprise clusters.",
            ]
        ),
        encoding="utf-8",
    )
    (docs_dir / "eviction-7-8.md").write_text(
        "\n".join(
            [
                "---",
                "document_hash: eviction-guide-7-8",
                "name: eviction-guide-7-8",
                "title: Redis 7.8 Eviction Guide",
                "doc_type: knowledge",
                "category: maintenance",
                "priority: normal",
                "version: 7.8",
                "summary: Redis 7.8 eviction behavior.",
                "source: fixture://docs/eviction-7-8.md",
                "---",
                "Redis 7.8 eviction behavior differs from the latest branch.",
            ]
        ),
        encoding="utf-8",
    )
    (skills_dir / "maintenance-mode-skill.md").write_text(
        "\n".join(
            [
                "---",
                "document_hash: maintenance-mode-skill",
                "name: maintenance-mode-skill",
                "title: Maintenance Mode Skill",
                "doc_type: skill",
                "priority: high",
                "summary: Check maintenance mode before using admin tooling.",
                "source: fixture://skills/maintenance-mode-skill.md",
                "---",
                "Before using admin tooling, check whether maintenance mode is enabled.",
            ]
        ),
        encoding="utf-8",
    )
    (tickets_dir / "RET-4421.yaml").write_text(
        yaml.safe_dump(
            {
                "document_hash": "RET-4421",
                "name": "RET-4421",
                "title": "Checkout cache failover",
                "doc_type": "support_ticket",
                "priority": "high",
                "summary": "Prior incident caused by maintenance mode on a node.",
                "source": "fixture://tickets/RET-4421.yaml",
                "content": "Prior incident caused by maintenance mode on a checkout cache node.",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        yaml.safe_dump(
            {
                "id": "fixture-knowledge-runtime",
                "name": "Fixture knowledge runtime",
                "provenance": {
                    "source_kind": "synthetic",
                    "source_pack": "fixture-pack",
                    "source_pack_version": "2026-04-13",
                    "golden": {
                        "expectation_basis": "human_authored",
                    },
                },
                "execution": {
                    "lane": "full_turn",
                    "query": "Investigate maintenance mode on the checkout cache.",
                    "route_via_router": True,
                },
                "knowledge": {
                    "mode": "full",
                    "version": "latest",
                    "pinned_documents": [
                        "fixtures/corpora/redis-docs-curated/2026-04-13/documents/maintenance-runbook.md",
                        "fixtures/corpora/redis-docs-curated/2026-04-13/documents/legacy-runbook.md",
                    ],
                    "corpus": [
                        "fixtures/corpora/redis-docs-curated/2026-04-13",
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return EvalScenario.from_file(scenario_path)


@pytest.mark.asyncio
async def test_fixture_knowledge_backend_matches_eval_helper_contracts(tmp_path: Path):
    scenario = _write_fixture_scenario(tmp_path)
    backend = build_fixture_knowledge_backend(scenario)

    pinned = await backend.get_pinned_documents(version="latest", limit=5, content_char_budget=200)
    skills = await backend.skills_check(query="maintenance mode", version="latest")
    skill = await backend.get_skill(skill_name="maintenance-mode-skill", version="latest")
    search = await backend.search_knowledge_base(query='"maintenance mode"', version="latest")
    tickets = await backend.search_support_tickets(query="RET-4421", version="latest")
    ticket = await backend.get_support_ticket(ticket_id="RET-4421")
    fragments = await backend.get_all_document_fragments(
        document_hash="failover-guide",
        index_type="knowledge",
        version="latest",
    )
    related = await backend.get_related_document_fragments(
        document_hash="failover-guide",
        current_chunk_index=0,
        context_window=1,
        version="latest",
        index_type="knowledge",
    )

    assert pinned["results_count"] == 1
    assert pinned["pinned_documents"][0]["name"] == "maintenance-runbook"
    assert pinned["pinned_documents"][0]["full_content"] == (
        "Check maintenance mode before failover triage."
    )
    assert skills["results_count"] == 1
    assert skills["skills"][0]["name"] == "maintenance-mode-skill"
    assert skill == {
        "skill_name": "maintenance-mode-skill",
        "full_content": "Before using admin tooling, check whether maintenance mode is enabled.",
    }
    assert search["results_count"] == 1
    assert search["results"][0]["document_hash"] == "failover-guide"
    assert search["results"][0]["source_kind"] == "redis_docs"
    assert search["results"][0]["source_pack"] == "redis-docs-curated"
    assert search["results"][0]["source_pack_version"] == "2026-04-13"
    assert search["results"][0]["derived_from"] == ["redis-docs-batch-17"]
    assert search["results"][0]["review_status"] == "reviewed"
    assert tickets["ticket_count"] == 1
    assert tickets["tickets"][0]["ticket_id"] == "RET-4421"
    assert ticket["full_content"] == (
        "Prior incident caused by maintenance mode on a checkout cache node."
    )
    assert fragments["fragments_count"] == 1
    assert fragments["metadata"]["product_labels"] == ["redis-enterprise"]
    assert fragments["metadata"]["source_pack"] == "redis-docs-curated"
    assert fragments["metadata"]["source_pack_version"] == "2026-04-13"
    assert related["related_count"] == 1
    assert related["related_fragments"][0]["is_target_chunk"] is True


@pytest.mark.asyncio
async def test_fixture_knowledge_backend_applies_version_filters_and_pinned_budget(tmp_path: Path):
    scenario = _write_fixture_scenario(tmp_path)
    backend = build_fixture_knowledge_backend(scenario)

    latest_pinned = await backend.get_pinned_documents(
        version="latest",
        limit=5,
        content_char_budget=20,
    )
    legacy_search = await backend.search_knowledge_base(query="eviction", version="7.8")
    latest_search = await backend.search_knowledge_base(query="eviction", version="latest")
    missing_skill = await backend.get_skill(skill_name="missing-skill", version="latest")

    assert latest_pinned["results_count"] == 1
    assert latest_pinned["truncated"] is True
    assert latest_pinned["pinned_documents"][0]["truncated"] is True
    assert latest_pinned["pinned_documents"][0]["full_content"].endswith("...")
    assert legacy_search["results_count"] == 1
    assert legacy_search["results"][0]["document_hash"] == "eviction-guide-7-8"
    assert all(
        result["document_hash"] != "eviction-guide-7-8" for result in latest_search["results"]
    )
    assert missing_skill["error"] == "Skill not found"
    assert missing_skill["available_skills"] == ["maintenance-mode-skill"]

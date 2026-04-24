"""Tests for formal skill packages in the fixture-backed eval knowledge backend."""

from pathlib import Path

import pytest
import yaml

from redis_sre_agent.evaluation.knowledge_backend import build_fixture_knowledge_backend
from redis_sre_agent.evaluation.scenarios import EvalScenario


def _write_scenario_with_formal_skills(tmp_path: Path) -> EvalScenario:
    corpus_root = tmp_path / "fixtures" / "corpora" / "formal-skills" / "2026-04-22"
    skills_dir = corpus_root / "skills"
    legacy_skill = skills_dir / "legacy-triage.md"
    formal_skill = skills_dir / "redis-maintenance-triage"
    (formal_skill / "references").mkdir(parents=True)
    (formal_skill / "scripts").mkdir()

    legacy_skill.parent.mkdir(parents=True, exist_ok=True)
    legacy_skill.write_text(
        "---\nname: legacy-triage\ndoc_type: skill\nsummary: Legacy summary.\n---\n\nLegacy body\n",
        encoding="utf-8",
    )
    (formal_skill / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: redis-maintenance-triage",
                "description: Investigate maintenance mode before failover.",
                "summary: Check maintenance state before disruptive actions.",
                "---",
                "",
                "Formal entrypoint body",
            ]
        ),
        encoding="utf-8",
    )
    (formal_skill / "references" / "maintenance-checklist.md").write_text(
        "---\ntitle: Maintenance Checklist\ndescription: Evidence checklist.\n---\n\nChecklist body\n",
        encoding="utf-8",
    )
    (formal_skill / "scripts" / "collect_context.sh").write_text(
        "#!/usr/bin/env bash\necho collect\n",
        encoding="utf-8",
    )

    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        yaml.safe_dump(
            {
                "id": "formal-skill-runtime",
                "name": "Formal skill runtime",
                "provenance": {
                    "source_kind": "synthetic",
                    "source_pack": "formal-skills",
                    "source_pack_version": "2026-04-22",
                    "golden": {"expectation_basis": "human_authored"},
                },
                "execution": {
                    "lane": "full_turn",
                    "query": "Check maintenance mode before failover.",
                    "route_via_router": True,
                },
                "knowledge": {
                    "mode": "full",
                    "version": "latest",
                    "corpus": [str(corpus_root)],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return EvalScenario.from_file(scenario_path)


@pytest.mark.asyncio
async def test_fixture_backend_loads_formal_and_legacy_skills(tmp_path: Path):
    scenario = _write_scenario_with_formal_skills(tmp_path)
    backend = build_fixture_knowledge_backend(scenario)

    skills = await backend.skills_check(query="maintenance", version="latest")
    formal = await backend.get_skill(skill_name="redis-maintenance-triage", version="latest")
    formal_resource = await backend.get_skill_resource(
        skill_name="redis-maintenance-triage",
        resource_path="references/maintenance-checklist.md",
        version="latest",
    )
    legacy = await backend.get_skill(skill_name="legacy-triage", version="latest")

    assert {skill["name"] for skill in skills["skills"]} == {
        "legacy-triage",
        "redis-maintenance-triage",
    }
    formal_skill_row = next(
        skill for skill in skills["skills"] if skill["name"] == "redis-maintenance-triage"
    )
    assert formal_skill_row["protocol"] == "formal_v1"
    assert formal_skill_row["has_references"] is True
    assert formal["references"] == [
        {
            "path": "references/maintenance-checklist.md",
            "title": "Maintenance Checklist",
            "summary": "Evidence checklist.",
        }
    ]
    assert formal["scripts"] == [
        {
            "path": "scripts/collect_context.sh",
            "description": "Script resource at collect_context.sh",
        }
    ]
    assert formal_resource["resource_kind"] == "reference"
    assert formal_resource["content"] == "Checklist body"
    assert legacy == {"skill_name": "legacy-triage", "full_content": "Legacy body"}

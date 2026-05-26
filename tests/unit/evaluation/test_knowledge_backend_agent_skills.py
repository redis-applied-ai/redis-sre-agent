"""Tests for Agent Skills packages in the fixture-backed eval knowledge backend."""

import re
from pathlib import Path

import pytest
import yaml

from redis_sre_agent.evaluation.knowledge_backend import (
    FixtureKnowledgeBackend,
    FixtureKnowledgeDocument,
    build_fixture_knowledge_backend,
)
from redis_sre_agent.evaluation.scenarios import EvalScenario


def _write_scenario_with_agent_skills(tmp_path: Path) -> EvalScenario:
    corpus_root = tmp_path / "fixtures" / "corpora" / "agent-skills" / "2026-04-22"
    skills_dir = corpus_root / "skills"
    legacy_skill = skills_dir / "legacy-triage.md"
    agent_skill = skills_dir / "example-incident-brief"
    (agent_skill / "references").mkdir(parents=True)
    (agent_skill / "scripts").mkdir()
    (agent_skill / "agents").mkdir()

    legacy_skill.parent.mkdir(parents=True, exist_ok=True)
    legacy_skill.write_text(
        "---\nname: legacy-triage\ndoc_type: skill\nsummary: Legacy summary.\n---\n\nLegacy body\n",
        encoding="utf-8",
    )
    (agent_skill / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: example-incident-brief",
                "description: Produce an incident brief from generic tool evidence.",
                "summary: Build a structured incident brief from evidence.",
                "---",
                "",
                "# Example Incident Brief",
                "",
                "## Output structure",
                "",
                "Return one markdown document in this shape:",
                "",
                "```markdown",
                "# Incident Brief: <incident name>",
                "",
                "**Incident ID:** <incident id>",
                "**Primary service:** <service name>",
                "",
                "## Summary",
                "",
                "## Evidence Timeline",
                "",
                "## Tool Findings",
                "",
                "### Inventory",
                "",
                "### Metrics",
                "",
                "## Open Questions",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    (agent_skill / "references" / "evidence-checklist.md").write_text(
        "---\ntitle: Evidence Checklist\ndescription: Evidence checklist.\n---\n\nChecklist body\n",
        encoding="utf-8",
    )
    (agent_skill / "scripts" / "collect_context.sh").write_text(
        "#!/usr/bin/env bash\necho collect\n",
        encoding="utf-8",
    )
    (agent_skill / "agents" / "openai.yaml").write_text(
        "\n".join(
            [
                "display_name: Example Incident Brief",
                "preferred_entrypoint: SKILL.md",
                "workflow_contract:",
                "  required_tool_calls:",
                "    - get_incident",
                "    - get_metric_window",
                "  progress_checklist:",
                "    - Retrieve the incident record before writing the brief.",
            ]
        ),
        encoding="utf-8",
    )

    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        yaml.safe_dump(
            {
                "id": "agent-skills-runtime",
                "name": "Agent Skills runtime",
                "provenance": {
                    "source_kind": "synthetic",
                    "source_pack": "agent-skills",
                    "source_pack_version": "2026-04-22",
                    "golden": {"expectation_basis": "human_authored"},
                },
                "execution": {
                    "lane": "full_turn",
                    "query": "Produce an incident brief.",
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
async def test_fixture_backend_loads_agent_skills_and_legacy_skills(tmp_path: Path):
    scenario = _write_scenario_with_agent_skills(tmp_path)
    backend = build_fixture_knowledge_backend(scenario)

    skills = await backend.skills_check(query="incident", version="latest")
    agent_skill = await backend.get_skill(skill_name="example-incident-brief", version="latest")
    agent_skill_resource = await backend.get_skill_resource(
        skill_name="example-incident-brief",
        resource_path="references/evidence-checklist.md",
        version="latest",
    )
    legacy = await backend.get_skill(skill_name="legacy-triage", version="latest")

    assert {skill["name"] for skill in skills["skills"]} == {
        "legacy-triage",
        "example-incident-brief",
    }
    agent_skill_row = next(
        skill for skill in skills["skills"] if skill["name"] == "example-incident-brief"
    )
    legacy_skill_row = next(skill for skill in skills["skills"] if skill["name"] == "legacy-triage")
    assert agent_skill_row["protocol"] == "agent_skills_v1"
    assert agent_skill_row["has_references"] is True
    assert legacy_skill_row["matched_resource_path"] == ""
    assert agent_skill["references"] == [
        {
            "path": "references/evidence-checklist.md",
            "title": "Evidence Checklist",
            "summary": "Evidence checklist.",
        }
    ]
    assert agent_skill["scripts"] == [
        {
            "path": "scripts/collect_context.sh",
            "description": "Script resource at collect_context.sh",
        }
    ]
    assert agent_skill["output_contract"] == {
        "mode": "markdown",
        "instructions": [
            "Return one markdown document only.",
            "Do not rename required headings.",
            "Use the required headings verbatim and in order.",
            "Include all required sections even when brief.",
        ],
        "validation_checklist": [
            "Confirm the final answer follows the markdown template from the skill's Output structure section.",
            "Confirm the document ends after `## Open Questions` with no footer.",
        ],
        "required_preamble_lines": [
            "# Incident Brief: <incident name>",
            "**Incident ID:** <incident id>",
            "**Primary service:** <service name>",
        ],
        "required_order": [
            "## Summary",
            "## Evidence Timeline",
            "## Tool Findings",
            "## Open Questions",
        ],
        "required_subsections": ["### Inventory", "### Metrics"],
        "required_patterns": [
            {
                "description": "Put `# Incident Brief: <incident name>` on its own line, add a blank line, then place `**Incident ID:**`, `**Primary service:**` on separate lines.",
                "pattern": "(?s)^\\#\\ Incident\\ Brief:\\ .+?\\\n\\\n\\*\\*Incident\\ ID:\\*\\*\\ .+?\\\n\\*\\*Primary\\ service:\\*\\*\\ .+?",
            },
            {
                "description": "Include a line matching `**Incident ID:** <incident id>`.",
                "pattern": "(?m)^\\*\\*Incident\\ ID:\\*\\*\\ .+?$",
            },
            {
                "description": "Include a line matching `**Primary service:** <service name>`.",
                "pattern": "(?m)^\\*\\*Primary\\ service:\\*\\*\\ .+?$",
            },
            {
                "description": "End the document in the required `## Open Questions` section without adding another `##` section.",
                "pattern": "(?s)\\#\\#\\ Open\\ Questions(?:(?!\\n##\\s).)*\\s*$",
            },
        ],
        "must_include_even_if_empty": True,
        "template": "\n".join(
            [
                "# Incident Brief: <incident name>",
                "",
                "**Incident ID:** <incident id>",
                "**Primary service:** <service name>",
                "",
                "## Summary",
                "",
                "## Evidence Timeline",
                "",
                "## Tool Findings",
                "",
                "### Inventory",
                "",
                "### Metrics",
                "",
                "## Open Questions",
            ]
        ),
    }
    final_section_pattern = agent_skill["output_contract"]["required_patterns"][-1]["pattern"]
    assert re.search(
        final_section_pattern,
        "## Summary\nok\n\n## Evidence Timeline\nnow\n\n## Tool Findings\n\n"
        "### Inventory\nok\n\n### Metrics\nok\n\n## Open Questions\nnone",
    )
    assert (
        re.search(
            final_section_pattern,
            "## Summary\nok\n\n## Open Questions\nnone\n\n## Footer\nextra",
        )
        is None
    )
    assert agent_skill["workflow_contract"] == {
        "required_tool_calls": ["get_incident", "get_metric_window"],
        "progress_checklist": ["Retrieve the incident record before writing the brief."],
    }
    assert agent_skill["contract_summary"][0].startswith(
        "This skill defines a binding output contract."
    )
    assert (
        "Output pattern: Include a line matching `**Incident ID:** <incident id>`."
        in agent_skill["contract_summary"]
    )
    assert (
        "Validation checklist: Confirm the document ends after `## Open Questions` with no footer."
        in agent_skill["contract_summary"]
    )
    assert (
        "Workflow checklist: Retrieve the incident record before writing the brief."
        in agent_skill["contract_summary"]
    )
    assert agent_skill_resource["resource_kind"] == "reference"
    assert agent_skill_resource["content"] == "Checklist body"
    assert legacy == {"skill_name": "legacy-triage", "full_content": "Legacy body"}


@pytest.mark.asyncio
async def test_fixture_backend_ignores_skill_markers_above_corpus_root(tmp_path: Path):
    (tmp_path / "SKILL.md").write_text(
        "---\nname: outer-skill\ndescription: outer package\n---\n",
        encoding="utf-8",
    )
    corpus_root = tmp_path / "fixtures" / "corpora" / "shared" / "2026-04-22"
    corpus_root.mkdir(parents=True)
    (corpus_root / "ops-guide.md").write_text(
        "---\nsummary: Shared ops guide.\n---\n\nCheck the dashboard first.\n",
        encoding="utf-8",
    )

    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        yaml.safe_dump(
            {
                "id": "shared-doc-runtime",
                "name": "Shared doc runtime",
                "provenance": {
                    "source_kind": "synthetic",
                    "source_pack": "shared",
                    "source_pack_version": "2026-04-22",
                    "golden": {"expectation_basis": "human_authored"},
                },
                "execution": {
                    "lane": "full_turn",
                    "query": "Check the dashboard first.",
                    "route_via_router": True,
                },
                "knowledge": {
                    "mode": "full",
                    "version": "latest",
                    "corpus": [str(corpus_root / "ops-guide.md")],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    backend = build_fixture_knowledge_backend(EvalScenario.from_file(scenario_path))

    result = await backend.get_all_document_fragments(
        document_hash="ops-guide",
        index_type="knowledge",
        version="latest",
    )

    assert result["title"] == "ops-guide"
    assert result["fragments"][0]["content"] == "Check the dashboard first."


@pytest.mark.asyncio
async def test_fixture_backend_skills_check_keeps_best_matching_resource_for_query():
    backend = FixtureKnowledgeBackend(
        [
            FixtureKnowledgeDocument(
                document_hash="entrypoint-doc",
                title="Example Incident Brief",
                name="example-incident-brief",
                content="General incident overview.",
                source="file://skills/example-incident-brief/SKILL.md",
                category="shared",
                doc_type="skill",
                severity="medium",
                summary="General incident guidance.",
                priority="normal",
                pinned=False,
                version="latest",
                product_labels=[],
                index_type="skills",
                provenance={},
                protocol="agent_skills_v1",
                resource_kind="entrypoint",
                resource_path="SKILL.md",
                has_references=True,
            ),
            FixtureKnowledgeDocument(
                document_hash="reference-doc",
                title="Evidence Checklist",
                name="example-incident-brief",
                content="Checklist body includes timeline evidence and owner confirmation.",
                source=("file://skills/example-incident-brief/references/evidence-checklist.md"),
                category="shared",
                doc_type="skill",
                severity="medium",
                summary="Detailed evidence checklist.",
                priority="normal",
                pinned=False,
                version="latest",
                product_labels=[],
                index_type="skills",
                provenance={},
                protocol="agent_skills_v1",
                resource_kind="reference",
                resource_path="references/evidence-checklist.md",
                has_references=True,
            ),
        ]
    )

    result = await backend.skills_check(query="timeline evidence", version="latest")

    assert result["skills"][0]["name"] == "example-incident-brief"
    assert result["skills"][0]["matched_resource_kind"] == "reference"
    assert result["skills"][0]["matched_resource_path"] == "references/evidence-checklist.md"
    assert result["search_type"] == "semantic"


@pytest.mark.asyncio
async def test_fixture_backend_skills_check_without_query_prefers_entrypoint_representative():
    backend = FixtureKnowledgeBackend(
        [
            FixtureKnowledgeDocument(
                document_hash="entrypoint-doc",
                title="Example Incident Brief",
                name="example-incident-brief",
                content="General incident overview.",
                source="file://skills/example-incident-brief/SKILL.md",
                category="shared",
                doc_type="skill",
                severity="medium",
                summary="General incident guidance.",
                priority="normal",
                pinned=False,
                version="latest",
                product_labels=[],
                index_type="skills",
                provenance={},
                protocol="agent_skills_v1",
                resource_kind="entrypoint",
                resource_path="SKILL.md",
                has_references=True,
            ),
            FixtureKnowledgeDocument(
                document_hash="uppercase-reference-doc",
                title="Agent Skills Overview",
                name="example-incident-brief",
                content="High-level overview.",
                source="file://skills/example-incident-brief/AGENTS.md",
                category="shared",
                doc_type="skill",
                severity="medium",
                summary="Overview doc.",
                priority="normal",
                pinned=False,
                version="latest",
                product_labels=[],
                index_type="skills",
                provenance={},
                protocol="agent_skills_v1",
                resource_kind="reference",
                resource_path="AGENTS.md",
                has_references=True,
            ),
        ]
    )

    result = await backend.skills_check(version="latest")

    assert result["skills"][0]["name"] == "example-incident-brief"
    assert result["skills"][0]["matched_resource_kind"] == "entrypoint"
    assert result["skills"][0]["matched_resource_path"] == "SKILL.md"
    assert result["search_type"] is None


@pytest.mark.asyncio
async def test_fixture_backend_skills_check_reports_unsupported_hybrid_search():
    backend = FixtureKnowledgeBackend([])

    result = await backend.skills_check(
        query="incident",
        search_type="hybrid",
        version="latest",
    )

    assert result["error"] == "unsupported_search_type"
    assert result["requested_search_type"] == "hybrid"
    assert result["supported_search_types"] == ["semantic", "keyword"]


@pytest.mark.asyncio
async def test_fixture_backend_skills_check_prefers_skill_description_for_summary():
    backend = FixtureKnowledgeBackend(
        [
            FixtureKnowledgeDocument(
                document_hash="entrypoint-doc",
                title="Example Incident Brief",
                name="example-incident-brief",
                content="General incident overview.",
                source="file://skills/example-incident-brief/SKILL.md",
                category="shared",
                doc_type="skill",
                severity="medium",
                summary="Summary field that should not win.",
                priority="normal",
                pinned=False,
                version="latest",
                product_labels=[],
                index_type="skills",
                provenance={},
                protocol="agent_skills_v1",
                resource_kind="entrypoint",
                resource_path="SKILL.md",
                has_references=True,
                skill_description="Description field that should win.",
            )
        ]
    )

    result = await backend.skills_check(version="latest")

    assert result["skills"][0]["summary"] == "Description field that should win."

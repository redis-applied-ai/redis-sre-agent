"""Tests for Agent Skills discovery and scaffolding."""

from pathlib import Path

import redis_sre_agent.skills.discovery as discovery
from redis_sre_agent.skills.discovery import (
    discover_skill_packages,
    find_skill_package_root,
    load_skill_package,
    skill_package_to_documents,
)
from redis_sre_agent.skills.scaffold import scaffold_skill_package_from_markdown


def _write_skill_package(root: Path, skill_name: str = "redis-maintenance-triage") -> Path:
    package_dir = root / skill_name
    (package_dir / "references").mkdir(parents=True)
    (package_dir / "scripts").mkdir()
    (package_dir / "assets").mkdir()
    (package_dir / "agents").mkdir()

    (package_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {skill_name}",
                "title: Redis Maintenance Triage",
                "description: Investigate maintenance mode before failover.",
                "summary: Check maintenance state before disruptive actions.",
                "---",
                "",
                "# Redis Maintenance Triage",
                "",
                "Investigate maintenance mode before failover.",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "references" / "maintenance-checklist.md").write_text(
        "\n".join(
            [
                "---",
                "title: Maintenance Checklist",
                "description: Evidence checklist for maintenance investigations.",
                "---",
                "",
                "- maintenance mode",
                "- owner",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "scripts" / "collect_context.sh").write_text(
        "#!/usr/bin/env bash\necho collect\n",
        encoding="utf-8",
    )
    (package_dir / "assets" / "example-query.txt").write_text(
        "maintenance mode cluster owner\n",
        encoding="utf-8",
    )
    (package_dir / "agents" / "openai.yaml").write_text(
        "display_name: Redis Maintenance Triage\npreferred_entrypoint: SKILL.md\n",
        encoding="utf-8",
    )
    return package_dir


def test_discover_skill_packages_parses_resources_and_ui_metadata(tmp_path: Path):
    package_dir = _write_skill_package(tmp_path)

    packages = discover_skill_packages(tmp_path)

    assert len(packages) == 1
    package = packages[0]
    assert package.root == package_dir.resolve()
    assert package.name == "redis-maintenance-triage"
    assert package.display_title == "Redis Maintenance Triage"
    assert package.ui_metadata["display_name"] == "Redis Maintenance Triage"
    assert [resource.path for resource in package.references] == [
        "references/maintenance-checklist.md"
    ]
    assert [resource.path for resource in package.scripts] == ["scripts/collect_context.sh"]
    assert [resource.path for resource in package.assets] == ["assets/example-query.txt"]


def test_discover_skill_packages_skips_invalid_package_and_keeps_valid_ones(tmp_path: Path, caplog):
    _write_skill_package(tmp_path, "valid-skill")
    invalid_dir = _write_skill_package(tmp_path, "invalid-skill")
    (invalid_dir / "SKILL.md").write_text(
        "---\nname: invalid-skill\n---\n\n# Invalid\n",
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        packages = discover_skill_packages(tmp_path)

    assert [package.name for package in packages] == ["valid-skill"]
    assert "Skipping invalid Agent Skills package" in caplog.text


def test_skill_package_to_documents_emits_entrypoint_and_resources(tmp_path: Path):
    _write_skill_package(tmp_path)
    package = discover_skill_packages(tmp_path)[0]

    documents = skill_package_to_documents(
        package, source_root=tmp_path, source_root_label="skills"
    )

    assert len(documents) == 4
    by_path = {document.metadata["resource_path"]: document for document in documents}
    assert set(by_path) == {
        "SKILL.md",
        "references/maintenance-checklist.md",
        "scripts/collect_context.sh",
        "assets/example-query.txt",
    }
    assert by_path["SKILL.md"].metadata["resource_kind"] == "entrypoint"
    assert by_path["references/maintenance-checklist.md"].metadata["resource_kind"] == "reference"
    assert by_path["scripts/collect_context.sh"].metadata["resource_kind"] == "script"
    assert by_path["assets/example-query.txt"].metadata["resource_kind"] == "asset"
    assert (
        by_path["references/maintenance-checklist.md"].metadata["source_document_path"]
        == "skills/redis-maintenance-triage/references/maintenance-checklist.md"
    )


def test_load_skill_package_reads_each_resource_file_once(tmp_path: Path, monkeypatch):
    package_dir = _write_skill_package(tmp_path)
    read_counts: dict[str, int] = {}
    original_safe_read_text = discovery._safe_read_text

    def _counted_safe_read_text(path: Path) -> str | None:
        read_counts[path.name] = read_counts.get(path.name, 0) + 1
        return original_safe_read_text(path)

    monkeypatch.setattr(discovery, "_safe_read_text", _counted_safe_read_text)

    package = load_skill_package(package_dir)

    assert package.references[0].content == "- maintenance mode\n- owner"
    assert read_counts["maintenance-checklist.md"] == 1
    assert read_counts["collect_context.sh"] == 1
    assert read_counts["example-query.txt"] == 1


def test_load_skill_package_preserves_entrypoint_metadata_when_body_starts_with_rule(
    tmp_path: Path,
):
    package_dir = _write_skill_package(tmp_path)
    (package_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: redis-maintenance-triage",
                "title: Redis Maintenance Triage",
                "description: Investigate maintenance mode before failover.",
                "---",
                "",
                "---",
                "example: keep-this-body",
                "---",
                "",
                "Entrypoint body",
            ]
        ),
        encoding="utf-8",
    )

    package = load_skill_package(package_dir)

    assert package.entrypoint.title == "Redis Maintenance Triage"
    assert package.entrypoint.description == "Investigate maintenance mode before failover."
    assert package.entrypoint.content.startswith("---\nexample: keep-this-body\n---")


def test_find_skill_package_root_respects_boundary(tmp_path: Path):
    (tmp_path / "SKILL.md").write_text(
        "---\nname: top-level\ndescription: outer package\n---\n",
        encoding="utf-8",
    )
    corpus_root = tmp_path / "fixtures" / "corpora" / "shared"
    corpus_root.mkdir(parents=True)
    document_path = corpus_root / "guide.md"
    document_path.write_text("# Guide\n\nBody", encoding="utf-8")

    assert find_skill_package_root(document_path) == tmp_path.resolve()
    assert find_skill_package_root(document_path, boundary=corpus_root) is None


def test_scaffold_skill_package_from_markdown_creates_package_skeleton(tmp_path: Path):
    legacy_skill = tmp_path / "legacy-skill.md"
    legacy_skill.write_text(
        "\n".join(
            [
                "---",
                "name: legacy-triage",
                "title: Legacy Triage",
                "summary: Legacy triage summary.",
                "priority: high",
                "---",
                "",
                "# Legacy Triage",
                "",
                "Confirm maintenance mode before failover.",
            ]
        ),
        encoding="utf-8",
    )

    package_dir = tmp_path / "legacy-triage"
    result = scaffold_skill_package_from_markdown(legacy_skill, package_dir)

    assert result["skill_name"] == "legacy-triage"
    assert (package_dir / "SKILL.md").is_file()
    assert (package_dir / "references" / "reference.md").is_file()
    assert (package_dir / "scripts" / "legacy-triage.sh").is_file()
    assert (package_dir / "assets" / "notes.txt").is_file()
    assert (package_dir / "agents" / "openai.yaml").is_file()
    assert "Confirm maintenance mode before failover." in (package_dir / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_scaffold_skill_package_from_markdown_allows_dotted_directory_names(tmp_path: Path):
    legacy_skill = tmp_path / "legacy-skill.md"
    legacy_skill.write_text(
        "# Legacy Triage\n\nConfirm maintenance mode before failover.\n", encoding="utf-8"
    )

    package_dir = tmp_path / "legacy-triage.v2"
    result = scaffold_skill_package_from_markdown(legacy_skill, package_dir)

    assert result["package_dir"] == str(package_dir.resolve())
    assert (package_dir / "SKILL.md").is_file()

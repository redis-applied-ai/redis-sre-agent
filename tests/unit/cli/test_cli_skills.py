"""Tests for the `skills` CLI commands."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.main import main
from redis_sre_agent.cli.skills import skills


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_main_help_lists_skills_command(cli_runner):
    result = cli_runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "skills" in result.output


def test_skills_list_json_uses_backend(cli_runner):
    helper = AsyncMock(
        return_value={
            "results_count": 1,
            "skills": [{"name": "redis-maintenance-triage", "protocol": "agent_skills_v1"}],
        }
    )

    with patch("redis_sre_agent.cli.skills.skills_check_helper", helper):
        result = cli_runner.invoke(skills, ["list", "--query", "maintenance", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["skills"][0]["name"] == "redis-maintenance-triage"
    helper.assert_awaited_once()


def test_skills_show_renders_manifest_sections(cli_runner):
    helper = AsyncMock(
        return_value={
            "skill_name": "redis-maintenance-triage",
            "protocol": "agent_skills_v1",
            "description": "Investigate maintenance mode first.",
            "references": [
                {
                    "path": "references/maintenance-checklist.md",
                    "title": "Maintenance Checklist",
                    "summary": "Evidence checklist.",
                }
            ],
            "scripts": [{"path": "scripts/collect_context.sh", "description": "Collect context."}],
            "assets": [{"path": "assets/example-query.txt"}],
            "full_content": "Entrypoint body",
        }
    )

    with patch("redis_sre_agent.cli.skills.get_skill_helper", helper):
        result = cli_runner.invoke(skills, ["show", "redis-maintenance-triage"])

    assert result.exit_code == 0, result.output
    assert "Protocol: agent_skills_v1" in result.output
    assert "references/maintenance-checklist.md" in result.output
    assert "scripts/collect_context.sh" in result.output
    assert "assets/example-query.txt" in result.output
    assert "Entrypoint body" in result.output


def test_skills_read_resource_reports_truncation(cli_runner):
    helper = AsyncMock(
        return_value={
            "skill_name": "redis-maintenance-triage",
            "resource_path": "references/maintenance-checklist.md",
            "resource_kind": "reference",
            "content": "1234567...",
            "truncated": True,
            "content_length": 15,
            "char_budget": 10,
        }
    )

    with patch("redis_sre_agent.cli.skills.get_skill_resource_helper", helper):
        result = cli_runner.invoke(
            skills,
            ["read-resource", "redis-maintenance-triage", "references/maintenance-checklist.md"],
        )

    assert result.exit_code == 0, result.output
    assert "Truncated to 10 chars from 15 chars." in result.output
    assert "1234567..." in result.output


def test_skills_scaffold_creates_package(cli_runner, tmp_path: Path):
    legacy_skill = tmp_path / "legacy.md"
    legacy_skill.write_text(
        "---\nname: legacy-triage\nsummary: Legacy summary.\n---\n\n# Legacy Triage\n\nBody\n",
        encoding="utf-8",
    )
    package_dir = tmp_path / "legacy-triage"

    result = cli_runner.invoke(skills, ["scaffold", str(legacy_skill), str(package_dir)])

    assert result.exit_code == 0, result.output
    assert (package_dir / "SKILL.md").is_file()
    assert (package_dir / "references" / "reference.md").is_file()
    assert (package_dir / "scripts" / "legacy-triage.sh").is_file()

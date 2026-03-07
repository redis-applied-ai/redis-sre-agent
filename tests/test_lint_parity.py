from pathlib import Path


def test_precommit_uses_same_ruff_commands_as_ci():
    lint_workflow = Path(".github/workflows/lint.yml").read_text(encoding="utf-8")
    precommit_config = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")

    commands = [
        "uv run ruff format --check .",
        "uv run ruff check .",
    ]

    for command in commands:
        assert f"run: {command}" in lint_workflow
        assert f"entry: {command}" in precommit_config


def test_precommit_does_not_use_ruff_autofix():
    precommit_config = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "--fix" not in precommit_config

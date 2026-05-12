"""Helpers for scaffolding Agent Skills packages from legacy markdown skills."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .discovery import _load_frontmatter

_HEADER_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _guess_description(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped.rstrip(".")
    return "Describe when this skill should be used."


def _slugify(value: str) -> str:
    normalized = _NON_ALNUM_RE.sub("-", value.strip().lower()).strip("-")
    return normalized or "skill-package"


def scaffold_skill_package_from_markdown(
    legacy_skill_path: str | Path,
    target_dir: str | Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Create an Agent Skills package skeleton from a legacy markdown skill."""

    source_path = Path(legacy_skill_path).expanduser().resolve()
    if not source_path.is_file():
        raise ValueError(f"Legacy skill does not exist: {source_path}")

    metadata, body = _load_frontmatter(source_path)
    body_title_match = _HEADER_RE.search(body)
    inferred_title = body_title_match.group(1) if body_title_match else ""
    title = str(metadata.get("title") or inferred_title or "").strip()
    name = str(metadata.get("name") or source_path.stem).strip()
    description = str(metadata.get("description") or metadata.get("summary") or "").strip()
    if not description:
        description = _guess_description(body)

    package_dir = Path(target_dir).expanduser()
    if package_dir.exists() and not package_dir.is_dir():
        raise ValueError(f"Target directory is not a directory: {package_dir}")
    if package_dir.exists() and any(package_dir.iterdir()) and not force:
        raise ValueError(f"Target directory already exists and is not empty: {package_dir}")

    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "references").mkdir(exist_ok=True)
    (package_dir / "scripts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "agents").mkdir(exist_ok=True)

    frontmatter: dict[str, Any] = {
        "name": name,
        "description": description,
        "summary": str(metadata.get("summary") or description).strip() or description,
    }
    if title and title != name:
        frontmatter["title"] = title
    if metadata.get("priority"):
        frontmatter["priority"] = metadata["priority"]
    if metadata.get("version"):
        frontmatter["version"] = metadata["version"]
    if metadata.get("pinned") is not None:
        frontmatter["pinned"] = bool(metadata["pinned"])

    entrypoint_lines = [
        "---",
        yaml.safe_dump(frontmatter, sort_keys=False).strip(),
        "---",
        "",
        body or f"# {title or name}\n\n{description}",
        "",
    ]
    (package_dir / "SKILL.md").write_text("\n".join(entrypoint_lines), encoding="utf-8")

    reference_template = "\n".join(
        [
            "---",
            yaml.safe_dump(
                {
                    "title": f"{title or name} reference",
                    "description": "Add background material or decision criteria here.",
                },
                sort_keys=False,
            ).strip(),
            "---",
            "",
            "Add supporting reference content for the skill here.",
            "",
        ]
    )
    (package_dir / "references" / "reference.md").write_text(reference_template, encoding="utf-8")

    script_name = f"{_slugify(name)}.sh"
    script_template = "\n".join(
        [
            "#!/usr/bin/env bash",
            "# Retrieval-only placeholder. This agent does not execute packaged scripts in v1.",
            "",
            'echo "Fill in external executor logic here."',
            "",
        ]
    )
    (package_dir / "scripts" / script_name).write_text(script_template, encoding="utf-8")

    (package_dir / "assets" / "notes.txt").write_text(
        "Optional text assets can live here. Binary assets stay out of model retrieval by default.\n",
        encoding="utf-8",
    )
    (package_dir / "agents" / "openai.yaml").write_text(
        yaml.safe_dump(
            {
                "display_name": title or name,
                "preferred_entrypoint": "SKILL.md",
                "output_contract": {
                    "mode": "markdown",
                    "instructions": [
                        "Add exact output-shape rules here when the response format is mandatory."
                    ],
                },
                "workflow_contract": {
                    "required_tool_calls": [],
                    "required_followups": [],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    return {
        "source_path": str(source_path),
        "package_dir": str(package_dir.resolve()),
        "skill_name": name,
        "files_created": [
            "SKILL.md",
            "references/reference.md",
            f"scripts/{script_name}",
            "assets/notes.txt",
            "agents/openai.yaml",
        ],
    }

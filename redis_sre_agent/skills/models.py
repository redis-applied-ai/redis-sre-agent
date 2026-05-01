"""Core models for Agent Skills packages."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class SkillProtocol(str, Enum):
    """Supported skill packaging protocols."""

    LEGACY_MARKDOWN = "legacy_markdown"
    AGENT_SKILLS_V1 = "agent_skills_v1"


class SkillResourceKind(str, Enum):
    """Kinds of resources inside a skill package."""

    ENTRYPOINT = "entrypoint"
    REFERENCE = "reference"
    SCRIPT = "script"
    ASSET = "asset"


@dataclass(frozen=True)
class SkillResource:
    """One materialized resource inside a skill package."""

    path: str
    kind: SkillResourceKind
    full_path: Path
    content: str | None
    mime_type: str
    encoding: str | None = "utf-8"
    indexed: bool = True
    title: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillPackage:
    """A parsed Agent Skills package rooted at a directory containing ``SKILL.md``."""

    name: str
    description: str
    root: Path
    entrypoint: SkillResource
    references: tuple[SkillResource, ...] = ()
    scripts: tuple[SkillResource, ...] = ()
    assets: tuple[SkillResource, ...] = ()
    ui_metadata: dict[str, Any] = field(default_factory=dict)
    protocol: SkillProtocol = SkillProtocol.AGENT_SKILLS_V1
    title: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def iter_resources(self) -> Iterable[SkillResource]:
        """Yield package resources in a stable order."""

        yield self.entrypoint
        yield from self.references
        yield from self.scripts
        yield from self.assets

    @property
    def display_title(self) -> str:
        """Return the human-facing skill title."""

        return str(self.title or self.name).strip() or self.name

    @property
    def has_references(self) -> bool:
        return bool(self.references)

    @property
    def has_scripts(self) -> bool:
        return bool(self.scripts)

    @property
    def has_assets(self) -> bool:
        return bool(self.assets)

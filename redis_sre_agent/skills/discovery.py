"""Filesystem discovery for Agent Skills packages."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

from redis_sre_agent.pipelines.scraper.base import (
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    SeverityLevel,
)

from .models import SkillPackage, SkillResource, SkillResourceKind

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_TEXT_SUFFIXES = {
    ".md",
    ".markdown",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".sql",
    ".js",
    ".ts",
}


def _parse_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(raw_text)
    if match is None:
        return {}, raw_text.strip()
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return metadata, match.group(2).strip()


def _load_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    raw_text = path.read_text(encoding="utf-8")
    return _parse_frontmatter(raw_text)


def _safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _normalize_relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _guess_mime_type(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type:
        return mime_type
    if path.suffix.lower() in {".md", ".markdown"}:
        return "text/markdown"
    if path.suffix.lower() in {".py", ".sh", ".bash", ".zsh"}:
        return "text/plain"
    return "application/octet-stream"


def _is_text_asset(path: Path) -> bool:
    mime_type = _guess_mime_type(path)
    if mime_type.startswith("text/"):
        return True
    return path.suffix.lower() in _TEXT_SUFFIXES


def _resource_description(path: str, metadata: dict[str, Any], fallback: str = "") -> str:
    return (
        str(metadata.get("description") or metadata.get("summary") or fallback or "").strip()
        or path
    )


def _iter_resource_paths(directory: Path) -> Iterable[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.rglob("*") if path.is_file())


def _readable_resource_paths(
    directory: Path, *, include: Callable[[Path], bool] | None = None
) -> Iterable[tuple[Path, str]]:
    for path in _iter_resource_paths(directory):
        if include is not None and not include(path):
            continue
        resource_content = _safe_read_text(path)
        if resource_content is None:
            continue
        yield path, resource_content


def find_skill_package_root(path: Path, *, boundary: Path | None = None) -> Path | None:
    """Return the package root containing ``path``, limited to ``boundary`` when provided."""

    resolved_path = path.resolve()
    boundary_path = None
    if boundary is not None:
        resolved_boundary = boundary.resolve()
        boundary_path = (
            resolved_boundary if resolved_boundary.is_dir() else resolved_boundary.parent
        )

    for candidate in (resolved_path.parent, *resolved_path.parents):
        if boundary_path is not None:
            try:
                candidate.relative_to(boundary_path)
            except ValueError:
                break
        if (candidate / "SKILL.md").is_file():
            return candidate
    return None


def load_skill_package(skill_root: Path) -> SkillPackage:
    """Load an Agent Skills package rooted at ``skill_root``."""

    skill_root = skill_root.resolve()
    entrypoint_path = skill_root / "SKILL.md"
    if not entrypoint_path.is_file():
        raise ValueError(f"Skill package is missing SKILL.md: {skill_root}")

    metadata, content = _load_frontmatter(entrypoint_path)
    name = str(metadata.get("name") or skill_root.name).strip()
    description = str(metadata.get("description") or metadata.get("summary") or "").strip()
    if not name:
        raise ValueError(f"Skill package name is required: {skill_root}")
    if not description:
        raise ValueError(f"Skill package description is required: {skill_root}")

    title = str(metadata.get("title") or metadata.get("display_name") or name).strip() or name
    ui_metadata: dict[str, Any] = {}
    ui_metadata_path = skill_root / "agents" / "openai.yaml"
    if ui_metadata_path.is_file():
        payload = yaml.safe_load(ui_metadata_path.read_text(encoding="utf-8")) or {}
        if isinstance(payload, dict):
            ui_metadata = payload

    def _build_resource(
        path: Path,
        kind: SkillResourceKind,
        *,
        resource_content: str | None = None,
        resource_metadata: dict[str, Any] | None = None,
        default_title: str | None = None,
        default_description: str = "",
    ) -> SkillResource:
        rel_path = _normalize_relpath(path, skill_root)
        parsed_metadata = dict(resource_metadata or {})
        if resource_content is None:
            resource_content = _safe_read_text(path)
        indexed = resource_content is not None and (
            kind != SkillResourceKind.ASSET or _is_text_asset(path)
        )
        if path.suffix.lower() in {".md", ".markdown"} and resource_content:
            frontmatter_metadata, stripped_content = _parse_frontmatter(resource_content)
            if frontmatter_metadata:
                parsed_metadata = frontmatter_metadata
            resource_content = stripped_content
        return SkillResource(
            path=rel_path,
            kind=kind,
            full_path=path,
            content=resource_content,
            mime_type=_guess_mime_type(path),
            indexed=indexed,
            title=str(parsed_metadata.get("title") or default_title or path.stem).strip()
            or path.stem,
            description=_resource_description(
                rel_path, parsed_metadata, fallback=default_description
            ),
            metadata=parsed_metadata,
        )

    entrypoint = _build_resource(
        entrypoint_path,
        SkillResourceKind.ENTRYPOINT,
        resource_content=content,
        resource_metadata=metadata,
        default_title=title,
        default_description=description,
    )
    references = tuple(
        _build_resource(path, SkillResourceKind.REFERENCE, resource_content=resource_content)
        for path, resource_content in _readable_resource_paths(skill_root / "references")
    )
    scripts = tuple(
        _build_resource(
            path,
            SkillResourceKind.SCRIPT,
            resource_content=resource_content,
            default_description=f"Script resource at {path.name}",
        )
        for path, resource_content in _readable_resource_paths(skill_root / "scripts")
    )
    assets = tuple(
        _build_resource(path, SkillResourceKind.ASSET, resource_content=resource_content)
        for path, resource_content in _readable_resource_paths(
            skill_root / "assets", include=_is_text_asset
        )
    )

    return SkillPackage(
        name=name,
        description=description,
        title=title,
        summary=str(metadata.get("summary") or description).strip() or description,
        root=skill_root,
        entrypoint=entrypoint,
        references=references,
        scripts=scripts,
        assets=assets,
        ui_metadata=ui_metadata,
        metadata=metadata,
    )


def discover_skill_packages(root: Path) -> list[SkillPackage]:
    """Discover Agent Skills packages below ``root``."""

    root = root.resolve()
    if not root.exists():
        return []

    packages: list[SkillPackage] = []
    candidates: list[Path] = []
    if (root / "SKILL.md").is_file():
        candidates.append(root)
    candidates.extend(sorted(path.parent for path in root.rglob("SKILL.md") if path.is_file()))

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        packages.append(load_skill_package(resolved))
    return packages


def _skill_package_manifest(package: SkillPackage) -> dict[str, Any]:
    return {
        "name": package.name,
        "title": package.display_title,
        "description": package.description,
        "protocol": package.protocol.value,
        "references": [
            {"path": resource.path, "title": resource.title, "description": resource.description}
            for resource in package.references
        ],
        "scripts": [
            {"path": resource.path, "title": resource.title, "description": resource.description}
            for resource in package.scripts
        ],
        "assets": [
            {"path": resource.path, "title": resource.title, "description": resource.description}
            for resource in package.assets
        ],
        "ui_metadata": package.ui_metadata,
    }


def _package_hash(package: SkillPackage) -> str:
    digest = hashlib.sha256()
    for resource in package.iter_resources():
        digest.update(resource.path.encode("utf-8"))
        if resource.content is not None:
            digest.update(resource.content.encode("utf-8"))
    return digest.hexdigest()[:16]


def skill_package_to_documents(
    package: SkillPackage,
    *,
    source_root: Path,
    source_root_label: str | None = None,
) -> list[ScrapedDocument]:
    """Convert an Agent Skills package into ``ScrapedDocument`` resources."""

    source_root = source_root.resolve()
    root_label = str(source_root_label or source_root.name or "skills").strip().strip("/")
    package_hash = _package_hash(package)
    manifest_json = json.dumps(_skill_package_manifest(package), sort_keys=True)
    documents: list[ScrapedDocument] = []

    for resource in package.iter_resources():
        if resource.content is None or not resource.indexed:
            continue

        relative_package_path = package.root.relative_to(source_root).as_posix()
        source_document_path = f"{root_label}/{relative_package_path}/{resource.path}".strip("/")
        metadata = {
            "name": package.name,
            "summary": package.summary or package.description,
            "priority": str(package.metadata.get("priority") or "normal").strip().lower()
            or "normal",
            "version": str(package.metadata.get("version") or "latest").strip() or "latest",
            "pinned": bool(package.metadata.get("pinned", False)),
            "source_document_path": source_document_path,
            "source_document_scope": f"{root_label}/",
            "skill_protocol": package.protocol.value,
            "resource_kind": resource.kind.value,
            "resource_path": resource.path,
            "mime_type": resource.mime_type,
            "encoding": resource.encoding or "",
            "package_hash": package_hash,
            "entrypoint": resource.kind is SkillResourceKind.ENTRYPOINT,
            "has_references": package.has_references,
            "has_scripts": package.has_scripts,
            "has_assets": package.has_assets,
            "resource_title": resource.title or "",
            "resource_description": resource.description or "",
            "skill_description": package.description,
            "skill_manifest": manifest_json,
            "ui_metadata": json.dumps(package.ui_metadata, sort_keys=True),
            **({"title": package.display_title} if package.display_title else {}),
        }
        documents.append(
            ScrapedDocument(
                title=package.display_title
                if resource.kind is SkillResourceKind.ENTRYPOINT
                else (resource.title or f"{package.display_title}: {resource.path}"),
                content=resource.content,
                source_url=f"file://{resource.full_path}",
                category=DocumentCategory.SHARED,
                doc_type=DocumentType.SKILL,
                severity=SeverityLevel.LOW,
                metadata=metadata,
            )
        )
    return documents

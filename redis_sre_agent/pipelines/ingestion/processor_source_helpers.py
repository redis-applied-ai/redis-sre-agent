"""Helpers for source-document parsing and metadata normalization."""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...pipelines.scraper.base import (
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    SeverityLevel,
)

logger = logging.getLogger(__name__)

CATEGORY_NAME_MAP = {
    "oss": DocumentCategory.OSS,
    "enterprise": DocumentCategory.ENTERPRISE,
    "shared": DocumentCategory.SHARED,
    "cloud": DocumentCategory.SHARED,
}

SEVERITY_NAME_MAP = {
    "critical": SeverityLevel.CRITICAL,
    "high": SeverityLevel.HIGH,
    "warning": SeverityLevel.MEDIUM,
    "medium": SeverityLevel.MEDIUM,
    "normal": SeverityLevel.MEDIUM,
    "low": SeverityLevel.LOW,
    "info": SeverityLevel.LOW,
}

RESERVED_METADATA_KEYS = {
    "file_path",
    "file_size",
    "original_category",
    "original_severity",
    "original_doc_type",
    "determined_category",
    "doc_type",
    "name",
    "summary",
    "priority",
    "pinned",
    "source_document_path",
    "source_document_scope",
}


def parse_bool(value: Any, default: bool = False) -> bool:
    """Best-effort boolean parser for chunk metadata fields."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    return default


def strip_yaml_front_matter(text: str) -> tuple[str, bool]:
    """Remove YAML front-matter delimited by leading --- blocks."""
    if not text.startswith("---"):
        return text, False

    try:
        end_idx = text.find("\n---", 3)
        if end_idx == -1:
            return text, False
        closing_line_end = end_idx + len("\n---")
        remainder = text[closing_line_end:]
        if remainder.startswith("\n"):
            remainder = remainder[1:]
        return remainder, True
    except Exception:
        return text, False


def normalize_metadata_key(key: str) -> str:
    """Normalize metadata keys into snake_case aliases."""
    normalized = re.sub(r"[\s-]+", "_", key.strip().lower())
    return re.sub(r"[^\w]", "", normalized)


def parse_markdown_metadata(content: str) -> Dict[str, str]:
    """Extract metadata from a markdown source document."""
    metadata: Dict[str, str] = {}
    front_matter_match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", content, re.DOTALL)
    if front_matter_match:
        front_matter = front_matter_match.group(1)
        for line in front_matter.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[normalize_metadata_key(key)] = value.strip().strip('"').strip("'")

    title_match = re.search(r"^# (.+)", content, re.MULTILINE)
    if title_match and "title" not in metadata:
        metadata["title"] = title_match.group(1).strip()

    metadata_pattern = r"^\*\*([^*]+)\*\*:\s*(.+)$"
    for match in re.finditer(metadata_pattern, content, re.MULTILINE):
        key = normalize_metadata_key(match.group(1))
        if key in metadata:
            continue
        metadata[key] = match.group(2).strip()

    return metadata


def normalize_doc_type(doc_type_raw: str) -> tuple[DocumentType, str]:
    """Normalize canonical doc_type values."""
    normalized = re.sub(r"[\s-]+", "_", (doc_type_raw or "").strip().lower())
    if not normalized:
        normalized = "knowledge"

    try:
        return DocumentType(normalized), normalized
    except ValueError:
        logger.debug("Unknown document type '%s'; defaulting to knowledge", doc_type_raw)
        return DocumentType.KNOWLEDGE, "knowledge"


def normalize_priority(priority_raw: Any) -> str:
    """Normalize priority values to the ADR enum."""
    normalized = str(priority_raw or "").strip().lower()
    if normalized in {"low", "normal", "high", "critical"}:
        return normalized
    return "normal"


def find_source_documents_root(source_dir: Path) -> Path:
    """Resolve the canonical source_documents root when ingesting a subtree."""
    resolved_source_dir = source_dir.resolve()
    for candidate in (resolved_source_dir, *resolved_source_dir.parents):
        if candidate.name == "source_documents":
            return candidate
    return resolved_source_dir


def resolve_source_document_identity(md_file: Path, source_dir: Path) -> tuple[str, str]:
    """Return the stable source path and scope prefix for a source document."""
    resolved_file = md_file.resolve()
    resolved_source_dir = source_dir.resolve()
    source_root = find_source_documents_root(source_dir)

    try:
        source_document_path = resolved_file.relative_to(source_root).as_posix()
    except ValueError:
        source_document_path = resolved_file.relative_to(resolved_source_dir).as_posix()

    try:
        scope_prefix = resolved_source_dir.relative_to(source_root).as_posix()
    except ValueError:
        scope_prefix = ""

    if scope_prefix in {".", ""}:
        return source_document_path, ""
    return source_document_path, f"{scope_prefix.rstrip('/')}/"


def determine_document_category(md_file: Path, metadata: Dict[str, Any]) -> DocumentCategory:
    """Determine document category from explicit metadata or directory structure."""
    explicit_category = metadata.get("category", "").lower()
    if explicit_category in CATEGORY_NAME_MAP:
        return CATEGORY_NAME_MAP[explicit_category]

    for part in md_file.parts:
        if part in CATEGORY_NAME_MAP:
            return CATEGORY_NAME_MAP[part]

    return DocumentCategory.SHARED


def create_scraped_document_from_markdown(
    md_file: Path, source_dir: Optional[Path] = None
) -> ScrapedDocument:
    """Convert a markdown file into a ScrapedDocument."""
    content = md_file.read_text(encoding="utf-8")
    metadata = parse_markdown_metadata(content)
    source_document_path = ""
    source_document_scope = ""
    if source_dir is not None:
        source_document_path, source_document_scope = resolve_source_document_identity(
            md_file, source_dir
        )

    title = metadata.get("title", md_file.stem.replace("-", " ").title())
    category = determine_document_category(md_file, metadata)
    priority = normalize_priority(metadata.get("priority"))
    severity_str = str(metadata.get("severity") or priority).strip().lower()

    severity = SEVERITY_NAME_MAP.get(severity_str.lower(), SeverityLevel.MEDIUM)

    doc_type_raw = str(metadata.get("doc_type", "knowledge"))
    doc_type, normalized_doc_type = normalize_doc_type(doc_type_raw)
    name = str(metadata.get("name") or md_file.stem).strip() or md_file.stem
    summary_raw = metadata.get("summary")
    summary = str(summary_raw).strip() if summary_raw is not None else ""
    pinned = parse_bool(metadata.get("pinned"), default=False)
    explicit_url = str(metadata.get("url") or "").strip()
    passthrough_metadata = {
        key: value for key, value in metadata.items() if key not in RESERVED_METADATA_KEYS
    }

    return ScrapedDocument(
        title=title,
        source_url=explicit_url or f"file://{md_file.absolute()}",
        content=content,
        category=category,
        doc_type=doc_type,
        severity=severity,
        metadata={
            **passthrough_metadata,
            "file_path": str(md_file),
            "file_size": md_file.stat().st_size,
            "original_category": metadata.get("category", "shared").lower(),
            "original_severity": severity_str,
            "original_doc_type": doc_type_raw,
            "determined_category": category.value,
            "doc_type": normalized_doc_type,
            "name": name,
            "summary": summary or None,
            "priority": priority,
            "pinned": pinned,
            "source_document_path": source_document_path,
            "source_document_scope": source_document_scope,
        },
    )


def find_markdown_files(source_dir: Path) -> List[Path]:
    """Return markdown source files, excluding README placeholders."""
    return sorted(
        (path for path in source_dir.rglob("*.md") if path.name.lower() != "readme.md"),
        key=lambda path: path.as_posix(),
    )

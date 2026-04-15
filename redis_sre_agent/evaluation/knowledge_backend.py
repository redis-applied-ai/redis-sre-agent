"""Fixture-backed eval knowledge backend."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from redis_sre_agent.evaluation.injection import EvalKnowledgeBackend
from redis_sre_agent.evaluation.scenarios import EvalScenario

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}
_SPECIAL_DOC_TYPES = {"skill", "support_ticket"}
_PACK_METADATA_FILENAMES = ("manifest.yaml", "manifest.yml", "metadata.yaml", "metadata.yml")
_PACK_CATEGORY_DIRS = ("documents", "skills", "tickets")
_FIXTURE_DOCUMENT_SUFFIXES = {".json", ".md", ".markdown", ".txt", ".yaml", ".yml"}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _coerce_non_negative_int(value: Any, *, default: int) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default
    return max(coerced, 0)


def _coerce_positive_int(value: Any, *, default: int) -> int:
    return max(_coerce_non_negative_int(value, default=default), 1)


def _version_matches(document_version: str, requested_version: Optional[str]) -> bool:
    normalized_document_version = str(document_version or "latest").strip() or "latest"
    if requested_version is None:
        return True
    normalized_requested_version = str(requested_version or "latest").strip() or "latest"
    if normalized_requested_version == "latest":
        return normalized_document_version == "latest"
    return normalized_document_version == normalized_requested_version


def _summarize_content(content: str, max_len: int = 150) -> str:
    compact = " ".join(str(content or "").split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[:max_len].rstrip()}..."


def _load_frontmatter_document(path: Path) -> tuple[dict[str, Any], str]:
    raw_text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw_text)
    if match is None:
        return {}, raw_text.strip()
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return metadata, match.group(2).strip()


def _load_structured_document(path: Path) -> tuple[dict[str, Any], str]:
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        payload = json.loads(raw_text)
    else:
        payload = yaml.safe_load(raw_text) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Structured knowledge fixture must contain an object: {path}")
    content = str(payload.pop("content", payload.pop("full_content", ""))).strip()
    return payload, content


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Fixture metadata must be a mapping: {path}")
    return payload


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    normalized = str(value).strip()
    return [normalized] if normalized else []


def _scenario_provenance_defaults(scenario: EvalScenario) -> dict[str, Any]:
    return {
        "source_kind": scenario.provenance.source_kind.value,
        "source_pack": scenario.provenance.source_pack,
        "source_pack_version": scenario.provenance.source_pack_version,
        "derived_from": list(scenario.provenance.derived_from),
        "review_status": scenario.provenance.golden.review_status.value,
        "reviewed_by": scenario.provenance.golden.reviewed_by,
        "exemplar_sources": list(scenario.provenance.golden.exemplar_sources),
    }


def _normalize_provenance_metadata(
    payload: dict[str, Any],
    *,
    fallback_source_pack: str | None = None,
    fallback_source_pack_version: str | None = None,
) -> dict[str, Any]:
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        provenance = {}
    golden = payload.get("golden")
    if not isinstance(golden, dict):
        golden = {}

    source_pack = (
        provenance.get("source_pack") or payload.get("source_pack") or fallback_source_pack
    )
    source_pack_version = (
        provenance.get("source_pack_version")
        or payload.get("source_pack_version")
        or payload.get("version")
        or fallback_source_pack_version
    )

    return {
        "source_kind": str(
            provenance.get("source_kind") or payload.get("source_kind") or ""
        ).strip()
        or None,
        "source_pack": str(source_pack).strip() or None if source_pack is not None else None,
        "source_pack_version": (
            str(source_pack_version).strip() or None if source_pack_version is not None else None
        ),
        "derived_from": _normalize_string_list(
            provenance.get("derived_from", payload.get("derived_from"))
        ),
        "review_status": str(
            golden.get("review_status") or payload.get("review_status") or ""
        ).strip()
        or None,
        "reviewed_by": str(golden.get("reviewed_by") or payload.get("reviewed_by") or "").strip()
        or None,
        "exemplar_sources": _normalize_string_list(
            golden.get("exemplar_sources", payload.get("exemplar_sources"))
        ),
    }


def _merge_provenance_metadata(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key in (
        "source_kind",
        "source_pack",
        "source_pack_version",
        "review_status",
        "reviewed_by",
    ):
        value = override.get(key)
        if value not in {None, ""}:
            merged[key] = value

    for key in ("derived_from", "exemplar_sources"):
        values = override.get(key)
        if values:
            merged[key] = list(values)
        else:
            merged.setdefault(key, [])

    return merged


def _pack_metadata_path(pack_root: Path) -> Path | None:
    for filename in _PACK_METADATA_FILENAMES:
        candidate = pack_root / filename
        if candidate.exists():
            return candidate
    return None


def _looks_like_pack_root(path: Path) -> bool:
    if not path.is_dir():
        return False
    if _pack_metadata_path(path) is not None:
        return True
    return any((path / category).is_dir() for category in _PACK_CATEGORY_DIRS)


def _iter_fixture_documents(pack_root: Path) -> list[Path]:
    discovered: list[Path] = []
    for category in _PACK_CATEGORY_DIRS:
        category_dir = pack_root / category
        if not category_dir.is_dir():
            continue
        discovered.extend(
            sorted(
                candidate
                for candidate in category_dir.rglob("*")
                if candidate.is_file() and candidate.suffix.lower() in _FIXTURE_DOCUMENT_SUFFIXES
            )
        )

    if discovered:
        return discovered

    return sorted(
        candidate
        for candidate in pack_root.rglob("*")
        if candidate.is_file()
        and candidate.name not in _PACK_METADATA_FILENAMES
        and candidate.suffix.lower() in _FIXTURE_DOCUMENT_SUFFIXES
    )


def _pack_provenance_for_root(
    pack_root: Path,
    *,
    default_provenance: dict[str, Any],
) -> dict[str, Any]:
    payload = (
        _load_yaml_mapping(_pack_metadata_path(pack_root)) if _pack_metadata_path(pack_root) else {}
    )
    normalized = _normalize_provenance_metadata(
        payload,
        fallback_source_pack=pack_root.parent.name,
        fallback_source_pack_version=pack_root.name,
    )
    return _merge_provenance_metadata(default_provenance, normalized)


def _resolve_fixture_paths(
    path: Path,
    *,
    default_provenance: dict[str, Any],
) -> list[tuple[Path, dict[str, Any]]]:
    if path.is_dir() and _looks_like_pack_root(path):
        pack_provenance = _pack_provenance_for_root(path, default_provenance=default_provenance)
        return [(candidate, pack_provenance) for candidate in _iter_fixture_documents(path)]

    if path.is_file() and path.name in _PACK_METADATA_FILENAMES:
        pack_root = path.parent
        pack_provenance = _pack_provenance_for_root(
            pack_root, default_provenance=default_provenance
        )
        return [(candidate, pack_provenance) for candidate in _iter_fixture_documents(pack_root)]

    for parent in path.parents:
        if not _looks_like_pack_root(parent):
            continue
        pack_provenance = _pack_provenance_for_root(parent, default_provenance=default_provenance)
        return [(path, pack_provenance)]

    return [(path, dict(default_provenance))]


def _infer_doc_type(path: Path, metadata: dict[str, Any]) -> str:
    explicit = str(metadata.get("doc_type", "")).strip().lower()
    if explicit:
        return explicit
    parent_name = path.parent.name.strip().lower()
    if parent_name == "skills":
        return "skill"
    if parent_name == "tickets":
        return "support_ticket"
    return "knowledge"


def _infer_index_type(doc_type: str) -> str:
    if doc_type == "skill":
        return "skills"
    if doc_type == "support_ticket":
        return "support_tickets"
    return "knowledge"


def _default_document_hash(path: Path, name: str) -> str:
    normalized_name = str(name or "").strip()
    if normalized_name:
        return normalized_name
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
    return f"doc-{digest[:12]}"


@dataclass(frozen=True)
class FixtureKnowledgeDocument:
    document_hash: str
    title: str
    name: str
    content: str
    source: str
    category: str
    doc_type: str
    severity: str
    summary: str
    priority: str
    pinned: bool
    frontmatter_pinned: bool
    version: str
    product_labels: list[str]
    index_type: str
    provenance: dict[str, Any]

    def provenance_row(self) -> dict[str, Any]:
        return {
            "source_kind": self.provenance.get("source_kind"),
            "source_pack": self.provenance.get("source_pack"),
            "source_pack_version": self.provenance.get("source_pack_version"),
            "derived_from": list(self.provenance.get("derived_from", [])),
            "review_status": self.provenance.get("review_status"),
            "reviewed_by": self.provenance.get("reviewed_by"),
            "exemplar_sources": list(self.provenance.get("exemplar_sources", [])),
            "provenance": dict(self.provenance),
        }

    def search_row(self) -> dict[str, Any]:
        row = {
            "id": self.document_hash,
            "document_hash": self.document_hash,
            "chunk_index": 0,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "category": self.category,
            "doc_type": self.doc_type,
            "name": self.name,
            "summary": self.summary,
            "priority": self.priority,
            "pinned": self.pinned,
            "severity": self.severity,
            "version": self.version,
            "product_labels": list(self.product_labels),
            "total_chunks": 1,
        }
        row.update(self.provenance_row())
        return row

    def pinned_row(self, *, full_content: str, truncated: bool) -> dict[str, Any]:
        row = self.search_row()
        row.update(
            {
                "full_content": full_content,
                "truncated": truncated,
                "index_type": self.index_type,
            }
        )
        return row


class FixtureKnowledgeBackend(EvalKnowledgeBackend):
    """Scenario-backed in-memory knowledge backend for eval runs."""

    def __init__(self, documents: Iterable[FixtureKnowledgeDocument]) -> None:
        self._documents = list(documents)

    @classmethod
    def from_scenario(cls, scenario: EvalScenario) -> "FixtureKnowledgeBackend":
        pinned_references = {
            str(reference) for reference in (scenario.knowledge.pinned_documents or [])
        }
        default_provenance = _scenario_provenance_defaults(scenario)
        seen_paths: set[Path] = set()
        documents: list[FixtureKnowledgeDocument] = []
        for reference in scenario.knowledge.pinned_documents + scenario.knowledge.corpus:
            path = scenario.resolve_fixture_path(reference)
            for resolved_path, provenance in _resolve_fixture_paths(
                path.resolve(),
                default_provenance=default_provenance,
            ):
                if resolved_path in seen_paths:
                    continue
                seen_paths.add(resolved_path)
                documents.append(
                    _load_fixture_document(
                        resolved_path,
                        pinned=str(reference) in pinned_references,
                        default_version=scenario.knowledge.version,
                        default_provenance=provenance,
                    )
                )
        return cls(documents)

    def _docs_for_index(
        self,
        *,
        index_type: str,
        version: Optional[str],
        include_special_document_types: bool = False,
    ) -> list[FixtureKnowledgeDocument]:
        normalized_index_type = str(index_type or "knowledge").strip().lower() or "knowledge"
        docs = [
            document
            for document in self._documents
            if document.index_type == normalized_index_type
            and _version_matches(document.version, version)
        ]
        if normalized_index_type == "knowledge" and not include_special_document_types:
            docs = [
                document
                for document in docs
                if document.doc_type not in _SPECIAL_DOC_TYPES and not document.pinned
            ]
        return docs

    def _rank_documents(
        self,
        documents: Iterable[FixtureKnowledgeDocument],
        *,
        query: str,
    ) -> list[FixtureKnowledgeDocument]:
        normalized_query = _normalize_text(query)
        if not normalized_query:
            return sorted(documents, key=lambda document: document.name.lower())

        quoted_query = (
            normalized_query[1:-1]
            if normalized_query.startswith('"') and normalized_query.endswith('"')
            else None
        )
        query_tokens = [token for token in normalized_query.replace('"', "").split() if token]

        def _rank(document: FixtureKnowledgeDocument) -> tuple[int, int, int, str]:
            name = _normalize_text(document.name)
            title = _normalize_text(document.title)
            source = _normalize_text(document.source)
            content = _normalize_text(document.content)
            summary = _normalize_text(document.summary)
            if normalized_query in {name, title, source, _normalize_text(document.document_hash)}:
                exact_rank = 0
            elif quoted_query and quoted_query in f"{title} {summary} {content}":
                exact_rank = 1
            elif normalized_query in f"{title} {summary} {content}":
                exact_rank = 2
            else:
                exact_rank = 3

            haystack = f"{name} {title} {summary} {content} {source}"
        token_hits = sum(1 for token in query_tokens if token in haystack)
        frontmatter_penalty = 1 if document.frontmatter_pinned and not document.pinned else 0
        return (
            exact_rank,
            -token_hits,
            frontmatter_penalty,
            _PRIORITY_ORDER.get(document.priority, _PRIORITY_ORDER["normal"]),
            document.name.lower(),
        )

        return sorted(documents, key=_rank)

    async def search_knowledge_base(
        self,
        *,
        query: str,
        category: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        distance_threshold: Optional[float] = 0.8,
        hybrid_search: bool = False,
        version: Optional[str] = "latest",
        index_type: str = "knowledge",
        include_special_document_types: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        effective_limit = _coerce_positive_int(limit, default=10)
        effective_offset = _coerce_non_negative_int(offset, default=0)
        documents = self._docs_for_index(
            index_type=index_type,
            version=version,
            include_special_document_types=include_special_document_types,
        )
        if category is not None:
            normalized_category = str(category).strip().lower()
            documents = [
                document
                for document in documents
                if document.category.lower() == normalized_category
            ]
        if doc_type is not None:
            normalized_type = str(doc_type).strip().lower()
            documents = [document for document in documents if document.doc_type == normalized_type]

        ranked_documents = self._rank_documents(documents, query=query)
        paged_documents = ranked_documents[effective_offset : effective_offset + effective_limit]
        return {
            "query": query,
            "category": category,
            "doc_type": doc_type,
            "version": version,
            "limit": effective_limit,
            "offset": effective_offset,
            "distance_threshold": distance_threshold,
            "hybrid_search": hybrid_search,
            "index_type": index_type,
            "results_count": len(paged_documents),
            "results": [document.search_row() for document in paged_documents],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def skills_check(
        self,
        *,
        query: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        version: Optional[str] = "latest",
        distance_threshold: Optional[float] = 0.8,
        **_: Any,
    ) -> dict[str, Any]:
        effective_limit = _coerce_positive_int(limit, default=20)
        effective_offset = _coerce_non_negative_int(offset, default=0)
        skill_documents = [
            document
            for document in self._docs_for_index(index_type="skills", version=version)
            if not document.pinned
        ]
        if query:
            ordered_documents = self._rank_documents(skill_documents, query=query)
        else:
            ordered_documents = sorted(skill_documents, key=lambda document: document.name.lower())
        paged_documents = ordered_documents[effective_offset : effective_offset + effective_limit]
        return {
            "query": query,
            "version": version,
            "offset": effective_offset,
            "limit": effective_limit,
            "results_count": len(paged_documents),
            "total_fetched": len(ordered_documents),
            "skills": [
                {
                    "name": document.name,
                    "document_hash": document.document_hash,
                    "title": document.title,
                    "source": document.source,
                    "version": document.version,
                    "priority": document.priority,
                    "summary": document.summary,
                    "index_type": document.index_type,
                }
                for document in paged_documents
            ],
            "distance_threshold": distance_threshold,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_skill(
        self,
        *,
        skill_name: str,
        version: Optional[str] = "latest",
        **_: Any,
    ) -> dict[str, Any]:
        normalized_name = _normalize_text(skill_name)
        for document in self._docs_for_index(index_type="skills", version=version):
            if (
                _normalize_text(document.name) == normalized_name
                or _normalize_text(document.title) == normalized_name
            ):
                return {
                    "skill_name": document.name,
                    "full_content": document.content,
                }
        available_skills = await self.skills_check(query=skill_name, limit=50, version=version)
        return {
            "skill_name": skill_name,
            "error": "Skill not found",
            "available_skills": [
                str(skill.get("name", "")) for skill in available_skills.get("skills", [])[:50]
            ],
        }

    async def search_support_tickets(
        self,
        *,
        query: str,
        limit: int = 10,
        offset: int = 0,
        distance_threshold: Optional[float] = 0.8,
        hybrid_search: bool = False,
        version: Optional[str] = "latest",
        **_: Any,
    ) -> dict[str, Any]:
        result = await self.search_knowledge_base(
            query=query,
            limit=limit,
            offset=offset,
            distance_threshold=distance_threshold,
            hybrid_search=hybrid_search,
            version=version,
            index_type="support_tickets",
        )
        tickets = []
        for row in result["results"]:
            row_with_ticket = dict(row)
            row_with_ticket["ticket_id"] = (
                row_with_ticket.get("name") or row_with_ticket["document_hash"]
            )
            tickets.append(row_with_ticket)
        result.update(
            {
                "tickets": tickets,
                "ticket_count": len(tickets),
                "doc_type": "support_ticket",
                "doc_type_filter": "support_ticket",
                "results": tickets,
                "results_count": len(tickets),
            }
        )
        return result

    async def get_support_ticket(
        self,
        *,
        ticket_id: str,
        **_: Any,
    ) -> dict[str, Any]:
        normalized_ticket_id = _normalize_text(ticket_id)
        for document in self._docs_for_index(index_type="support_tickets", version=None):
            if normalized_ticket_id in {
                _normalize_text(document.name),
                _normalize_text(document.title),
                _normalize_text(document.document_hash),
            }:
                fragment = document.search_row()
                return {
                    "ticket_id": ticket_id,
                    "document_hash": document.document_hash,
                    "title": document.title,
                    "source": document.source,
                    "doc_type": document.doc_type,
                    "priority": document.priority,
                    "summary": document.summary,
                    "fragments_count": 1,
                    "fragments": [fragment],
                    "full_content": document.content,
                    "metadata": {
                        "name": document.name,
                        "summary": document.summary,
                        "priority": document.priority,
                        "pinned": document.pinned,
                        **document.provenance_row(),
                    },
                }
        return {"ticket_id": ticket_id, "error": "Support ticket not found"}

    async def get_pinned_documents(
        self,
        *,
        version: Optional[str] = "latest",
        limit: int = 50,
        content_char_budget: int = 12000,
        **_: Any,
    ) -> dict[str, Any]:
        effective_limit = _coerce_positive_int(limit, default=50)
        effective_budget = _coerce_non_negative_int(content_char_budget, default=12000)
        pinned_documents = [
            document
            for document in self._documents
            if document.pinned and _version_matches(document.version, version)
        ]
        pinned_documents = sorted(
            pinned_documents,
            key=lambda document: (
                _PRIORITY_ORDER.get(document.priority, _PRIORITY_ORDER["normal"]),
                document.name.lower(),
            ),
        )[:effective_limit]

        used_chars = 0
        rendered_documents = []
        for document in pinned_documents:
            remaining_budget = effective_budget - used_chars
            if remaining_budget <= 0:
                break

            full_content = document.content
            if len(full_content) <= remaining_budget:
                rendered_documents.append(
                    document.pinned_row(full_content=full_content, truncated=False)
                )
                used_chars += len(full_content)
                continue

            if remaining_budget > 3:
                truncated_content = f"{full_content[: remaining_budget - 3].rstrip()}..."
                rendered_documents.append(
                    document.pinned_row(full_content=truncated_content, truncated=True)
                )
            break

        return {
            "version": version,
            "limit": effective_limit,
            "total_fetched": len(pinned_documents),
            "content_char_budget": content_char_budget,
            "results_count": len(rendered_documents),
            "truncated": len(rendered_documents) < len(pinned_documents)
            or any(document.get("truncated") for document in rendered_documents),
            "pinned_documents": rendered_documents,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_all_document_fragments(
        self,
        *,
        document_hash: str,
        version: Optional[str] = "latest",
        include_metadata: bool = True,
        index_type: str = "knowledge",
        **_: Any,
    ) -> dict[str, Any]:
        for document in self._docs_for_index(
            index_type=index_type,
            version=version,
            include_special_document_types=True,
        ):
            if document.document_hash == document_hash:
                fragment = document.search_row()
                result = {
                    "document_hash": document.document_hash,
                    "index_type": document.index_type,
                    "fragments_count": 1,
                    "fragments": [fragment],
                    "title": document.title,
                    "source": document.source,
                    "category": document.category,
                    "doc_type": document.doc_type,
                    "name": document.name,
                    "summary": document.summary,
                    "priority": document.priority,
                    "pinned": document.pinned,
                }
                if include_metadata:
                    result["metadata"] = {
                        "name": document.name,
                        "summary": document.summary,
                        "priority": document.priority,
                        "pinned": document.pinned,
                        "product_labels": list(document.product_labels),
                        "version": document.version,
                        **document.provenance_row(),
                    }
                return result
        return {
            "document_hash": document_hash,
            "error": "No fragments found for this document",
            "fragments": [],
        }

    async def get_related_document_fragments(
        self,
        *,
        document_hash: str,
        chunk_index: int | None = None,
        window: int = 2,
        current_chunk_index: int | None = None,
        context_window: int | None = None,
        version: Optional[str] = "latest",
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = await self.get_all_document_fragments(
            document_hash=document_hash,
            version=version,
            include_metadata=True,
            index_type=kwargs.get("index_type", "knowledge"),
        )
        if "error" in result:
            return result
        active_chunk_index = current_chunk_index if current_chunk_index is not None else chunk_index
        active_window = context_window if context_window is not None else window
        if active_chunk_index is None:
            return result

        normalized_chunk_index = int(active_chunk_index)
        normalized_window = max(int(active_window), 0)
        related_fragments = []
        for fragment in result.get("fragments", []):
            fragment_chunk_index = int(fragment.get("chunk_index", 0) or 0)
            if abs(fragment_chunk_index - normalized_chunk_index) > normalized_window:
                continue
            related_fragment = dict(fragment)
            related_fragment["is_target_chunk"] = fragment_chunk_index == normalized_chunk_index
            related_fragments.append(related_fragment)
        result.update(
            {
                "current_chunk_index": normalized_chunk_index,
                "context_window": normalized_window,
                "related_count": len(related_fragments),
                "related_fragments": related_fragments,
            }
        )
        return result


def _load_fixture_document(
    path: Path,
    *,
    pinned: bool,
    default_version: str,
    default_provenance: dict[str, Any],
) -> FixtureKnowledgeDocument:
    if path.suffix.lower() in {".yaml", ".yml", ".json"}:
        metadata, content = _load_structured_document(path)
    else:
        metadata, content = _load_frontmatter_document(path)

    name = str(metadata.get("name") or metadata.get("title") or path.stem).strip()
    title = str(metadata.get("title") or name).strip()
    doc_type = _infer_doc_type(path, metadata)
    version = str(metadata.get("version") or default_version or "latest").strip() or "latest"
    priority = str(metadata.get("priority") or "normal").strip().lower() or "normal"
    document_hash = str(metadata.get("document_hash") or _default_document_hash(path, name)).strip()
    summary = str(metadata.get("summary") or _summarize_content(content)).strip()
    source = str(metadata.get("source") or path.as_posix()).strip()
    category = str(metadata.get("category") or "").strip()
    severity = str(metadata.get("severity") or "").strip()
    raw_product_labels = metadata.get("product_labels") or []
    if isinstance(raw_product_labels, list):
        product_labels = [str(label) for label in raw_product_labels]
    elif raw_product_labels:
        product_labels = [str(raw_product_labels)]
    else:
        product_labels = []
    provenance = _merge_provenance_metadata(
        default_provenance,
        _normalize_provenance_metadata(
            metadata,
            fallback_source_pack=default_provenance.get("source_pack"),
            fallback_source_pack_version=default_provenance.get("source_pack_version"),
        ),
    )

    return FixtureKnowledgeDocument(
        document_hash=document_hash,
        title=title,
        name=name,
        content=content,
        source=source,
        category=category,
        doc_type=doc_type,
        severity=severity,
        summary=summary,
        priority=priority,
        pinned=bool(metadata.get("pinned", pinned) or pinned),
        frontmatter_pinned=bool(metadata.get("pinned", False)),
        version=version,
        product_labels=product_labels,
        index_type=_infer_index_type(doc_type),
        provenance=provenance,
    )


def build_fixture_knowledge_backend(scenario: EvalScenario) -> FixtureKnowledgeBackend:
    """Build a scenario-scoped fixture knowledge backend."""

    return FixtureKnowledgeBackend.from_scenario(scenario)


__all__ = [
    "FixtureKnowledgeBackend",
    "build_fixture_knowledge_backend",
]

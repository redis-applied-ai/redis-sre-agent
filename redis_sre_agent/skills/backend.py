"""Runtime skill backend abstraction and default Redis implementation."""

from __future__ import annotations

import importlib
import json
import threading
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from redis_sre_agent.core.config import Settings, settings

from .contracts import build_contract_summary, extract_output_contract, extract_workflow_contract

SkillSearchType = Literal["semantic", "keyword", "hybrid"]
SUPPORTED_SKILL_SEARCH_TYPES: tuple[SkillSearchType, ...] = ("semantic", "keyword", "hybrid")


def normalize_skill_search_type(
    query: str | None,
    search_type: str | None,
    *,
    default_when_queried: SkillSearchType = "semantic",
) -> SkillSearchType | None:
    """Normalize search_type for queried skill lookups."""
    if not str(query or "").strip():
        return None

    normalized = str(search_type or default_when_queried).strip().lower() or default_when_queried
    if normalized not in SUPPORTED_SKILL_SEARCH_TYPES:
        supported = ", ".join(SUPPORTED_SKILL_SEARCH_TYPES)
        raise ValueError(f"Unsupported skill search_type '{normalized}'. Expected one of: {supported}")
    return cast(SkillSearchType, normalized)


def unsupported_skill_search_type_result(
    *,
    query: str | None,
    search_type: str | None,
    version: str | None,
    offset: int,
    limit: int,
    backend_kind: str,
    supported_search_types: tuple[str, ...],
) -> dict[str, Any]:
    """Return a structured unsupported-search response."""
    requested = str(search_type or "").strip().lower() or None
    return {
        "query": query,
        "search_type": requested,
        "version": version,
        "offset": offset,
        "limit": limit,
        "results_count": 0,
        "total_fetched": 0,
        "skills": [],
        "backend_kind": backend_kind,
        "error": "unsupported_search_type",
        "requested_search_type": requested,
        "supported_search_types": list(supported_search_types),
    }


class SkillBackend(Protocol):
    """Runtime backend for skill discovery and retrieval."""

    async def list_skills(
        self,
        *,
        query: str | None,
        limit: int,
        offset: int,
        version: str | None,
        search_type: str | None = None,
        distance_threshold: float | None = 0.8,
    ) -> dict[str, Any]: ...

    async def get_skill(self, *, skill_name: str, version: str | None) -> dict[str, Any]: ...

    async def get_skill_resource(
        self,
        *,
        skill_name: str,
        resource_path: str,
        version: str | None,
    ) -> dict[str, Any]: ...


@dataclass
class RedisSkillBackend:
    """Default Redis-backed skill backend."""

    config: Settings | None = None

    @property
    def settings(self) -> Settings:
        return self.config or settings

    def _truncate_resource_content(self, content: str) -> tuple[str, bool]:
        budget = max(int(self.settings.skill_reference_char_budget), 1)
        if len(content) <= budget:
            return content, False
        if budget <= 3:
            return content[:budget], True
        return f"{content[: budget - 3].rstrip()}...", True

    async def list_skills(
        self,
        *,
        query: str | None,
        limit: int,
        offset: int,
        version: str | None,
        search_type: str | None = None,
        distance_threshold: float | None = 0.8,
    ) -> dict[str, Any]:
        from redis_sre_agent.core import knowledge_helpers as helpers

        index = await helpers.get_skills_index(config=self.settings)
        normalized_search_type = normalize_skill_search_type(query, search_type)

        fetch_limit = min(max(limit + offset, 1) * 8, 1000)
        return_fields = [
            "id",
            "document_hash",
            "chunk_index",
            "title",
            "content",
            "source",
            "name",
            "summary",
            "priority",
            "pinned",
            "doc_type",
            "version",
            "score",
            "vector_distance",
            "distance",
            "skill_protocol",
            "resource_kind",
            "resource_path",
            "mime_type",
            "encoding",
            "package_hash",
            "entrypoint",
            "has_references",
            "has_scripts",
            "has_assets",
            "resource_title",
            "resource_description",
            "skill_description",
            "ui_metadata",
            "skill_manifest",
            "meta_name",
            "meta_summary",
            "meta_priority",
            "meta_pinned",
        ]

        if normalized_search_type == "semantic":
            vectorizer = helpers.get_vectorizer(config=self.settings)
            vectors = await vectorizer.aembed_many([query])
            query_vector = vectors[0] if vectors else []
            if distance_threshold is not None:
                query_obj = helpers.VectorRangeQuery(
                    vector=query_vector,
                    vector_field_name="vector",
                    return_fields=return_fields,
                    num_results=fetch_limit,
                    distance_threshold=distance_threshold,
                )
            else:
                query_obj = helpers.VectorQuery(
                    vector=query_vector,
                    vector_field_name="vector",
                    return_fields=return_fields,
                    num_results=fetch_limit,
                )
            candidates = await index.query(query_obj)
        elif normalized_search_type == "keyword":
            candidates = await index.query(
                helpers._RawTextQuery(
                    query or "",
                    return_fields=return_fields,
                    num_results=fetch_limit,
                )
            )
        elif normalized_search_type == "hybrid":
            vectorizer = helpers.get_vectorizer(config=self.settings)
            vectors = await vectorizer.aembed_many([query or ""])
            query_vector = vectors[0] if vectors else []
            try:
                candidates = await index.query(
                    helpers.HybridQuery(
                        vector=query_vector,
                        vector_field_name="vector",
                        text_field_name="content",
                        text=query or "",
                        num_results=fetch_limit,
                        return_fields=return_fields,
                    )
                )
            except Exception as exc:
                if not helpers._is_hybrid_query_unsupported_error(exc):
                    raise
                candidates = await helpers._run_hybrid_rrf_fallback(
                    index=index,
                    query=query or "",
                    query_vector=query_vector,
                    query_filter=None,
                    return_fields=return_fields,
                    num_results=fetch_limit,
                )
        else:
            candidates = await index.query(
                helpers.FilterQuery(
                    filter_expression=helpers.Tag("document_hash") != "",
                    return_fields=return_fields,
                    num_results=fetch_limit,
                )
            )

        candidates = [
            {**doc, "_index_type": "skills"}
            for doc in helpers._dedupe_docs(candidates)
            if helpers._doc_matches_requested_version(doc, version)
            and not helpers._doc_is_pinned(doc)
        ]

        def _skill_key(doc: dict[str, Any]) -> str:
            return str(doc.get("name") or doc.get("meta_name") or doc.get("title") or "").strip()

        def _score(doc: dict[str, Any]) -> float:
            for key in ("score", "vector_distance", "distance"):
                value = doc.get(key)
                if value is not None:
                    try:
                        return float(value)
                    except Exception:
                        continue
            return float("inf")

        def _representative_rank(doc: dict[str, Any]) -> tuple[int, str, int, str]:
            resource_kind = str(doc.get("resource_kind") or "").strip().lower()
            resource_path = str(doc.get("resource_path") or "").strip().lower()
            return (
                0 if resource_kind == "entrypoint" else 1,
                resource_path,
                helpers._doc_chunk_index(doc),
                str(doc.get("document_hash") or ""),
            )

        by_skill: dict[str, dict[str, Any]] = {}
        for doc in candidates:
            skill_key = _skill_key(doc)
            if not skill_key:
                continue
            existing = by_skill.get(skill_key)
            if existing is None:
                by_skill[skill_key] = doc
                continue
            if normalized_search_type is not None:
                if (_score(doc), str(doc.get("resource_path") or "")) < (
                    _score(existing),
                    str(existing.get("resource_path") or ""),
                ):
                    by_skill[skill_key] = doc
            elif _representative_rank(doc) < _representative_rank(existing):
                by_skill[skill_key] = doc

        ordered_docs = sorted(
            by_skill.values(),
            key=(
                (
                    lambda d: (
                        _score(d),
                        _skill_key(d).lower(),
                        str(d.get("resource_path") or "").lower(),
                    )
                )
                if normalized_search_type is not None
                else (lambda d: (_skill_key(d).lower(), str(d.get("resource_path") or "").lower()))
            ),
        )
        paged_docs = ordered_docs[offset : offset + limit]

        skills = []
        for doc in paged_docs:
            protocol = (
                str(doc.get("skill_protocol") or "legacy_markdown").strip() or "legacy_markdown"
            )
            skills.append(
                {
                    "name": _skill_key(doc),
                    "document_hash": str(doc.get("document_hash", "")),
                    "title": str(doc.get("title") or _skill_key(doc)),
                    "source": str(doc.get("source", "")),
                    "version": helpers._normalized_doc_version(doc),
                    "priority": helpers._doc_priority(doc),
                    "summary": str(
                        doc.get("skill_description")
                        or helpers._doc_summary(doc)
                        or helpers._summary_preview(str(doc.get("content", "")))
                    ).strip(),
                    "index_type": str(doc.get("_index_type", "skills")),
                    "backend_kind": "redis",
                    "protocol": protocol,
                    "has_references": helpers._parse_bool(doc.get("has_references"), default=False),
                    "has_scripts": helpers._parse_bool(doc.get("has_scripts"), default=False),
                    "has_assets": helpers._parse_bool(doc.get("has_assets"), default=False),
                    "matched_resource_kind": str(
                        doc.get("resource_kind")
                        or ("entrypoint" if protocol == "legacy_markdown" else "")
                    ),
                    "matched_resource_path": str(doc.get("resource_path") or ""),
                }
            )

        from datetime import datetime, timezone

        return {
            "query": query,
            "search_type": normalized_search_type,
            "version": version,
            "offset": offset,
            "limit": limit,
            "results_count": len(skills),
            "total_fetched": len(ordered_docs),
            "skills": skills,
            "supported_search_types": list(SUPPORTED_SKILL_SEARCH_TYPES),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_skill(self, *, skill_name: str, version: str | None) -> dict[str, Any]:
        normalized_name = str(skill_name or "").strip()
        if not normalized_name:
            return {"skill_name": skill_name, "error": "Skill name is required"}

        rows = await self._query_skill_rows(skill_name=normalized_name, version=version)
        if not rows:
            related_skills: list[str] = []
            try:
                related = await self.list_skills(
                    query=skill_name,
                    limit=50,
                    offset=0,
                    version=version,
                )
                related_skills = [
                    str(skill.get("name", "")) for skill in related.get("skills", [])[:50]
                ]
            except Exception:
                related_skills = []
            return {
                "skill_name": skill_name,
                "error": "Skill not found",
                "available_skills": related_skills,
            }

        resources = await self._load_skill_resources(rows=rows, version=version)
        if not resources:
            return {
                "skill_name": skill_name,
                "error": "Skill not found",
                "available_skills": [],
            }
        if resources[0].get("_error"):
            error_resource = resources[0]
            return {
                "skill_name": str(error_resource.get("skill_name") or normalized_name),
                "document_hash": str(error_resource.get("document_hash") or ""),
                "doc_type": str(error_resource.get("doc_type") or ""),
                "error": str(error_resource.get("_error") or "Skill not found"),
            }
        entrypoint = next(
            (resource for resource in resources if resource["resource_kind"] == "entrypoint"),
            resources[0],
        )
        manifest = self._extract_skill_manifest(entrypoint.get("metadata", {}))
        protocol = str(entrypoint.get("protocol") or "legacy_markdown")
        if protocol == "legacy_markdown":
            return {
                "skill_name": str(entrypoint.get("skill_name") or normalized_name),
                "full_content": str(entrypoint.get("content") or "").strip(),
            }
        ui_metadata = self._extract_ui_metadata(entrypoint.get("metadata", {}))
        output_contract = extract_output_contract(ui_metadata)
        workflow_contract = extract_workflow_contract(ui_metadata)
        return {
            "skill_name": str(entrypoint.get("skill_name") or normalized_name),
            "backend_kind": "redis",
            "protocol": protocol,
            "full_content": str(entrypoint.get("content") or "").strip(),
            "description": str(
                entrypoint.get("description") or entrypoint.get("summary") or ""
            ).strip(),
            "references": [
                {
                    "path": resource["resource_path"],
                    "title": resource.get("title", ""),
                    "summary": resource.get("description", ""),
                }
                for resource in resources
                if resource["resource_kind"] == "reference"
            ],
            "scripts": [
                {
                    "path": resource["resource_path"],
                    "description": resource.get("description", ""),
                }
                for resource in resources
                if resource["resource_kind"] == "script"
            ],
            "assets": manifest.get("assets", [])
            or [
                {"path": resource["resource_path"]}
                for resource in resources
                if resource["resource_kind"] == "asset"
            ],
            "ui_metadata": ui_metadata,
            "output_contract": output_contract,
            "workflow_contract": workflow_contract,
            "contract_summary": build_contract_summary(output_contract, workflow_contract),
        }

    async def get_skill_resource(
        self,
        *,
        skill_name: str,
        resource_path: str,
        version: str | None,
    ) -> dict[str, Any]:
        normalized_name = str(skill_name or "").strip()
        normalized_path = str(resource_path or "").strip()
        if not normalized_name:
            return {
                "skill_name": skill_name,
                "resource_path": resource_path,
                "error": "Skill name is required",
            }
        if not normalized_path:
            return {
                "skill_name": skill_name,
                "resource_path": resource_path,
                "error": "Resource path is required",
            }

        rows = await self._query_skill_rows(
            skill_name=normalized_name,
            version=version,
            resource_path=normalized_path,
        )
        if not rows:
            return {
                "skill_name": skill_name,
                "resource_path": resource_path,
                "error": "Skill resource not found",
            }

        resources = await self._load_skill_resources(rows=rows, version=version)
        if not resources:
            return {
                "skill_name": skill_name,
                "resource_path": resource_path,
                "error": "Skill resource not found",
            }
        resource = resources[0]
        if resource.get("_error"):
            return {
                "skill_name": str(resource.get("skill_name") or normalized_name),
                "resource_path": normalized_path,
                "document_hash": str(resource.get("document_hash") or ""),
                "doc_type": str(resource.get("doc_type") or ""),
                "error": str(resource.get("_error") or "Skill resource not found"),
            }
        content, truncated = self._truncate_resource_content(str(resource.get("content") or ""))
        return {
            "skill_name": resource["skill_name"],
            "resource_path": resource["resource_path"],
            "resource_kind": resource["resource_kind"],
            "content": content,
            "truncated": truncated,
            "mime_type": resource["mime_type"],
            "backend_kind": "redis",
            "protocol": resource["protocol"],
            "content_length": len(str(resource.get("content") or "")),
            "char_budget": int(self.settings.skill_reference_char_budget),
        }

    async def _query_skill_rows(
        self,
        *,
        skill_name: str,
        version: str | None,
        resource_path: str | None = None,
    ) -> list[dict[str, Any]]:
        from redis_sre_agent.core import knowledge_helpers as helpers

        index = await helpers.get_skills_index(config=self.settings)
        return_fields = [
            "id",
            "document_hash",
            "chunk_index",
            "title",
            "source",
            "name",
            "summary",
            "priority",
            "doc_type",
            "version",
            "skill_protocol",
            "resource_kind",
            "resource_path",
            "mime_type",
            "encoding",
            "package_hash",
            "entrypoint",
            "has_references",
            "has_scripts",
            "has_assets",
            "resource_title",
            "resource_description",
            "skill_description",
            "ui_metadata",
            "skill_manifest",
        ]
        filter_expression = helpers._tag_equals_expression("name", skill_name)
        if resource_path:
            filter_expression = filter_expression & helpers._tag_equals_expression(
                "resource_path", resource_path
            )
        query = helpers.FilterQuery(
            filter_expression=filter_expression,
            return_fields=return_fields,
            num_results=200,
        )
        rows = await index.query(query)
        rows = [
            {**row, "_index_type": "skills"}
            for row in helpers._dedupe_docs(rows)
            if helpers._doc_matches_requested_version(row, version)
        ]
        rows.sort(
            key=lambda row: (str(row.get("resource_path") or ""), helpers._doc_chunk_index(row))
        )
        return rows

    async def _load_skill_resources(
        self,
        *,
        rows: list[dict[str, Any]],
        version: str | None,
    ) -> list[dict[str, Any]]:
        from redis_sre_agent.core import knowledge_helpers as helpers

        resources: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()
        for row in rows:
            document_hash = str(row.get("document_hash") or "").strip()
            if not document_hash or document_hash in seen_hashes:
                continue
            seen_hashes.add(document_hash)
            doc = await helpers.get_all_document_fragments(
                document_hash=document_hash,
                include_metadata=True,
                index_type="skills",
                version=version,
                config=self.settings,
            )
            doc_type = str(doc.get("doc_type") or "").strip().lower()
            if doc_type and doc_type != "skill":
                skill_name = str(row.get("name") or row.get("title") or "").strip()
                return [
                    {
                        "skill_name": skill_name,
                        "document_hash": document_hash,
                        "doc_type": doc_type,
                        "_error": f"Resolved document type was '{doc_type}', not 'skill'",
                    }
                ]
            fragments = sorted(
                doc.get("fragments") or [], key=lambda fragment: helpers._doc_chunk_index(fragment)
            )
            full_content = "\n\n".join(
                str(fragment.get("content", "")).strip()
                for fragment in fragments
                if str(fragment.get("content", "")).strip()
            ).strip()
            metadata = doc.get("metadata") or {}
            protocol = (
                str(
                    metadata.get("skill_protocol") or row.get("skill_protocol") or "legacy_markdown"
                ).strip()
                or "legacy_markdown"
            )
            resource_kind = str(
                metadata.get("resource_kind") or row.get("resource_kind") or "entrypoint"
            )
            resources.append(
                {
                    "skill_name": str(
                        metadata.get("name") or row.get("name") or row.get("title") or ""
                    ),
                    "protocol": protocol,
                    "resource_kind": resource_kind,
                    "resource_path": str(
                        metadata.get("resource_path") or row.get("resource_path") or "SKILL.md"
                    ),
                    "mime_type": str(
                        metadata.get("mime_type") or row.get("mime_type") or "text/markdown"
                    ),
                    "content": full_content,
                    "title": str(
                        metadata.get("resource_title")
                        or row.get("resource_title")
                        or doc.get("title")
                        or ""
                    ),
                    "summary": str(metadata.get("summary") or doc.get("summary") or ""),
                    "description": str(
                        metadata.get("resource_description")
                        or row.get("resource_description")
                        or metadata.get("skill_description")
                        or row.get("skill_description")
                        or ""
                    ),
                    "metadata": metadata,
                }
            )
        resources.sort(
            key=lambda item: (item["resource_kind"] != "entrypoint", item["resource_path"])
        )
        return resources

    @staticmethod
    def _extract_ui_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        return RedisSkillBackend._extract_metadata_dict(metadata, "ui_metadata")

    @staticmethod
    def _extract_skill_manifest(metadata: dict[str, Any]) -> dict[str, Any]:
        return RedisSkillBackend._extract_metadata_dict(metadata, "skill_manifest")

    @staticmethod
    def _extract_metadata_dict(metadata: dict[str, Any], key: str) -> dict[str, Any]:
        raw = metadata.get(key)
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str) and raw.strip():
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            if isinstance(payload, dict):
                return payload
        return {}


_DEFAULT_BACKEND_CACHE: tuple[tuple[str, str], SkillBackend] | None = None
_DEFAULT_BACKEND_CACHE_LOCK = threading.Lock()


def _load_custom_backend(config: Settings) -> SkillBackend:
    class_path = str(config.skill_backend_class or "").strip()
    if not class_path:
        raise ValueError("skill_backend_class is required when skill_backend_kind=custom")
    module_name, _, attr_name = class_path.rpartition(".")
    if not module_name or not attr_name:
        raise ValueError(f"Invalid skill backend class path: {class_path}")
    module = importlib.import_module(module_name)
    backend_cls = getattr(module, attr_name)
    if hasattr(backend_cls, "from_settings"):
        return backend_cls.from_settings(config)
    try:
        return backend_cls(config=config)
    except TypeError:
        try:
            return backend_cls(config)
        except TypeError:
            return backend_cls()


def get_skill_backend(config: Settings | None = None) -> SkillBackend:
    """Return the active runtime skill backend."""

    global _DEFAULT_BACKEND_CACHE
    active_config = config or settings
    if config is not None:
        if active_config.skill_backend_kind == "custom":
            return _load_custom_backend(active_config)
        return RedisSkillBackend(config=active_config)

    cache_key = (
        str(active_config.skill_backend_kind or "redis"),
        str(active_config.skill_backend_class or ""),
    )
    with _DEFAULT_BACKEND_CACHE_LOCK:
        if _DEFAULT_BACKEND_CACHE and _DEFAULT_BACKEND_CACHE[0] == cache_key:
            return _DEFAULT_BACKEND_CACHE[1]

        if active_config.skill_backend_kind == "custom":
            backend = _load_custom_backend(active_config)
        else:
            backend = RedisSkillBackend(config=active_config)
        _DEFAULT_BACKEND_CACHE = (cache_key, backend)
        return backend

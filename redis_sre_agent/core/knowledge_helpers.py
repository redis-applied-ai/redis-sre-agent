"""Helper functions for knowledge base operations.

These are the core implementation functions that do the actual work.
They are called by:
- Tasks (in core.tasks) for background execution via Docket
- Tools (in agent.knowledge_agent) for LLM access with custom docstrings
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from redisvl.query import FilterQuery, HybridQuery, VectorQuery, VectorRangeQuery
from ulid import ULID

from redis_sre_agent.core.config import Settings
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_knowledge_index, get_vectorizer

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
_SOURCE_VERSION_RE = re.compile(r"/(\d+\.\d+)/")
_SPECIAL_DOCUMENT_TYPES = {"skill", "support_ticket"}
_PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}


def _extract_version_from_source(source: str) -> str:
    """Infer doc version from source URL/path."""
    if not source:
        return "latest"
    match = _SOURCE_VERSION_RE.search(source)
    if match:
        return match.group(1)
    return "latest"


def _normalized_doc_version(doc: Dict[str, Any]) -> str:
    """Choose the most reliable version for output."""
    source_version = _extract_version_from_source(str(doc.get("source", "")))
    if source_version != "latest":
        return source_version
    version = str(doc.get("version", "")).strip()
    return version or "latest"


def _normalized_doc_type(doc: Dict[str, Any]) -> str:
    """Normalize document type from canonical/legacy fields."""
    doc_type = str(doc.get("document_type", "")).strip().lower()
    if doc_type:
        if doc_type == "ticket":
            return "support_ticket"
        return doc_type
    legacy_doc_type = str(doc.get("doc_type", "")).strip().lower()
    if legacy_doc_type:
        if legacy_doc_type == "ticket":
            return "support_ticket"
        return legacy_doc_type
    return "general"


def _doc_matches_requested_version(doc: Dict[str, Any], requested_version: Optional[str]) -> bool:
    """Apply source-aware version matching for compatibility with legacy indexed docs."""
    if requested_version is None:
        return True

    source_version = _extract_version_from_source(str(doc.get("source", "")))
    doc_version = str(doc.get("version", "")).strip()

    if requested_version == "latest":
        # Canonical latest docs are unversioned paths.
        return source_version == "latest"

    return source_version == requested_version or doc_version == requested_version


def _doc_matches_requested_type(doc: Dict[str, Any], requested_type: Optional[str]) -> bool:
    """Apply document type filtering while supporting legacy fields."""
    if requested_type is None:
        return True
    normalized_requested = requested_type.strip().lower()
    if normalized_requested == "ticket":
        normalized_requested = "support_ticket"
    return _normalized_doc_type(doc) == normalized_requested


def _parse_bool(value: Any, default: bool = False) -> bool:
    """Best-effort bool coercion for metadata values."""
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


def _doc_is_pinned(doc: Dict[str, Any]) -> bool:
    """Whether a document is marked pinned."""
    return _parse_bool(doc.get("pinned"), default=_parse_bool(doc.get("meta_pinned"), False))


def _doc_priority(doc: Dict[str, Any]) -> str:
    """Normalize priority to low|normal|high|critical."""
    raw_priority = str(doc.get("priority") or doc.get("meta_priority") or "normal").strip().lower()
    if raw_priority in _PRIORITY_ORDER:
        return raw_priority
    return "normal"


def _doc_name(doc: Dict[str, Any]) -> str:
    """Resolve document display name with metadata fallback."""
    for key in ("name", "meta_name", "title"):
        value = str(doc.get(key, "")).strip()
        if value:
            return value
    return ""


def _doc_summary(doc: Dict[str, Any]) -> str:
    """Resolve document summary with metadata fallback."""
    for key in ("summary", "meta_summary"):
        value = str(doc.get(key, "")).strip()
        if value:
            return value
    return ""


def _summary_preview(text: str, max_len: int = 150) -> str:
    """Build deterministic summary preview text."""
    compact = " ".join((text or "").split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[:max_len].rstrip()}..."


def _doc_is_general_knowledge(doc: Dict[str, Any]) -> bool:
    """General knowledge excludes pinned, skills, and support tickets."""
    return (not _doc_is_pinned(doc)) and _normalized_doc_type(doc) not in _SPECIAL_DOCUMENT_TYPES


def _dedupe_docs(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Preserve order while removing duplicate documents/chunks."""
    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for doc in docs:
        key = (
            doc.get("id"),
            doc.get("document_hash"),
            doc.get("chunk_index"),
            doc.get("source"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(doc)
    return deduped


def _doc_chunk_index(doc: Dict[str, Any]) -> int:
    """Best-effort chunk index parsing for deterministic ordering."""
    try:
        if doc.get("chunk_index") is not None and str(doc.get("chunk_index")) != "":
            return int(doc.get("chunk_index"))  # type: ignore[arg-type]
    except Exception:
        pass
    return 10**9


async def skills_check_helper(
    query: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    version: Optional[str] = "latest",
    distance_threshold: Optional[float] = 0.8,
    config: Optional[Settings] = None,
) -> Dict[str, Any]:
    """List available skills from the knowledge base.

    If query is provided, skill selection is relevance-ranked via vector search.
    """
    logger.info(
        "Listing skills (query=%s, version=%s, offset=%s, limit=%s)",
        bool(query),
        version,
        offset,
        limit,
    )
    index = await get_knowledge_index(config=config)

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
        "meta_name",
        "meta_summary",
        "meta_priority",
        "meta_pinned",
        "document_type",
        "doc_type",
        "version",
        "score",
        "vector_distance",
        "distance",
    ]

    if query:
        from redisvl.query.filter import Tag

        vectorizer = get_vectorizer()
        vectors = await vectorizer.aembed_many([query])
        query_vector = vectors[0] if vectors else []

        def _skill_vector_query(filter_expression):
            if distance_threshold is not None:
                q = VectorRangeQuery(
                    vector=query_vector,
                    vector_field_name="vector",
                    return_fields=return_fields,
                    num_results=fetch_limit,
                    distance_threshold=distance_threshold,
                )
            else:
                q = VectorQuery(
                    vector=query_vector,
                    vector_field_name="vector",
                    return_fields=return_fields,
                    num_results=fetch_limit,
                )
            q.set_filter(filter_expression)
            return q

        canonical = await index.query(_skill_vector_query(Tag("document_type") == "skill"))
        legacy = await index.query(_skill_vector_query(Tag("doc_type") == "skill"))
    else:
        # Query canonical and legacy type fields, then normalize/dedupe in memory.
        canonical = await index.query(
            FilterQuery(
                filter_expression='@document_type:{"skill"}',
                return_fields=return_fields,
                num_results=fetch_limit,
            )
        )
        legacy = await index.query(
            FilterQuery(
                filter_expression='@doc_type:{"skill"}',
                return_fields=return_fields,
                num_results=fetch_limit,
            )
        )

    candidates = [
        doc
        for doc in _dedupe_docs(canonical + legacy)
        if _doc_matches_requested_type(doc, "skill")
        and _doc_matches_requested_version(doc, version)
        and not _doc_is_pinned(doc)
    ]

    # Keep one representative row per document, preferring the first chunk.
    by_document: Dict[str, Dict[str, Any]] = {}
    for doc in candidates:
        key = str(doc.get("document_hash") or doc.get("id") or "").strip()
        if not key:
            continue
        existing = by_document.get(key)
        if existing is None or _doc_chunk_index(doc) < _doc_chunk_index(existing):
            by_document[key] = doc

    if query:

        def _score(doc: Dict[str, Any]) -> float:
            for key in ("score", "vector_distance", "distance"):
                value = doc.get(key)
                if value is not None:
                    try:
                        return float(value)
                    except Exception:
                        continue
            return float("inf")

        ordered_docs = sorted(
            by_document.values(),
            key=lambda d: (_score(d), _doc_name(d).lower(), str(d.get("source", "")).lower()),
        )
    else:
        ordered_docs = sorted(
            by_document.values(),
            key=lambda d: (_doc_name(d).lower(), str(d.get("source", "")).lower()),
        )
    paged_docs = ordered_docs[offset : offset + limit]

    skills = [
        {
            "name": _doc_name(doc),
            "document_hash": str(doc.get("document_hash", "")),
            "title": str(doc.get("title", "")),
            "source": str(doc.get("source", "")),
            "version": _normalized_doc_version(doc),
            "priority": _doc_priority(doc),
            "summary": _doc_summary(doc) or _summary_preview(str(doc.get("content", ""))),
        }
        for doc in paged_docs
    ]

    return {
        "query": query,
        "version": version,
        "offset": offset,
        "limit": limit,
        "results_count": len(skills),
        "total_fetched": len(ordered_docs),
        "skills": skills,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def get_skill_helper(skill_name: str, version: Optional[str] = "latest") -> Dict[str, Any]:
    """Get complete content for a skill document by skill name."""
    skills_result = await skills_check_helper(query=None, limit=1000, offset=0, version=version)
    skills = skills_result.get("skills") or []

    target = next(
        (
            skill
            for skill in skills
            if str(skill.get("name", "")).strip().lower() == skill_name.strip().lower()
        ),
        None,
    )

    if target is None:
        return {
            "skill_name": skill_name,
            "error": "Skill not found",
            "available_skills": [str(skill.get("name", "")) for skill in skills[:50]],
        }

    document_hash = str(target.get("document_hash", ""))
    if not document_hash:
        return {
            "skill_name": skill_name,
            "error": "Skill document hash is missing",
        }

    result = await get_all_document_fragments(document_hash=document_hash, include_metadata=True)

    fragments = result.get("fragments") or []
    if not fragments:
        return {
            "skill_name": skill_name,
            "document_hash": document_hash,
            **result,
        }

    normalized_type = str(
        result.get("document_type") or _normalized_doc_type(fragments[0])  # type: ignore[index]
    ).lower()
    if normalized_type != "skill":
        return {
            "skill_name": skill_name,
            "document_hash": document_hash,
            "error": f"Document type is '{normalized_type}', not 'skill'",
            "document_type": normalized_type,
        }

    sorted_fragments = sorted(fragments, key=lambda x: _doc_chunk_index(x))
    full_content = "\n\n".join(str(f.get("content", "")).strip() for f in sorted_fragments).strip()

    return {
        "skill_name": _doc_name({"name": target.get("name"), "title": result.get("title", "")}),
        "document_hash": document_hash,
        "title": result.get("title", ""),
        "source": result.get("source", ""),
        "document_type": normalized_type,
        "fragments_count": len(sorted_fragments),
        "fragments": sorted_fragments,
        "full_content": full_content,
        "metadata": result.get("metadata", {}),
    }


async def search_support_tickets_helper(
    query: str,
    limit: int = 10,
    offset: int = 0,
    distance_threshold: Optional[float] = 0.8,
    hybrid_search: bool = False,
    version: Optional[str] = "latest",
    config: Optional[Settings] = None,
) -> Dict[str, Any]:
    """Search support tickets only."""
    result = await search_knowledge_base_helper(
        query=query,
        document_type="support_ticket",
        limit=limit,
        offset=offset,
        distance_threshold=distance_threshold,
        hybrid_search=hybrid_search,
        version=version,
        config=config,
        include_special_document_types=True,
    )

    tickets = []
    for ticket in result.get("results", []):
        ticket_with_id = dict(ticket)
        ticket_with_id["ticket_id"] = str(ticket.get("document_hash") or ticket.get("id") or "")
        tickets.append(ticket_with_id)

    result.update(
        {
            "ticket_count": len(tickets),
            "tickets": tickets,
            "results": tickets,
            "results_count": len(tickets),
            "document_type": "support_ticket",
            "document_type_filter": "support_ticket",
        }
    )
    return result


async def get_support_ticket_helper(ticket_id: str) -> Dict[str, Any]:
    """Get complete content for a support ticket by ticket id."""
    result = await get_all_document_fragments(document_hash=ticket_id, include_metadata=True)
    fragments = result.get("fragments") or []
    if not fragments:
        return {
            "ticket_id": ticket_id,
            **result,
        }

    normalized_type = str(
        result.get("document_type") or _normalized_doc_type(fragments[0])  # type: ignore[index]
    ).lower()
    if normalized_type != "support_ticket":
        return {
            "ticket_id": ticket_id,
            "document_hash": ticket_id,
            "error": f"Document type is '{normalized_type}', not 'support_ticket'",
            "document_type": normalized_type,
        }

    sorted_fragments = sorted(fragments, key=lambda x: _doc_chunk_index(x))
    full_content = "\n\n".join(str(f.get("content", "")).strip() for f in sorted_fragments).strip()
    metadata = result.get("metadata", {}) or {}
    return {
        "ticket_id": ticket_id,
        "document_hash": ticket_id,
        "title": result.get("title", ""),
        "source": result.get("source", ""),
        "document_type": normalized_type,
        "priority": str(metadata.get("priority", "normal")),
        "summary": str(metadata.get("summary", "")),
        "fragments_count": len(sorted_fragments),
        "fragments": sorted_fragments,
        "full_content": full_content,
        "metadata": metadata,
    }


async def get_pinned_documents_helper(
    version: Optional[str] = "latest",
    limit: int = 50,
    content_char_budget: int = 12000,
    config: Optional[Settings] = None,
) -> Dict[str, Any]:
    """Return pinned documents in deterministic priority order."""
    index = await get_knowledge_index(config=config)
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
        "meta_name",
        "meta_summary",
        "meta_priority",
        "meta_pinned",
        "document_type",
        "doc_type",
        "version",
    ]

    rows = await index.query(
        FilterQuery(
            filter_expression='@pinned:{"true"}',
            return_fields=return_fields,
            num_results=2000,
        )
    )

    candidates = [
        row
        for row in _dedupe_docs(rows)
        if _doc_is_pinned(row) and _doc_matches_requested_version(row, version)
    ]

    by_document: Dict[str, List[Dict[str, Any]]] = {}
    for row in candidates:
        doc_hash = str(row.get("document_hash") or row.get("id") or "").strip()
        if not doc_hash:
            continue
        by_document.setdefault(doc_hash, []).append(row)

    docs = []
    for doc_hash, chunks in by_document.items():
        sorted_chunks = sorted(chunks, key=_doc_chunk_index)
        sample = sorted_chunks[0]
        full_content = "\n\n".join(
            str(fragment.get("content", "")).strip() for fragment in sorted_chunks
        ).strip()
        docs.append(
            {
                "document_hash": doc_hash,
                "name": _doc_name(sample),
                "summary": _doc_summary(sample) or _summary_preview(full_content),
                "priority": _doc_priority(sample),
                "source": str(sample.get("source", "")),
                "document_type": _normalized_doc_type(sample),
                "full_content": full_content,
                "truncated": False,
            }
        )

    docs.sort(
        key=lambda doc: (
            _PRIORITY_ORDER.get(str(doc.get("priority", "normal")), _PRIORITY_ORDER["normal"]),
            str(doc.get("name", "")).lower(),
            str(doc.get("source", "")).lower(),
            str(doc.get("document_hash", "")).lower(),
        )
    )

    docs = docs[:limit]
    used_chars = 0
    included = []
    for doc in docs:
        content = str(doc.get("full_content", ""))
        remaining = content_char_budget - used_chars
        if remaining <= 0:
            break
        if len(content) <= remaining:
            included.append(doc)
            used_chars += len(content)
            continue

        truncated = dict(doc)
        if remaining > 3:
            truncated["full_content"] = f"{content[: remaining - 3].rstrip()}..."
            used_chars = content_char_budget
            truncated["truncated"] = True
            included.append(truncated)
        break

    return {
        "version": version,
        "limit": limit,
        "results_count": len(included),
        "total_fetched": len(docs),
        "truncated": len(included) < len(docs) or any(doc.get("truncated") for doc in included),
        "pinned_documents": included,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def search_knowledge_base_helper(
    query: str,
    category: Optional[str] = None,
    document_type: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    distance_threshold: Optional[float] = 0.8,
    hybrid_search: bool = False,
    version: Optional[str] = "latest",
    config: Optional[Settings] = None,
    include_special_document_types: bool = False,
) -> Dict[str, Any]:
    """Search the SRE knowledge base.

    NOTE: The HybridQuery class can't take a distance threshold, so if
          hybrid_search is True, distance_threshold is ignored.

    Behavior:
        - Default: distance_threshold=0.8 (filters by cosine distance)
        - Explicit None: disables threshold (pure KNN, return top-k regardless of distance)
        - Default version: "latest" (filters to unversioned/latest docs)
        - Explicit version: Filter to specific version (e.g., "7.8", "7.4")
        - version=None: Return all versions (no version filtering)

    Args:
        query: Search query text
        category: Optional category filter (incident, maintenance, monitoring, etc.)
        document_type: Optional document type filter
        limit: Maximum number of results
        offset: Number of results to skip (for pagination)
        distance_threshold: Cosine distance cutoff; None disables threshold
        hybrid_search: Whether to use hybrid search (vector + full-text)
        version: Version filter - "latest" (default), specific version like "7.8",
                 or None to return all versions
        config: Optional Settings for dependency injection (testing)

    Returns:
        Dictionary with search results including task_id, query, results, etc.
    """
    logger.info(f"Searching SRE knowledge: '{query}' (version={version}, offset={offset})")
    index = await get_knowledge_index(config=config)
    normalized_document_type = document_type.strip().lower() if document_type else None
    if normalized_document_type == "ticket":
        normalized_document_type = "support_ticket"

    return_fields = [
        "id",
        "document_hash",
        # "chunk_index",
        "title",
        "content",
        "source",
        "category",
        "doc_type",
        "document_type",
        "name",
        "summary",
        "priority",
        "pinned",
        "meta_name",
        "meta_summary",
        "meta_priority",
        "meta_pinned",
        "severity",
        "version",
    ]

    # Build version filter expression if version is specified.
    # NOTE: legacy indices may have incorrect version tags; we apply
    # source-aware filtering post-query and can fall back to an unfiltered
    # query if the tag-filtered query is too restrictive.
    from redisvl.query.filter import Tag

    filter_expr = None
    if version is not None:
        # Filter by specific version (e.g., "latest", "7.8", "7.4")
        filter_expr = Tag("version") == version
        logger.debug(f"Applying version filter: {version}")
    if category is not None:
        category_filter = Tag("category") == category
        filter_expr = category_filter if filter_expr is None else (filter_expr & category_filter)
        logger.debug("Applying category filter: %s", category)
    # Always use vector search (tests rely on embedding being used)
    vectorizer = get_vectorizer()

    # Measure embedding latency and trace it
    _t0 = time.monotonic()
    with tracer.start_as_current_span("knowledge.embed") as _span:
        _span.set_attribute("query.length", len(query))
        vectors = await vectorizer.aembed_many([query])
    _t1 = time.monotonic()

    query_vector = vectors[0] if vectors else []

    # We need to fetch more results if there's an offset, then slice.
    # This is because RedisVL vector queries don't support offset directly
    fetch_limit = limit + offset
    if version is not None or normalized_document_type is not None:
        # Oversample when version filtering to improve recall after post-filtering.
        fetch_limit = min(fetch_limit * 4, 200)

    def _build_query(query_filter, num_results: int):
        if hybrid_search:
            logger.info(f"Using hybrid search (vector + full-text) for query: {query}")
            return HybridQuery(
                vector=query_vector,
                vector_field_name="vector",
                text_field_name="content",
                text=query,
                num_results=num_results,
                return_fields=return_fields,
                filter_expression=query_filter,
            )

        # Build pure vector query
        # distance_threshold default is 0.5; None disables threshold (pure KNN)
        effective_threshold = distance_threshold
        if effective_threshold is not None:
            q = VectorRangeQuery(
                vector=query_vector,
                vector_field_name="vector",
                return_fields=return_fields,
                num_results=num_results,
                distance_threshold=effective_threshold,
            )
        else:
            q = VectorQuery(
                vector=query_vector,
                vector_field_name="vector",
                return_fields=return_fields,
                num_results=num_results,
            )
        if query_filter is not None:
            q.set_filter(query_filter)
        return q

    # Perform vector search
    _t2 = time.monotonic()
    desired_results = limit + offset
    query_obj = _build_query(filter_expr, fetch_limit)
    with tracer.start_as_current_span("knowledge.index.query") as _span:
        _span.set_attribute("limit", int(limit))
        _span.set_attribute("offset", int(offset))
        _span.set_attribute("hybrid_search", bool(hybrid_search))
        _span.set_attribute("version", version or "all")
        _span.set_attribute(
            "distance_threshold",
            float(distance_threshold) if distance_threshold is not None else -1.0,
        )
        all_results = await index.query(query_obj)
        _span.set_attribute("query.filtered", bool(filter_expr is not None))
    _t3 = time.monotonic()

    filtered_results = [
        doc
        for doc in all_results
        if _doc_matches_requested_version(doc, version)
        and _doc_matches_requested_type(doc, normalized_document_type)
        and (include_special_document_types or _doc_is_general_knowledge(doc))
    ]

    if version not in (None, "latest") and len(filtered_results) < desired_results:
        fallback_fetch_limit = min(max(desired_results * 8, fetch_limit), 500)
        logger.debug(
            "Version-filter fallback query triggered for version=%s; "
            "primary_count=%s desired=%s fallback_fetch_limit=%s",
            version,
            len(filtered_results),
            desired_results,
            fallback_fetch_limit,
        )
        fallback_query = _build_query(None, fallback_fetch_limit)
        with tracer.start_as_current_span("knowledge.index.query") as _span:
            _span.set_attribute("limit", int(limit))
            _span.set_attribute("offset", int(offset))
            _span.set_attribute("hybrid_search", bool(hybrid_search))
            _span.set_attribute("version", version or "all")
            _span.set_attribute(
                "distance_threshold",
                float(distance_threshold) if distance_threshold is not None else -1.0,
            )
            _span.set_attribute("query.filtered", False)
            fallback_results = await index.query(fallback_query)

        fallback_filtered = [
            doc
            for doc in fallback_results
            if _doc_matches_requested_version(doc, version)
            and _doc_matches_requested_type(doc, normalized_document_type)
            and (include_special_document_types or _doc_is_general_knowledge(doc))
        ]
        filtered_results = _dedupe_docs(filtered_results + fallback_filtered)

    # Category fallback: if a category filter returns nothing, retry without category
    # while preserving other filters such as version/document_type.
    if category is not None and len(filtered_results) == 0:
        category_fallback_expr = Tag("version") == version if version is not None else None
        category_fallback_query = _build_query(category_fallback_expr, fetch_limit)
        with tracer.start_as_current_span("knowledge.index.query") as _span:
            _span.set_attribute("limit", int(limit))
            _span.set_attribute("offset", int(offset))
            _span.set_attribute("hybrid_search", bool(hybrid_search))
            _span.set_attribute("version", version or "all")
            _span.set_attribute(
                "distance_threshold",
                float(distance_threshold) if distance_threshold is not None else -1.0,
            )
            _span.set_attribute("query.filtered", bool(category_fallback_expr is not None))
            category_fallback_results = await index.query(category_fallback_query)

        filtered_results = [
            doc
            for doc in category_fallback_results
            if _doc_matches_requested_version(doc, version)
            and _doc_matches_requested_type(doc, normalized_document_type)
            and (include_special_document_types or _doc_is_general_knowledge(doc))
        ]

    # Apply offset by slicing results
    if offset > 0:
        results = filtered_results[offset : offset + limit]
    else:
        results = filtered_results[:limit]

    search_result = {
        "query": query,
        "category": category,
        "category_filter": category,
        "document_type": normalized_document_type,
        "document_type_filter": normalized_document_type,
        "version": version,
        "offset": offset,
        "limit": limit,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results_count": len(results),
        "total_fetched": len(filtered_results),
        "results": [
            {
                "id": doc.get("id", ""),
                "document_hash": doc.get("document_hash", ""),
                "chunk_index": doc.get("chunk_index", None),
                "title": doc.get("title", ""),
                # Return full content so callers/tests can assert on complete examples
                "content": doc.get("content", ""),
                "source": doc.get("source", ""),
                "category": doc.get("category", ""),
                "document_type": _normalized_doc_type(doc),
                "name": _doc_name(doc),
                "summary": _doc_summary(doc) or _summary_preview(str(doc.get("content", ""))),
                "priority": _doc_priority(doc),
                "pinned": _doc_is_pinned(doc),
                "version": _normalized_doc_version(doc),
                # RedisVL returns distance when return_score=True (default). Some versions
                # expose it as 'score' and others as 'vector_distance' or 'distance'.
                # Normalize to float.
                "score": (lambda _v: (float(_v) if _v is not None else 0.0))(
                    doc.get("score")
                    if doc.get("score") is not None
                    else (
                        doc.get("vector_distance")
                        if doc.get("vector_distance") is not None
                        else doc.get("distance")
                    )
                ),
            }
            for doc in results
        ],
    }

    # Log timing metrics for observability
    _embed_ms = int((_t1 - _t0) * 1000)
    _index_ms = int((_t3 - _t2) * 1000)
    _total_ms = int((_t3 - _t0) * 1000)
    logger.debug(
        f"Knowledge search timings: embed_ms={_embed_ms} index_ms={_index_ms} total_ms={_total_ms}"
    )

    logger.info(f"Knowledge search completed: ({len(results)} results)")
    return search_result


async def ingest_sre_document_helper(
    title: str,
    content: str,
    source: str,
    category: str = "general",
    severity: str = "info",
    document_type: Optional[str] = None,
    product_labels: Optional[List[str]] = None,
    config: Optional[Settings] = None,
) -> Dict[str, Any]:
    """Ingest a document into the SRE knowledge base (core implementation).

    This is the core helper function that performs the actual ingestion.
    Called by both the task (for background execution) and the tool (for LLM access).

    Args:
        title: Document title
        content: Document content
        source: Source system or file
        category: Document category (incident, runbook, monitoring, etc.)
        severity: Severity level (info, warning, critical)
        document_type: Optional document type (e.g., skill, ticket, runbook)
        product_labels: Optional list of product labels
        config: Optional Settings for dependency injection (testing)

    Returns:
        Dictionary with ingestion result including task_id, document_id, status, etc.
    """
    logger.info(f"Ingesting SRE document: {title} from {source}")

    # Get components
    index = await get_knowledge_index(config=config)
    vectorizer = get_vectorizer()

    # Create document embedding (as_buffer=True for Redis storage)
    content_vector = await vectorizer.aembed(content, as_buffer=True)

    # Prepare document data
    doc_id = str(ULID())
    doc_key = RedisKeys.knowledge_document(doc_id)

    # Convert product_labels list to comma-separated string for tag field
    product_labels_str = ",".join(product_labels) if product_labels else ""
    normalized_document_type = (document_type or "general").lower()
    if normalized_document_type == "ticket":
        normalized_document_type = "support_ticket"

    document = {
        "id": doc_id,
        "title": title,
        "content": content,
        "source": source,
        "category": category,
        # Keep legacy `doc_type` while promoting `document_type`.
        "doc_type": normalized_document_type,
        "document_type": normalized_document_type,
        "severity": severity,
        "name": title,
        "summary": "",
        "priority": "normal",
        "pinned": "false",
        "created_at": datetime.now(timezone.utc).timestamp(),
        "vector": content_vector,
        "product_labels": product_labels_str,
        "product_label_tags": product_labels_str,  # Duplicate for tag searching
    }

    # Store in vector index
    await index.load(data=[document], id_field="id", keys=[doc_key])

    result = {
        "task_id": str(ULID()),
        "document_id": doc_id,
        "title": title,
        "source": source,
        "category": category,
        "document_type": normalized_document_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ingested",
    }

    logger.info(f"Document ingested successfully: {doc_id}")
    return result


async def get_all_document_fragments(
    document_hash: str, include_metadata: bool = True
) -> Dict[str, Any]:
    """
    Retrieve all fragments/chunks of a specific document.

    This function allows the agent to get the complete document when it finds
    a relevant fragment during search.

    Args:
        document_hash: The document hash to retrieve all fragments for
        include_metadata: Whether to include document metadata

    Returns:
        Dictionary containing all fragments and metadata of the document
    """
    logger.info(f"Retrieving all fragments for document: {document_hash}")

    try:
        # Get components
        index = await get_knowledge_index()

        # Use FT.SEARCH to find all chunks for this document
        # document_hash is indexed as a TAG field, so we can filter on it.
        # Tag values that include punctuation (e.g., '-') must be quoted.
        from redisvl.query import FilterQuery

        def _quote_tag_value(value: str) -> str:
            """Quote a RediSearch TAG value, escaping any embedded quotes.

            See: RediSearch TAG query syntax — values with special chars must be
            wrapped in double quotes. Double quotes inside must be escaped.
            """
            return '"' + (value.replace('"', '\\"')) + '"'

        filter_query = FilterQuery(
            filter_expression=f"@document_hash:{{{_quote_tag_value(document_hash)}}}",
            return_fields=[
                "title",
                "content",
                "source",
                "category",
                "doc_type",
                "document_type",
                "severity",
                "document_hash",
                "chunk_index",
                "total_chunks",
                "name",
                "summary",
                "priority",
                "pinned",
                "product_labels",
            ],
            num_results=1000,  # Set high limit to get all chunks
        )

        # Execute search
        results = await index.query(filter_query)

        if not results:
            return {
                "document_hash": document_hash,
                "error": "No fragments found for this document",
                "fragments": [],
            }

        # Sort fragments by chunk_index to maintain order
        fragments = sorted(
            results, key=lambda x: int(x.get("chunk_index", 0)) if x.get("chunk_index") else 0
        )

        # Normalize numeric fields to ints for stable assertions/consumers
        normalized_fragments = []
        for f in fragments:
            nf = dict(f)
            try:
                if nf.get("chunk_index") is not None and nf.get("chunk_index") != "":
                    nf["chunk_index"] = int(nf["chunk_index"])  # type: ignore
            except Exception:
                pass
            try:
                if nf.get("total_chunks") is not None and nf.get("total_chunks") != "":
                    nf["total_chunks"] = int(nf["total_chunks"])  # type: ignore
            except Exception:
                pass
            normalized_fragments.append(nf)

        # Get document metadata if requested
        metadata = {}
        if include_metadata:
            from redis_sre_agent.pipelines.ingestion.deduplication import (
                DocumentDeduplicator,
            )

            deduplicator = DocumentDeduplicator(index)
            metadata = await deduplicator.get_document_metadata(document_hash) or {}

        result = {
            "document_hash": document_hash,
            "fragments_count": len(normalized_fragments),
            "fragments": normalized_fragments,
            "title": metadata.get("title", ""),
            "source": metadata.get("source", ""),
            "category": metadata.get("category", ""),
            "document_type": metadata.get(
                "document_type",
                _normalized_doc_type(normalized_fragments[0])
                if normalized_fragments
                else "general",
            ),
            "name": metadata.get(
                "name", _doc_name(normalized_fragments[0]) if normalized_fragments else ""
            ),
            "summary": metadata.get(
                "summary",
                _doc_summary(normalized_fragments[0]) if normalized_fragments else "",
            ),
            "priority": metadata.get(
                "priority",
                _doc_priority(normalized_fragments[0]) if normalized_fragments else "normal",
            ),
            "pinned": _parse_bool(
                metadata.get("pinned"),
                default=_doc_is_pinned(normalized_fragments[0]) if normalized_fragments else False,
            ),
            "metadata": metadata,
        }

        logger.info(f"Retrieved {len(normalized_fragments)} fragments for document {document_hash}")
        return result

    except Exception as e:
        logger.error(f"Failed to retrieve document fragments: {e}")
        return {"document_hash": document_hash, "error": str(e), "fragments": []}


async def get_related_document_fragments(
    document_hash: str, current_chunk_index: Optional[int] = None, context_window: int = 2
) -> Dict[str, Any]:
    """
    Get related fragments around a specific chunk for additional context.

    This is useful when the agent finds a relevant fragment and wants to get
    surrounding context without retrieving the entire document.

    Args:
        document_hash: The document hash to get related fragments for
        current_chunk_index: The chunk index to get context around (if None, gets all)
        context_window: Number of chunks before and after to include

    Returns:
        Dictionary containing related fragments with context
    """
    logger.info(
        f"Getting related fragments for document {document_hash}, chunk {current_chunk_index}"
    )

    try:
        # Get all fragments first
        all_fragments_result = await get_all_document_fragments(
            document_hash, include_metadata=True
        )

        if "error" in all_fragments_result:
            return all_fragments_result

        fragments = all_fragments_result["fragments"]

        if current_chunk_index is None:
            # Return all fragments if no specific chunk specified
            return all_fragments_result

        # Filter to get context window around the specified chunk
        related_fragments = []
        current_chunk_int = (
            int(current_chunk_index)
            if isinstance(current_chunk_index, str)
            else current_chunk_index
        )
        start_index = max(0, current_chunk_int - context_window)
        end_index = min(len(fragments), current_chunk_int + context_window + 1)

        for i in range(start_index, end_index):
            if i < len(fragments):
                fragment = fragments[i]
                fragment["is_target_chunk"] = (
                    int(fragment.get("chunk_index", 0)) == current_chunk_int
                )
                related_fragments.append(fragment)

        # Reconstruct content from related fragments
        related_content = " ".join(f.get("content", "") for f in related_fragments)

        result = {
            "document_hash": document_hash,
            "target_chunk_index": current_chunk_index,
            "context_window": context_window,
            "related_fragments_count": len(related_fragments),
            "related_fragments": related_fragments,
            "related_content": related_content,
            "title": all_fragments_result.get("title", ""),
            "source": all_fragments_result.get("source", ""),
            "category": all_fragments_result.get("category", ""),
            "document_type": all_fragments_result.get("document_type", "general"),
            "metadata": all_fragments_result.get("metadata", {}),
        }

        logger.info(
            f"Retrieved {len(related_fragments)} related fragments for document {document_hash}"
        )
        return result

    except Exception as e:
        logger.error(f"Failed to retrieve related document fragments: {e}")
        return {"document_hash": document_hash, "error": str(e), "related_fragments": []}

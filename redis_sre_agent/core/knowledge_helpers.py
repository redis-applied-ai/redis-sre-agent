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
from redisvl.query import BaseQuery, FilterQuery, HybridQuery, VectorQuery, VectorRangeQuery
from redisvl.query.filter import FilterExpression, Tag
from redisvl.query.query import TokenEscaper
from ulid import ULID

from redis_sre_agent.core.config import Settings
from redis_sre_agent.core.redis import (
    get_knowledge_index,
    get_skills_index,
    get_support_tickets_index,
    get_vectorizer,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
_SOURCE_VERSION_RE = re.compile(r"/(\d+\.\d+)/")
_SPECIAL_DOCUMENT_TYPES = {"skill", "support_ticket"}
_PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}
_INDEX_TYPE_TO_PREFIX = {
    "knowledge": "sre_knowledge",
    "skills": "sre_skills",
    "support_tickets": "sre_support_tickets",
}
_SEARCH_RETURN_FIELDS = [
    "id",
    "document_hash",
    "chunk_index",
    "title",
    "content",
    "source",
    "category",
    "doc_type",
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
_EXACT_MATCH_TAG_FIELDS = ("name", "document_hash", "source")
_SUPPORT_TICKET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")
_TEXT_PHRASE_QUERY_FIELDS = ("title", "summary", "content")
_RRF_K = 60
_HYBRID_UNSUPPORTED_INDEX_TYPES: set[str] = set()


def _coerce_non_negative_int(value: Any, *, default: int) -> int:
    """Best-effort conversion for pagination args that may arrive as null/strings."""
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default
    return max(coerced, 0)


def _coerce_positive_int(value: Any, *, default: int) -> int:
    """Best-effort conversion for limits that must stay >= 1."""
    return max(_coerce_non_negative_int(value, default=default), 1)


def _is_unknown_field_error(exc: Exception, field_name: str) -> bool:
    """Return True when a RediSearch query failed because a field is missing."""
    message = str(exc).lower()
    return "unknown field" in message and field_name.lower() in message


class _RawTextQuery(BaseQuery):
    """Minimal raw-text query wrapper for literal phrase search."""

    def __init__(
        self,
        query_string: str,
        *,
        filter_expression: Optional[FilterExpression | str] = None,
        return_fields: Optional[List[str]] = None,
        num_results: int = 10,
        dialect: int = 2,
        return_score: bool = True,
    ):
        self._raw_query_string = query_string
        super().__init__("*")
        self.set_filter(filter_expression)

        if return_fields:
            self.return_fields(*return_fields)
        self.paging(0, num_results).dialect(dialect)

        if return_score:
            self.with_scores()

    def _build_query_string(self) -> str:
        filter_expression = self._filter_expression
        if isinstance(filter_expression, FilterExpression):
            filter_expression = str(filter_expression)

        text = self._raw_query_string
        if filter_expression and filter_expression != "*":
            text += f" {filter_expression}"
        return text


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
    """Normalize document type from doc_type fields."""
    doc_type = str(doc.get("doc_type") or doc.get("meta_doc_type") or "").strip().lower()
    return doc_type or "knowledge"


def _doc_matches_requested_version(doc: Dict[str, Any], requested_version: Optional[str]) -> bool:
    """Apply source-aware version matching."""
    if requested_version is None:
        return True

    source_version = _extract_version_from_source(str(doc.get("source", "")))
    doc_version = str(doc.get("version", "")).strip()

    if requested_version == "latest":
        # Canonical latest docs are unversioned paths.
        return source_version == "latest"

    return source_version == requested_version or doc_version == requested_version


def _doc_matches_requested_type(doc: Dict[str, Any], requested_type: Optional[str]) -> bool:
    """Apply document type filtering."""
    if requested_type is None:
        return True
    return _normalized_doc_type(doc) == requested_type.strip().lower()


def _doc_matches_requested_category(doc: Dict[str, Any], requested_category: Optional[str]) -> bool:
    """Apply category filtering when the caller requested one."""
    if requested_category is None:
        return True
    return str(doc.get("category", "")).strip().lower() == requested_category.strip().lower()


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


async def _get_index_for_type(index_type: str, config: Optional[Settings] = None):
    """Resolve an index getter by logical document type."""
    normalized = index_type.strip().lower()
    if normalized == "skills":
        return await get_skills_index(config=config)
    if normalized == "support_tickets":
        return await get_support_tickets_index(config=config)
    return await get_knowledge_index(config=config)


def _strip_outer_quotes(query: str) -> tuple[str, bool]:
    """Remove a single pair of wrapping quotes if present."""
    normalized_query = str(query or "").strip()
    quote_pairs = (('"', '"'), ("“", "”"), ("'", "'"))
    for start, end in quote_pairs:
        if (
            len(normalized_query) >= 2
            and normalized_query.startswith(start)
            and normalized_query.endswith(end)
        ):
            return normalized_query[len(start) : -len(end)].strip(), True
    return normalized_query, False


def _normalize_exact_match_query(query: str, index_type: str) -> str:
    """Normalize exact-match queries to the canonical stored value when possible."""
    normalized_query, _ = _strip_outer_quotes(query)
    return _normalize_exact_match_value(normalized_query, index_type)


def _normalize_exact_match_value(value: str, index_type: str) -> str:
    """Normalize an already-unquoted exact-match value when possible."""
    if index_type.strip().lower() == "support_tickets":
        return _normalize_support_ticket_id(value)
    return str(value or "").strip()


def _quote_tag_value(value: str) -> str:
    """Quote a RediSearch TAG value so punctuation is treated literally."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _tag_equals_expression(field_name: str, value: str) -> FilterExpression:
    """Build an exact TAG match expression that survives punctuation like `|`."""
    return FilterExpression(f"@{field_name}:{{{_quote_tag_value(value)}}}")


def _looks_like_precise_search_query(query: str, index_type: str) -> bool:
    """Heuristic for queries that benefit from exact-match plus hybrid retrieval."""
    normalized_query, was_quoted = _strip_outer_quotes(query)
    normalized_query = _normalize_exact_match_value(normalized_query, index_type)
    if not normalized_query or "\n" in normalized_query:
        return False

    if was_quoted:
        return True

    if " " in normalized_query:
        return False

    if index_type.strip().lower() == "support_tickets" and _SUPPORT_TICKET_ID_RE.match(
        normalized_query
    ):
        return True

    return any(char.isdigit() for char in normalized_query) or any(
        not char.isalnum() for char in normalized_query
    )


def _exact_match_sort_key(doc: Dict[str, Any], normalized_query: str) -> tuple[int, str, str, int]:
    """Prefer stronger exact matches before weaker exact-field hits."""
    lowered_query = normalized_query.lower()
    normalized_name = _doc_name(doc).strip().lower()
    document_hash = str(doc.get("document_hash") or "").strip().lower()
    source = str(doc.get("source") or "").strip().lower()

    if normalized_name == lowered_query:
        rank = 0
    elif document_hash == lowered_query:
        rank = 1
    elif source == lowered_query:
        rank = 2
    else:
        rank = 3

    return (rank, normalized_name, source, _doc_chunk_index(doc))


async def _find_exact_document_matches(
    query: str,
    *,
    index_type: str,
    version: Optional[str] = "latest",
    category: Optional[str] = None,
    doc_type: Optional[str] = None,
    config: Optional[Settings] = None,
    include_special_document_types: bool = False,
) -> List[Dict[str, Any]]:
    """Find exact matches on the stable indexed tag fields for a document index."""
    normalized_index_type = index_type.strip().lower()
    normalized_query = _normalize_exact_match_query(query, normalized_index_type)
    if not normalized_query:
        return []

    index = await _get_index_for_type(normalized_index_type, config=config)

    filter_expr = None
    for field_name in _EXACT_MATCH_TAG_FIELDS:
        field_expr = _tag_equals_expression(field_name, normalized_query)
        filter_expr = field_expr if filter_expr is None else (filter_expr | field_expr)

    if version is not None:
        version_expr = _tag_equals_expression("version", version)
        filter_expr = version_expr if filter_expr is None else (filter_expr & version_expr)
    if category is not None:
        category_expr = _tag_equals_expression("category", category)
        filter_expr = category_expr if filter_expr is None else (filter_expr & category_expr)
    if doc_type is not None:
        doc_type_expr = _tag_equals_expression("doc_type", doc_type.strip().lower())
        filter_expr = doc_type_expr if filter_expr is None else (filter_expr & doc_type_expr)

    rows = await index.query(
        FilterQuery(
            filter_expression=filter_expr,
            return_fields=_SEARCH_RETURN_FIELDS,
            num_results=50,
        )
    )

    candidates = [
        doc
        for doc in _dedupe_docs(rows)
        if _doc_matches_requested_version(doc, version)
        and _doc_matches_requested_category(doc, category)
        and _doc_matches_requested_type(doc, doc_type)
        and (
            normalized_index_type != "knowledge"
            or include_special_document_types
            or _doc_is_general_knowledge(doc)
        )
    ]

    by_document: Dict[str, Dict[str, Any]] = {}
    for doc in candidates:
        key = str(doc.get("document_hash") or doc.get("id") or "").strip()
        if not key:
            continue
        existing = by_document.get(key)
        if existing is None or _exact_match_sort_key(doc, normalized_query) < _exact_match_sort_key(
            existing, normalized_query
        ):
            by_document[key] = doc

    return sorted(
        by_document.values(),
        key=lambda doc: _exact_match_sort_key(doc, normalized_query),
    )


def _quoted_text_phrase_query(phrase: str) -> str:
    """Build a literal phrase query over the searchable TEXT fields."""
    escaped_phrase = phrase.lower().replace("\\", "\\\\").replace('"', '\\"')
    field_queries = []
    for field_name in _TEXT_PHRASE_QUERY_FIELDS:
        field_queries.append(f'@{field_name}:("{escaped_phrase}")')

    return "(" + " | ".join(field_queries) + ")"


def _hybrid_text_query(query: str) -> str:
    """Build a best-effort token query across searchable text fields."""
    escaper = TokenEscaper()
    tokens = [
        escaper.escape(token.strip().strip(",").replace("“", "").replace("”", "").lower())
        for token in str(query or "").split()
    ]
    tokens = [token for token in tokens if token]
    if not tokens:
        normalized_query, _ = _strip_outer_quotes(query)
        if not normalized_query:
            return "*"
        tokens = [escaper.escape(normalized_query.lower())]

    token_query = " | ".join(tokens)
    return (
        "(" + " | ".join(f"@{field}:({token_query})" for field in _TEXT_PHRASE_QUERY_FIELDS) + ")"
    )


def _doc_rrf_key(doc: Dict[str, Any]) -> tuple[Any, ...]:
    """Stable chunk-level key for reciprocal-rank fusion."""
    return (
        doc.get("id"),
        doc.get("document_hash"),
        doc.get("chunk_index"),
        doc.get("source"),
    )


def _reciprocal_rank_fuse(
    ranked_lists: List[List[Dict[str, Any]]],
    *,
    limit: int,
    rrf_k: int = _RRF_K,
) -> List[Dict[str, Any]]:
    """Merge ranked result sets with reciprocal-rank fusion."""
    scores: Dict[tuple[Any, ...], float] = {}
    docs_by_key: Dict[tuple[Any, ...], Dict[str, Any]] = {}
    first_rank: Dict[tuple[Any, ...], int] = {}
    first_list_index: Dict[tuple[Any, ...], int] = {}

    for list_index, ranked_docs in enumerate(ranked_lists):
        for rank, doc in enumerate(_dedupe_docs(ranked_docs), start=1):
            key = _doc_rrf_key(doc)
            if key not in docs_by_key:
                docs_by_key[key] = dict(doc)
                first_rank[key] = rank
                first_list_index[key] = list_index
            else:
                docs_by_key[key].update(
                    {field: value for field, value in doc.items() if value not in (None, "")}
                )
                first_rank[key] = min(first_rank[key], rank)

            scores[key] = scores.get(key, 0.0) + (1.0 / (rrf_k + rank))

    ordered_keys = sorted(
        docs_by_key,
        key=lambda key: (
            -scores.get(key, 0.0),
            first_list_index.get(key, 10**9),
            first_rank.get(key, 10**9),
            _doc_name(docs_by_key[key]).lower(),
            str(docs_by_key[key].get("source", "")).lower(),
            _doc_chunk_index(docs_by_key[key]),
        ),
    )

    fused = []
    for key in ordered_keys[:limit]:
        doc = dict(docs_by_key[key])
        doc["rrf_score"] = scores[key]
        fused.append(doc)
    return fused


def _is_hybrid_query_unsupported_error(exc: Exception) -> bool:
    """Whether Redis rejected the HybridQuery syntax/capability."""
    message = str(exc or "").lower()
    if "hybrid" not in message:
        return False
    return any(
        marker in message
        for marker in (
            "syntax error",
            "unknown argument",
            "unsupported",
            "not supported",
            "unknown keyword",
            "no such",
        )
    )


async def _run_hybrid_rrf_fallback(
    *,
    index: Any,
    query: str,
    query_vector: List[float],
    query_filter: Optional[FilterExpression],
    return_fields: List[str],
    num_results: int,
) -> List[Dict[str, Any]]:
    """Approximate HybridQuery semantics with separate RedisVL text/vector queries."""
    text_results = await index.query(
        _RawTextQuery(
            _hybrid_text_query(query),
            filter_expression=query_filter,
            return_fields=return_fields,
            num_results=num_results,
        )
    )
    vector_results = await index.query(
        VectorQuery(
            vector=query_vector,
            vector_field_name="vector",
            return_fields=return_fields,
            num_results=num_results,
            filter_expression=query_filter,
        )
    )
    return _reciprocal_rank_fuse([text_results, vector_results], limit=num_results)


def _result_score(doc: Dict[str, Any]) -> float:
    """Normalize text/vector scores for sorting merged results."""
    for key in ("score", "vector_distance", "distance"):
        value = doc.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except Exception:
            continue
    return 0.0


async def _find_precise_text_matches(
    query: str,
    *,
    index_type: str,
    version: Optional[str] = "latest",
    category: Optional[str] = None,
    doc_type: Optional[str] = None,
    config: Optional[Settings] = None,
    include_special_document_types: bool = False,
    force_literal_phrase: bool = False,
) -> List[Dict[str, Any]]:
    """Find literal quoted-phrase matches on TEXT fields."""
    phrase, was_quoted = _strip_outer_quotes(query)
    if not phrase or not (was_quoted or force_literal_phrase):
        return []

    normalized_index_type = index_type.strip().lower()
    index = await _get_index_for_type(normalized_index_type, config=config)

    filter_expr = None
    if version is not None:
        filter_expr = _tag_equals_expression("version", version)
    if category is not None:
        category_expr = _tag_equals_expression("category", category)
        filter_expr = category_expr if filter_expr is None else (filter_expr & category_expr)
    if doc_type is not None:
        doc_type_expr = _tag_equals_expression("doc_type", doc_type.strip().lower())
        filter_expr = doc_type_expr if filter_expr is None else (filter_expr & doc_type_expr)

    query_obj = _RawTextQuery(
        _quoted_text_phrase_query(phrase),
        filter_expression=filter_expr,
        return_fields=_SEARCH_RETURN_FIELDS,
        num_results=50,
    )
    rows = await index.query(query_obj)

    candidates = [
        doc
        for doc in _dedupe_docs(rows)
        if _doc_matches_requested_version(doc, version)
        and _doc_matches_requested_category(doc, category)
        and _doc_matches_requested_type(doc, doc_type)
        and (
            normalized_index_type != "knowledge"
            or include_special_document_types
            or _doc_is_general_knowledge(doc)
        )
    ]

    by_document: Dict[str, Dict[str, Any]] = {}
    for doc in candidates:
        key = str(doc.get("document_hash") or doc.get("id") or "").strip()
        if not key:
            continue
        existing = by_document.get(key)
        if existing is None or _result_score(doc) > _result_score(existing):
            by_document[key] = doc

    return sorted(
        by_document.values(),
        key=lambda doc: (
            -_result_score(doc),
            _doc_name(doc).lower(),
            str(doc.get("source", "")).lower(),
            _doc_chunk_index(doc),
        ),
    )


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
    limit = _coerce_positive_int(limit, default=20)
    offset = _coerce_non_negative_int(offset, default=0)
    logger.info(
        "Listing skills (query=%s, version=%s, offset=%s, limit=%s)",
        bool(query),
        version,
        offset,
        limit,
    )
    index = await get_skills_index(config=config)

    fetch_limit = min(max(limit + offset, 1) * 8, 1000)
    common_return_fields = [
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
    ]
    skills_return_fields = [
        *common_return_fields,
        "meta_name",
        "meta_summary",
        "meta_priority",
        "meta_pinned",
    ]

    if query:
        vectorizer = get_vectorizer()
        vectors = await vectorizer.aembed_many([query])
        query_vector = vectors[0] if vectors else []

        def _skill_vector_query(query_return_fields: list[str]):
            if distance_threshold is not None:
                q = VectorRangeQuery(
                    vector=query_vector,
                    vector_field_name="vector",
                    return_fields=query_return_fields,
                    num_results=fetch_limit,
                    distance_threshold=distance_threshold,
                )
            else:
                q = VectorQuery(
                    vector=query_vector,
                    vector_field_name="vector",
                    return_fields=query_return_fields,
                    num_results=fetch_limit,
                )
            return q

        candidates = await index.query(_skill_vector_query(skills_return_fields))
    else:
        candidates = await index.query(
            FilterQuery(
                filter_expression=Tag("document_hash") != "",
                return_fields=skills_return_fields,
                num_results=fetch_limit,
            )
        )

    candidates = [{**doc, "_index_type": "skills"} for doc in candidates]

    candidates = [
        doc
        for doc in _dedupe_docs(candidates)
        if _doc_matches_requested_version(doc, version) and not _doc_is_pinned(doc)
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
            "index_type": str(doc.get("_index_type", "skills")),
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
    normalized_name = skill_name.strip()
    if not normalized_name:
        return {
            "skill_name": skill_name,
            "error": "Skill name is required",
        }

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
        "doc_type",
        "version",
    ]

    async def _query_by_name(index_type: str) -> list[dict]:
        index = await _get_index_for_type(index_type)
        query = FilterQuery(
            filter_expression=_tag_equals_expression("name", normalized_name),
            return_fields=return_fields,
            num_results=50,
        )
        rows = await index.query(query)
        return [{**row, "_index_type": index_type} for row in rows]

    candidates = await _query_by_name("skills")

    candidates = [
        doc
        for doc in _dedupe_docs(candidates)
        if _doc_matches_requested_version(doc, version) and not _doc_is_pinned(doc)
    ]

    by_document: Dict[str, Dict[str, Any]] = {}
    for doc in candidates:
        key = str(doc.get("document_hash") or doc.get("id") or "").strip()
        if not key:
            continue
        existing = by_document.get(key)
        if existing is None or _doc_chunk_index(doc) < _doc_chunk_index(existing):
            by_document[key] = doc

    ordered = sorted(
        by_document.values(),
        key=lambda d: (_doc_name(d).lower(), str(d.get("source", "")).lower()),
    )
    target = next(
        (doc for doc in ordered if _doc_name(doc).strip().lower() == normalized_name.lower()),
        ordered[0] if ordered else None,
    )

    if target is None:
        # Fallback only for the not-found path: provide a short list of nearby skills.
        skills_result = await skills_check_helper(
            query=skill_name, limit=50, offset=0, version=version
        )
        skills = skills_result.get("skills") or []
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
    target_index_type = str(target.get("_index_type") or target.get("index_type") or "skills")

    result = await get_all_document_fragments(
        document_hash=document_hash,
        include_metadata=True,
        index_type=target_index_type,
        version=version,
    )

    fragments = result.get("fragments") or []
    if not fragments:
        return {
            "skill_name": skill_name,
            "document_hash": document_hash,
            **result,
        }

    normalized_type = str(
        result.get("doc_type") or _normalized_doc_type(fragments[0])  # type: ignore[index]
    ).lower()
    if normalized_type != "skill":
        return {
            "skill_name": skill_name,
            "document_hash": document_hash,
            "error": f"Document type is '{normalized_type}', not 'skill'",
            "doc_type": normalized_type,
        }

    sorted_fragments = sorted(fragments, key=lambda x: _doc_chunk_index(x))
    full_content = "\n\n".join(str(f.get("content", "")).strip() for f in sorted_fragments).strip()

    return {
        "skill_name": _doc_name({"name": target.get("name"), "title": result.get("title", "")}),
        "full_content": full_content,
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
    limit = _coerce_positive_int(limit, default=10)
    offset = _coerce_non_negative_int(offset, default=0)
    # Fetch one extra page so per-ticket dedupe still has enough rows to fill
    # the requested page when multiple chunks collapse into the same ticket.
    effective_limit = limit + offset + max(limit, 1)
    result = await search_knowledge_base_helper(
        query=query,
        limit=effective_limit,
        offset=0,
        distance_threshold=distance_threshold,
        hybrid_search=hybrid_search or _looks_like_support_ticket_identifier(query),
        version=version,
        config=config,
        index_type="support_tickets",
    )

    tickets = []
    seen_ticket_keys: set[str] = set()
    for ticket in result.get("results", []):
        ticket_key = str(ticket.get("document_hash") or ticket.get("id") or "").strip()
        if ticket_key and ticket_key in seen_ticket_keys:
            continue
        if ticket_key:
            seen_ticket_keys.add(ticket_key)
        ticket_with_id = dict(ticket)
        ticket_with_id["ticket_id"] = _support_ticket_id_for_result(ticket)
        tickets.append(ticket_with_id)
    paged_tickets = tickets[offset : offset + limit]

    result.update(
        {
            "offset": offset,
            "limit": limit,
            "ticket_count": len(paged_tickets),
            "tickets": paged_tickets,
            "results": paged_tickets,
            "results_count": len(paged_tickets),
            "doc_type": "support_ticket",
            "doc_type_filter": "support_ticket",
        }
    )
    return result


def _normalize_support_ticket_id(ticket_id: str) -> str:
    """Normalize support ticket identifiers to document_hash form when possible."""
    raw_id = str(ticket_id or "").strip()
    if not raw_id:
        return raw_id

    # Convert indexed chunk keys like:
    #   sre_support_tickets:<document_hash>:chunk:<n>
    # to the canonical document hash expected by get_all_document_fragments().
    parts = raw_id.split(":")
    if len(parts) >= 4 and parts[0] == "sre_support_tickets" and parts[-2] == "chunk":
        return parts[1]

    return raw_id


def _looks_like_support_ticket_identifier(query: str) -> bool:
    """Best-effort detection for exact support ticket IDs like RET-4421."""
    normalized_query = _normalize_support_ticket_id(query)
    if not normalized_query or " " in normalized_query:
        return False
    if not _SUPPORT_TICKET_ID_RE.match(normalized_query):
        return False
    return any(char.isdigit() for char in normalized_query)


def _support_ticket_id_for_result(ticket: Dict[str, Any]) -> str:
    """Resolve the stable public ticket identifier for a search result."""
    for key in ("name", "meta_name"):
        value = str(ticket.get(key) or "").strip()
        if value:
            return value
    return _normalize_support_ticket_id(str(ticket.get("document_hash") or ticket.get("id") or ""))


async def _find_support_ticket_exact_matches(
    query: str,
    version: Optional[str] = "latest",
    config: Optional[Settings] = None,
) -> List[Dict[str, Any]]:
    """Find support tickets by exact indexed values."""
    return await _find_exact_document_matches(
        query=query,
        index_type="support_tickets",
        version=version,
        doc_type="support_ticket",
        config=config,
    )


async def get_support_ticket_helper(ticket_id: str) -> Dict[str, Any]:
    """Get complete content for a support ticket by ticket id."""
    normalized_ticket_id = _normalize_support_ticket_id(ticket_id)
    exact_matches = await _find_support_ticket_exact_matches(
        query=normalized_ticket_id,
        version=None,
    )
    resolved_document_hash = (
        str(exact_matches[0].get("document_hash") or normalized_ticket_id).strip()
        if exact_matches
        else normalized_ticket_id
    )
    result = await get_all_document_fragments(
        document_hash=resolved_document_hash,
        include_metadata=True,
        index_type="support_tickets",
    )
    fragments = result.get("fragments") or []
    if not fragments:
        return {
            "ticket_id": ticket_id,
            "normalized_ticket_id": normalized_ticket_id,
            "document_hash": resolved_document_hash,
            **result,
        }

    normalized_type = str(
        result.get("doc_type") or _normalized_doc_type(fragments[0])  # type: ignore[index]
    ).lower()
    if normalized_type != "support_ticket":
        return {
            "ticket_id": ticket_id,
            "document_hash": resolved_document_hash,
            "error": f"Document type is '{normalized_type}', not 'support_ticket'",
            "doc_type": normalized_type,
        }

    sorted_fragments = sorted(fragments, key=lambda x: _doc_chunk_index(x))
    full_content = "\n\n".join(str(f.get("content", "")).strip() for f in sorted_fragments).strip()
    metadata = result.get("metadata", {}) or {}
    return {
        "ticket_id": ticket_id,
        "document_hash": resolved_document_hash,
        "title": result.get("title", ""),
        "source": result.get("source", ""),
        "doc_type": normalized_type,
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
        "doc_type",
        "version",
    ]

    async def _query_rows(
        index_type: str, *, filter_expression: Optional[FilterExpression] = None
    ) -> List[Dict[str, Any]]:
        index = await _get_index_for_type(index_type, config=config)
        rows = await index.query(
            FilterQuery(
                filter_expression=filter_expression,
                return_fields=return_fields,
                num_results=2000,
            )
        )
        return [{**row, "_index_type": index_type} for row in rows]

    async def _query_pinned_rows(index_type: str) -> List[Dict[str, Any]]:
        try:
            return await _query_rows(index_type, filter_expression=Tag("pinned") == "true")
        except Exception as exc:
            if not _is_unknown_field_error(exc, "pinned"):
                raise
            logger.info(
                "Pinned field unavailable on %s index; falling back to unfiltered query",
                index_type,
            )
            return await _query_rows(index_type, filter_expression=Tag("document_hash") != "")

    rows: List[Dict[str, Any]] = []
    for index_type in ("knowledge", "skills", "support_tickets"):
        try:
            rows.extend(await _query_pinned_rows(index_type))
        except Exception as exc:
            logger.warning("Failed to load pinned docs from %s index: %s", index_type, exc)

    candidates = [
        row
        for row in _dedupe_docs(rows)
        if _doc_is_pinned(row) and _doc_matches_requested_version(row, version)
    ]

    def _index_rank(doc_type: str, index_type: str) -> int:
        if doc_type == "skill" and index_type == "skills":
            return 0
        if doc_type == "support_ticket" and index_type == "support_tickets":
            return 0
        if doc_type not in _SPECIAL_DOCUMENT_TYPES and index_type == "knowledge":
            return 0
        return 1

    by_document: Dict[str, Dict[str, Any]] = {}
    for row in candidates:
        doc_hash = str(row.get("document_hash") or row.get("id") or "").strip()
        if not doc_hash:
            continue
        doc_type = _normalized_doc_type(row)
        key = f"{doc_type}:{doc_hash}"
        index_type = str(row.get("_index_type", "knowledge"))
        rank = _index_rank(doc_type, index_type)
        existing = by_document.get(key)
        if existing is None or rank < int(existing.get("rank", 99)):
            by_document[key] = {"rank": rank, "rows": [row]}
        elif rank == int(existing.get("rank", 99)):
            existing_rows = list(existing.get("rows") or [])
            existing_rows.append(row)
            existing["rows"] = existing_rows

    docs = []
    for key, doc_info in by_document.items():
        chunks = list(doc_info.get("rows") or [])
        doc_hash = key.split(":", 1)[1] if ":" in key else key
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
                "doc_type": _normalized_doc_type(sample),
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
    doc_type: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    distance_threshold: Optional[float] = 0.8,
    hybrid_search: bool = False,
    version: Optional[str] = "latest",
    config: Optional[Settings] = None,
    index_type: str = "knowledge",
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
        doc_type: Optional document type filter
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
    limit = _coerce_positive_int(limit, default=10)
    offset = _coerce_non_negative_int(offset, default=0)
    logger.info(f"Searching SRE knowledge: '{query}' (version={version}, offset={offset})")
    normalized_index_type = index_type.strip().lower()
    index = await _get_index_for_type(normalized_index_type, config=config)
    normalized_doc_type = doc_type.strip().lower() if doc_type else None

    return_fields = list(_SEARCH_RETURN_FIELDS)

    # Build version filter expression if version is specified.
    # Source-aware filtering still runs post-query for canonical matching.
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

    exact_match_search = _looks_like_precise_search_query(query, normalized_index_type)
    precise_search = hybrid_search or exact_match_search
    exact_matches = (
        await _find_exact_document_matches(
            query=query,
            index_type=normalized_index_type,
            version=version,
            category=category,
            doc_type=normalized_doc_type,
            config=config,
            include_special_document_types=include_special_document_types,
        )
        if exact_match_search
        else []
    )
    precise_text_matches = (
        await _find_precise_text_matches(
            query=query,
            index_type=normalized_index_type,
            version=version,
            category=category,
            doc_type=normalized_doc_type,
            config=config,
            include_special_document_types=include_special_document_types,
            force_literal_phrase=exact_match_search,
        )
        if exact_match_search
        else []
    )
    effective_hybrid_search = hybrid_search or precise_search

    # We need to fetch more results if there's an offset, then slice.
    # This path merges exact/quoted prequery results with semantic results and
    # applies additional post-filtering, while the RedisVL HybridQuery path
    # does not expose paging directly.
    fetch_limit = limit + offset
    if version is not None or normalized_doc_type is not None:
        # Oversample when version filtering to improve recall after post-filtering.
        fetch_limit = min(fetch_limit * 4, 200)

    async def _run_query(query_filter, num_results: int):
        if effective_hybrid_search:
            if normalized_index_type in _HYBRID_UNSUPPORTED_INDEX_TYPES:
                logger.info(
                    "Using RedisVL RRF fallback for hybrid search on %s index: %s",
                    normalized_index_type,
                    query,
                )
                return await _run_hybrid_rrf_fallback(
                    index=index,
                    query=query,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    return_fields=return_fields,
                    num_results=num_results,
                )

            logger.info(f"Using hybrid search (vector + full-text) for query: {query}")
            hybrid_query = HybridQuery(
                vector=query_vector,
                vector_field_name="vector",
                text_field_name="content",
                text=query,
                num_results=num_results,
                return_fields=return_fields,
                filter_expression=query_filter,
            )
            try:
                return await index.query(hybrid_query)
            except Exception as exc:
                if not _is_hybrid_query_unsupported_error(exc):
                    raise
                logger.warning(
                    "HybridQuery unsupported on %s index; falling back to RedisVL RRF search: %s",
                    normalized_index_type,
                    exc,
                )
                _HYBRID_UNSUPPORTED_INDEX_TYPES.add(normalized_index_type)
                return await _run_hybrid_rrf_fallback(
                    index=index,
                    query=query,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    return_fields=return_fields,
                    num_results=num_results,
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
        return await index.query(q)

    # Perform vector search
    _t2 = time.monotonic()
    with tracer.start_as_current_span("knowledge.index.query") as _span:
        _span.set_attribute("limit", int(limit))
        _span.set_attribute("offset", int(offset))
        _span.set_attribute("hybrid_search", bool(effective_hybrid_search))
        _span.set_attribute("version", version or "all")
        _span.set_attribute(
            "distance_threshold",
            float(distance_threshold) if distance_threshold is not None else -1.0,
        )
        _span.set_attribute("query.filtered", bool(filter_expr is not None))
        all_results = await _run_query(filter_expr, fetch_limit)
    _t3 = time.monotonic()

    merged_results = _dedupe_docs([*exact_matches, *precise_text_matches, *all_results])
    filtered_results = [
        doc
        for doc in merged_results
        if _doc_matches_requested_version(doc, version)
        and _doc_matches_requested_category(doc, category)
        and _doc_matches_requested_type(doc, normalized_doc_type)
        and (
            normalized_index_type != "knowledge"
            or include_special_document_types
            or _doc_is_general_knowledge(doc)
        )
    ]

    # Category fallback: if a category filter returns nothing, retry without category
    # while preserving other filters such as version/doc_type.
    if category is not None and len(filtered_results) == 0:
        category_fallback_expr = Tag("version") == version if version is not None else None
        with tracer.start_as_current_span("knowledge.index.query") as _span:
            _span.set_attribute("limit", int(limit))
            _span.set_attribute("offset", int(offset))
            _span.set_attribute("hybrid_search", bool(effective_hybrid_search))
            _span.set_attribute("version", version or "all")
            _span.set_attribute(
                "distance_threshold",
                float(distance_threshold) if distance_threshold is not None else -1.0,
            )
            _span.set_attribute("query.filtered", bool(category_fallback_expr is not None))
            category_fallback_results = await _run_query(category_fallback_expr, fetch_limit)

        fallback_exact_matches = (
            await _find_exact_document_matches(
                query=query,
                index_type=normalized_index_type,
                version=version,
                category=None,
                doc_type=normalized_doc_type,
                config=config,
                include_special_document_types=include_special_document_types,
            )
            if exact_match_search
            else []
        )
        fallback_precise_text_matches = (
            await _find_precise_text_matches(
                query=query,
                index_type=normalized_index_type,
                version=version,
                category=None,
                doc_type=normalized_doc_type,
                config=config,
                include_special_document_types=include_special_document_types,
                force_literal_phrase=exact_match_search,
            )
            if exact_match_search
            else []
        )
        merged_fallback_results = _dedupe_docs(
            [*fallback_exact_matches, *fallback_precise_text_matches, *category_fallback_results]
        )
        filtered_results = [
            doc
            for doc in merged_fallback_results
            if _doc_matches_requested_version(doc, version)
            and _doc_matches_requested_type(doc, normalized_doc_type)
            and (
                normalized_index_type != "knowledge"
                or include_special_document_types
                or _doc_is_general_knowledge(doc)
            )
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
        "doc_type": normalized_doc_type,
        "doc_type_filter": normalized_doc_type,
        "version": version,
        "index_type": normalized_index_type,
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
                "doc_type": _normalized_doc_type(doc),
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
    doc_type: Optional[str] = None,
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
        doc_type: Optional document type (e.g., skill, support_ticket, runbook)
        product_labels: Optional list of product labels
        config: Optional Settings for dependency injection (testing)

    Returns:
        Dictionary with ingestion result including task_id, document_id, status, etc.
    """
    logger.info(f"Ingesting SRE document: {title} from {source}")

    normalized_doc_type = (doc_type or "knowledge").lower()
    index_type = "knowledge"
    if normalized_doc_type == "skill":
        index = await get_skills_index(config=config)
        index_type = "skills"
    elif normalized_doc_type == "support_ticket":
        index = await get_support_tickets_index(config=config)
        index_type = "support_tickets"
    else:
        index = await get_knowledge_index(config=config)
    vectorizer = get_vectorizer()

    # Create document embedding (as_buffer=True for Redis storage)
    content_vector = await vectorizer.aembed(content, as_buffer=True)

    # Prepare document data
    doc_id = str(ULID())
    key_prefix = _INDEX_TYPE_TO_PREFIX.get(index_type, "sre_knowledge")
    doc_key = f"{key_prefix}:{doc_id}"

    # Convert product_labels list to comma-separated string for tag field
    product_labels_str = ",".join(product_labels) if product_labels else ""
    document = {
        "id": doc_id,
        "title": title,
        "content": content,
        "source": source,
        "category": category,
        "doc_type": normalized_doc_type,
        "severity": severity,
        "name": title,
        "summary": "",
        "priority": "normal",
        "created_at": datetime.now(timezone.utc).timestamp(),
        "vector": content_vector,
        "product_labels": product_labels_str,
        "product_label_tags": product_labels_str,  # Duplicate for tag searching
        "pinned": "false",
    }

    # Store in vector index
    await index.load(data=[document], id_field="id", keys=[doc_key])

    result = {
        "task_id": str(ULID()),
        "document_id": doc_id,
        "title": title,
        "source": source,
        "category": category,
        "doc_type": normalized_doc_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ingested",
    }

    logger.info(f"Document ingested successfully: {doc_id}")
    return result


async def get_all_document_fragments(
    document_hash: str,
    include_metadata: bool = True,
    index_type: str = "knowledge",
    version: Optional[str] = None,
    config: Optional[Settings] = None,
) -> Dict[str, Any]:
    """
    Retrieve all fragments/chunks of a specific document.

    This function allows the agent to get the complete document when it finds
    a relevant fragment during search.

    Args:
        document_hash: The document hash to retrieve all fragments for
        include_metadata: Whether to include document metadata
        index_type: Which index to query ('knowledge', 'skills', 'support_tickets')
        version: Optional version filter for source-aware matching
        config: Optional Settings for dependency injection (testing)

    Returns:
        Dictionary containing all fragments and metadata of the document
    """
    logger.info(f"Retrieving all fragments for document: {document_hash}")

    try:
        # Get components
        normalized_index_type = index_type.strip().lower()
        index = await _get_index_for_type(normalized_index_type, config=config)

        # Use FT.SEARCH to find all chunks for this document
        # document_hash is indexed as a TAG field, so we can filter on it.
        # Tag values that include punctuation (e.g., '-') must be quoted.
        from redisvl.query import FilterQuery

        filter_query = FilterQuery(
            filter_expression=str(_tag_equals_expression("document_hash", document_hash)),
            return_fields=[
                "title",
                "content",
                "source",
                "category",
                "doc_type",
                "severity",
                "document_hash",
                "chunk_index",
                "total_chunks",
                "name",
                "summary",
                "priority",
                "pinned",
                "product_labels",
                "version",
            ],
            num_results=1000,  # Set high limit to get all chunks
        )

        # Execute search
        results = await index.query(filter_query)
        if version is not None:
            results = [doc for doc in results if _doc_matches_requested_version(doc, version)]

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

            deduplicator = DocumentDeduplicator(
                index,
                key_prefix=_INDEX_TYPE_TO_PREFIX.get(normalized_index_type, "sre_knowledge"),
            )
            metadata = await deduplicator.get_document_metadata(document_hash) or {}

        result = {
            "document_hash": document_hash,
            "index_type": normalized_index_type,
            "fragments_count": len(normalized_fragments),
            "fragments": normalized_fragments,
            "title": metadata.get("title", ""),
            "source": metadata.get("source", ""),
            "category": metadata.get("category", ""),
            "doc_type": metadata.get(
                "doc_type",
                _normalized_doc_type(normalized_fragments[0])
                if normalized_fragments
                else "knowledge",
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
            "doc_type": all_fragments_result.get("doc_type", "knowledge"),
            "metadata": all_fragments_result.get("metadata", {}),
        }

        logger.info(
            f"Retrieved {len(related_fragments)} related fragments for document {document_hash}"
        )
        return result

    except Exception as e:
        logger.error(f"Failed to retrieve related document fragments: {e}")
        return {"document_hash": document_hash, "error": str(e), "related_fragments": []}

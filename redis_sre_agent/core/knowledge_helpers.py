"""Helper functions for knowledge base operations.

These are the core implementation functions that do the actual work.
They are called by:
- Tasks (in core.tasks) for background execution via Docket
- Tools (in agent.knowledge_agent) for LLM access with custom docstrings
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from redisvl.query import HybridQuery, VectorQuery, VectorRangeQuery
from ulid import ULID

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_knowledge_index, get_vectorizer

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


async def search_knowledge_base_helper(
    query: str,
    category: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    distance_threshold: Optional[float] = 0.8,
    hybrid_search: bool = False,
    version: Optional[str] = "latest",
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
        limit: Maximum number of results
        offset: Number of results to skip (for pagination)
        distance_threshold: Cosine distance cutoff; None disables threshold
        hybrid_search: Whether to use hybrid search (vector + full-text)
        version: Version filter - "latest" (default), specific version like "7.8",
                 or None to return all versions

    Returns:
        Dictionary with search results including task_id, query, results, etc.
    """
    logger.info(f"Searching SRE knowledge: '{query}' (version={version}, offset={offset})")
    index = await get_knowledge_index()
    return_fields = [
        "id",
        "document_hash",
        # "chunk_index",
        "title",
        "content",
        "source",
        "category",
        "severity",
        "version",
    ]

    # Build version filter expression if version is specified
    from redisvl.query.filter import Tag

    filter_expr = None
    if version is not None:
        # Filter by specific version (e.g., "latest", "7.8", "7.4")
        filter_expr = Tag("version") == version
        logger.debug(f"Applying version filter: {version}")

    # Always use vector search (tests rely on embedding being used)
    vectorizer = get_vectorizer()

    # Measure embedding latency and trace it
    _t0 = time.monotonic()
    with tracer.start_as_current_span("knowledge.embed") as _span:
        _span.set_attribute("query.length", len(query))
        vectors = await vectorizer.aembed_many([query])
    _t1 = time.monotonic()

    query_vector = vectors[0] if vectors else []

    # We need to fetch more results if there's an offset, then slice
    # This is because RedisVL vector queries don't support offset directly
    fetch_limit = limit + offset

    if hybrid_search:
        logger.info(f"Using hybrid search (vector + full-text) for query: {query}")
        query_obj = HybridQuery(
            vector=query_vector,
            vector_field_name="vector",
            text_field_name="content",
            text=query,
            num_results=fetch_limit,
            return_fields=return_fields,
            filter_expression=filter_expr,
        )
    else:
        # Build pure vector query
        # distance_threshold default is 0.5; None disables threshold (pure KNN)
        effective_threshold = distance_threshold
        if effective_threshold is not None:
            query_obj = VectorRangeQuery(
                vector=query_vector,
                vector_field_name="vector",
                return_fields=return_fields,
                num_results=fetch_limit,
                distance_threshold=effective_threshold,
            )
        else:
            query_obj = VectorQuery(
                vector=query_vector,
                vector_field_name="vector",
                return_fields=return_fields,
                num_results=fetch_limit,
            )
        if filter_expr is not None:
            query_obj.set_filter(filter_expr)

    # Perform vector search
    _t2 = time.monotonic()
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
    _t3 = time.monotonic()

    # Apply offset by slicing results
    results = all_results[offset:] if offset > 0 else all_results

    search_result = {
        "query": query,
        "category": category,
        "version": version,
        "offset": offset,
        "limit": limit,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results_count": len(results),
        "total_fetched": len(all_results),
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
                "version": doc.get("version", "latest"),
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
    product_labels: Optional[List[str]] = None,
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

    Returns:
        Dictionary with ingestion result including task_id, document_id, status, etc.
    """
    logger.info(f"Ingesting SRE document: {title} from {source}")

    # Get components
    index = await get_knowledge_index()
    vectorizer = get_vectorizer()

    # Create document embedding (as_buffer=True for Redis storage)
    content_vector = await vectorizer.aembed(content, as_buffer=True)

    # Prepare document data
    doc_id = str(ULID())
    doc_key = RedisKeys.knowledge_document(doc_id)

    # Convert product_labels list to comma-separated string for tag field
    product_labels_str = ",".join(product_labels) if product_labels else ""

    document = {
        "id": doc_id,
        "title": title,
        "content": content,
        "source": source,
        "category": category,
        "severity": severity,
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
                "severity",
                "document_hash",
                "chunk_index",
                "total_chunks",
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
            from redis_sre_agent.pipelines.ingestion.deduplication import DocumentDeduplicator

            deduplicator = DocumentDeduplicator(index)
            metadata = await deduplicator.get_document_metadata(document_hash) or {}

        result = {
            "document_hash": document_hash,
            "fragments_count": len(normalized_fragments),
            "fragments": normalized_fragments,
            "title": metadata.get("title", ""),
            "source": metadata.get("source", ""),
            "category": metadata.get("category", ""),
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
            "metadata": all_fragments_result.get("metadata", {}),
        }

        logger.info(
            f"Retrieved {len(related_fragments)} related fragments for document {document_hash}"
        )
        return result

    except Exception as e:
        logger.error(f"Failed to retrieve related document fragments: {e}")
        return {"document_hash": document_hash, "error": str(e), "related_fragments": []}

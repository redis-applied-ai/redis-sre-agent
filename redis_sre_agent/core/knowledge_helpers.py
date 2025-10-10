"""Helper functions for knowledge base operations.

These are the core implementation functions that do the actual work.
They are called by:
- Tasks (in core.tasks) for background execution via Docket
- Tools (in agent.knowledge_agent) for LLM access with custom docstrings
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ulid import ULID

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_knowledge_index, get_vectorizer

logger = logging.getLogger(__name__)


async def search_knowledge_base_helper(
    query: str,
    category: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """Search the SRE knowledge base (core implementation).

    This is the core helper function that performs the actual search.
    Called by both the task (for background execution) and the tool (for LLM access).

    Args:
        query: Search query text
        category: Optional category filter (incident, maintenance, monitoring, etc.)
        limit: Maximum number of results

    Returns:
        Dictionary with search results including task_id, query, results, etc.
    """
    logger.info(f"Searching SRE knowledge: '{query}' in category '{category}'")

    # Get vector search components
    index = get_knowledge_index()
    vectorizer = get_vectorizer()

    # Create vector embedding for the query
    query_vectors = await vectorizer.embed_many([query])
    query_vector = query_vectors[0]

    # Build vector query
    from redisvl.query import VectorQuery

    vector_query = VectorQuery(
        vector=query_vector,
        vector_field_name="vector",
        return_fields=["title", "content", "source", "category", "severity"],
        num_results=limit,
    )

    # Build search filters
    if category:
        vector_query.set_filter(f"@category:{{{category}}}")

    # Perform vector search
    async with index:
        results = await index.query(vector_query)

    search_result = {
        "task_id": str(ULID()),
        "query": query,
        "category": category,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results_count": len(results),
        "results": [
            {
                "title": doc.get("title", ""),
                "content": doc.get("content", "")[:500],  # Truncate for response
                "source": doc.get("source", ""),
                "score": doc.get("score", 0.0),
            }
            for doc in results
        ],
    }

    logger.info(f"Knowledge search completed: {search_result['task_id']} ({len(results)} results)")
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
    index = get_knowledge_index()
    vectorizer = get_vectorizer()

    # Create document embedding (use as_buffer=True for Redis storage)
    # Note: vectorizer.embed returns bytes when as_buffer=True
    content_vector = await asyncio.to_thread(vectorizer._inner.embed, content, as_buffer=True)

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
        index = get_knowledge_index()

        # Use FT.SEARCH to find all chunks for this document
        # document_hash is indexed as a TAG field, so we can filter on it
        from redisvl.query import FilterQuery

        filter_query = FilterQuery(
            filter_expression=f"@document_hash:{{{document_hash}}}",
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
        async with index:
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

        # Get document metadata if requested
        metadata = {}
        if include_metadata:
            from redis_sre_agent.pipelines.ingestion.deduplication import DocumentDeduplicator

            deduplicator = DocumentDeduplicator(index)
            metadata = await deduplicator.get_document_metadata(document_hash) or {}

        result = {
            "document_hash": document_hash,
            "fragments_count": len(fragments),
            "fragments": fragments,
            "title": metadata.get("title", ""),
            "source": metadata.get("source", ""),
            "category": metadata.get("category", ""),
            "metadata": metadata,
        }

        logger.info(f"Retrieved {len(fragments)} fragments for document {document_hash}")
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

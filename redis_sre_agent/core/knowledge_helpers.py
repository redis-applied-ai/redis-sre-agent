"""Helper functions for knowledge base operations."""

import logging
from typing import Any, Dict, Optional

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_knowledge_index, get_redis_client

logger = logging.getLogger(__name__)


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
        redis_client = get_redis_client()

        # Find all chunks for this document
        pattern = RedisKeys.knowledge_chunk_pattern(document_hash)
        chunk_keys = []

        async for key in redis_client.scan_iter(match=pattern):
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            chunk_keys.append(key)

        if not chunk_keys:
            return {
                "document_hash": document_hash,
                "error": "No fragments found for this document",
                "fragments": [],
            }

        # Sort chunk keys by chunk index to maintain order
        chunk_keys.sort(key=lambda k: int(k.split(":")[-1]) if k.split(":")[-1].isdigit() else 0)

        # Retrieve all chunks
        fragments = []
        for key in chunk_keys:
            chunk_data = await redis_client.hgetall(key)
            if chunk_data:
                # Convert bytes to strings, but skip binary fields like vectors
                fragment = {}
                for k, v in chunk_data.items():
                    # Decode key
                    key_str = k.decode("utf-8") if isinstance(k, bytes) else k

                    # Skip vector field (binary data) and other binary fields
                    if key_str in ["vector"]:
                        continue

                    # Decode value safely
                    if isinstance(v, bytes):
                        try:
                            value_str = v.decode("utf-8")
                        except UnicodeDecodeError:
                            # Skip fields that can't be decoded (likely binary)
                            continue
                    else:
                        value_str = v

                    fragment[key_str] = value_str

                fragments.append(fragment)

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

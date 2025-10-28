"""
Document deduplication and replacement logic for ingestion pipeline.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from redis_sre_agent.core.keys import RedisKeys

logger = logging.getLogger(__name__)


class DocumentDeduplicator:
    """Handles document deduplication and replacement during ingestion."""

    def __init__(self, index: Any):
        self.index = index

    def generate_deterministic_chunk_key(self, document_hash: str, chunk_index: int) -> str:
        """Generate deterministic key for a document chunk."""
        return RedisKeys.knowledge_chunk(document_hash, chunk_index)

    def generate_document_tracking_key(self, document_hash: str) -> str:
        """Generate key for tracking document metadata."""
        return f"sre_knowledge_meta:{document_hash}"

    async def find_existing_chunks(self, document_hash: str) -> List[str]:
        """Find all existing chunk keys for a document.

        Supports both current and legacy key formats to avoid duplicate leftovers
        after schema changes:
        - Current: sre_knowledge:{document_hash}:chunk:{index}
        - Legacy:  sre_knowledge:{document_hash}_{index}
        """
        try:
            # Get Redis client from the index (already initialized)
            redis_client = self.index.client

            existing_keys: List[str] = []

            # Current key format
            try:
                current_pattern = RedisKeys.knowledge_chunk_pattern(document_hash)
                async for key in redis_client.scan_iter(match=current_pattern):
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")
                    existing_keys.append(key)
            except Exception as e:
                logger.debug(f"scan_iter current pattern failed for {document_hash}: {e}")

            # Legacy key format (pre-deduplicator)
            try:
                legacy_pattern = f"{RedisKeys.PREFIX_KNOWLEDGE}:{document_hash}_*"
                async for key in redis_client.scan_iter(match=legacy_pattern):
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")
                    existing_keys.append(key)
            except Exception as e:
                logger.debug(f"scan_iter legacy pattern failed for {document_hash}: {e}")

            # De-duplicate any overlaps just in case
            unique_keys = list(dict.fromkeys(existing_keys))

            logger.debug(f"Found {len(unique_keys)} existing chunks for document {document_hash}")
            return unique_keys

        except Exception as e:
            logger.error(f"Failed to find existing chunks for {document_hash}: {e}")
            return []

    async def delete_existing_chunks(self, document_hash: str) -> int:
        """Delete all existing chunks for a document."""
        existing_keys = await self.find_existing_chunks(document_hash)

        if not existing_keys:
            return 0

        try:
            redis_client = self.index.client
            deleted_count = await redis_client.delete(*existing_keys)
            logger.info(f"Deleted {deleted_count} existing chunks for document {document_hash}")
            return int(deleted_count)

        except Exception as e:
            logger.error(f"Failed to delete existing chunks for {document_hash}: {e}")
            return 0

    async def update_document_metadata(self, document_hash: str, metadata: Dict[str, Any]) -> None:
        """Update document-level metadata tracking."""
        try:
            redis_client = self.index.client
            tracking_key = self.generate_document_tracking_key(document_hash)

            metadata_with_timestamp = {
                **metadata,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "document_hash": document_hash,
            }

            await redis_client.hset(tracking_key, mapping=metadata_with_timestamp)
            logger.debug(f"Updated document metadata for {document_hash}")

        except Exception as e:
            logger.error(f"Failed to update document metadata for {document_hash}: {e}")

    async def get_document_metadata(self, document_hash: str) -> Optional[Dict[str, Any]]:
        """Get document-level metadata."""
        try:
            redis_client = self.index.client
            tracking_key = self.generate_document_tracking_key(document_hash)

            metadata = await redis_client.hgetall(tracking_key)

            if metadata:
                # Convert bytes keys/values to strings
                return {
                    k.decode("utf-8") if isinstance(k, bytes) else k: (
                        v.decode("utf-8") if isinstance(v, bytes) else v
                    )
                    for k, v in metadata.items()
                }
            return None

        except Exception as e:
            logger.error(f"Failed to get document metadata for {document_hash}: {e}")
            return None

    async def get_existing_chunks_with_hashes(
        self, document_hash: str
    ) -> Dict[str, Dict[str, Any]]:
        """Get existing chunks with their content hashes and embeddings for reuse."""
        try:
            redis_client = self.index.client
            pattern = RedisKeys.knowledge_chunk_pattern(document_hash)

            existing_chunks = {}
            async for key in redis_client.scan_iter(match=pattern):
                if isinstance(key, bytes):
                    key = key.decode("utf-8")

                # Get the chunk data (hash storage)
                chunk_data = await redis_client.hgetall(key)
                if chunk_data:
                    # Extract content_hash and vector
                    content_hash = chunk_data.get(b"content_hash") or chunk_data.get("content_hash")
                    if isinstance(content_hash, bytes):
                        content_hash = content_hash.decode("utf-8")

                    vector = chunk_data.get(b"vector") or chunk_data.get("vector")

                    if content_hash and vector:
                        existing_chunks[key] = {
                            "content_hash": content_hash,
                            "vector": vector,
                        }

            logger.debug(
                f"Found {len(existing_chunks)} existing chunks with hashes for document {document_hash}"
            )
            return existing_chunks

        except Exception as e:
            logger.error(f"Failed to get existing chunks with hashes for {document_hash}: {e}")
            return {}

    async def should_replace_document(
        self, document_hash: str, new_content_hash: Optional[str] = None
    ) -> bool:
        """Determine if a document should be replaced."""
        existing_metadata = await self.get_document_metadata(document_hash)

        if not existing_metadata:
            # Document doesn't exist, always ingest
            return True

        # If we have a content hash, compare it
        if new_content_hash:
            existing_content_hash = existing_metadata.get("content_hash")
            if existing_content_hash != new_content_hash:
                logger.info(f"Document {document_hash} content changed, will replace")
                return True
            else:
                logger.debug(f"Document {document_hash} content unchanged, skipping")
                return False

        # If no content hash provided, assume we should replace
        return True

    def prepare_chunks_for_replacement(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare chunks with deterministic keys for replacement-safe indexing."""
        prepared_chunks = []

        for chunk in chunks:
            document_hash = chunk["document_hash"]
            chunk_index = chunk["chunk_index"]

            # Create deterministic key
            deterministic_key = self.generate_deterministic_chunk_key(document_hash, chunk_index)

            # Update chunk with deterministic ID
            prepared_chunk = {
                **chunk,
                "id": deterministic_key,  # Use deterministic key as ID
                "chunk_key": deterministic_key,  # Also store as separate field
            }

            prepared_chunks.append(prepared_chunk)

        return prepared_chunks

    async def replace_document_chunks(self, chunks: List[Dict[str, Any]], vectorizer: Any) -> int:
        """Replace chunks for a document, reusing embeddings for unchanged chunks."""
        if not chunks:
            return 0

        # Get document hash from first chunk
        document_hash = chunks[0]["document_hash"]

        # Check if we should replace this document
        should_replace = await self.should_replace_document(document_hash)
        if not should_replace:
            logger.info(f"Skipping document {document_hash} - no changes detected")
            return 0

        try:
            # Step 1: Get existing chunks with their content hashes and embeddings
            existing_chunks = await self.get_existing_chunks_with_hashes(document_hash)

            # Step 2: Prepare chunks with deterministic keys and compute content hashes
            prepared_chunks = self.prepare_chunks_for_replacement(chunks)

            # Step 3: Separate chunks into "reuse embedding" vs "need embedding"
            chunks_to_embed = []
            chunks_to_embed_indices = []
            reused_embeddings = {}

            for i, chunk in enumerate(prepared_chunks):
                # Compute content hash for this chunk
                content_hash = hashlib.sha256(chunk["content"].encode()).hexdigest()
                chunk["content_hash"] = content_hash  # Store for later

                chunk_key = chunk["chunk_key"]
                existing = existing_chunks.get(chunk_key)

                if existing and existing.get("content_hash") == content_hash:
                    # Content unchanged - reuse existing embedding!
                    reused_embeddings[i] = existing["vector"]
                    logger.debug(f"Reusing embedding for chunk {chunk_key}")
                else:
                    # Content changed or new - need to embed
                    chunks_to_embed.append(chunk["content"])
                    chunks_to_embed_indices.append(i)

            # Step 4: Batch embed only the changed/new chunks
            new_embeddings = []
            if chunks_to_embed:
                logger.info(
                    f"Embedding {len(chunks_to_embed)} changed/new chunks "
                    f"(reusing {len(reused_embeddings)} unchanged)"
                )
                new_embeddings = await vectorizer.aembed_many(chunks_to_embed, as_buffer=True)
            else:
                logger.info(f"All {len(prepared_chunks)} chunks unchanged, reusing embeddings")

            # Step 5: Combine reused and new embeddings in correct order
            all_embeddings = []
            new_emb_idx = 0
            for i in range(len(prepared_chunks)):
                if i in reused_embeddings:
                    all_embeddings.append(reused_embeddings[i])
                else:
                    all_embeddings.append(new_embeddings[new_emb_idx])
                    new_emb_idx += 1

            # Step 6: Prepare documents for indexing
            documents_to_index = []
            for i, chunk in enumerate(prepared_chunks):
                # Handle product labels specially for Redis schema
                product_labels = ""
                product_label_tags = ""

                # Flatten metadata
                flattened_metadata = {}
                if isinstance(chunk.get("metadata"), dict):
                    for key, value in chunk["metadata"].items():
                        if key == "product_labels":
                            # Handle product labels as comma-separated string for Redis tags
                            if isinstance(value, list):
                                product_labels = ",".join(value)
                            else:
                                product_labels = str(value) if value else ""
                        elif key == "product_label_tags":
                            # Handle product label tags as comma-separated string for Redis tags
                            if isinstance(value, list):
                                product_label_tags = ",".join(value)
                            else:
                                product_label_tags = str(value) if value else ""
                        else:
                            # Regular metadata gets meta_ prefix
                            if value is None:
                                flattened_metadata[f"meta_{key}"] = ""
                            else:
                                flattened_metadata[f"meta_{key}"] = str(value)

                doc_for_index = {
                    "id": chunk["chunk_key"],  # Use deterministic key
                    "document_hash": chunk["document_hash"],
                    "content_hash": chunk[
                        "content_hash"
                    ],  # Store content hash for future deduplication
                    "title": chunk["title"],
                    "content": chunk["content"],
                    "source": chunk["source"],
                    "category": chunk["category"],
                    "doc_type": chunk["doc_type"],
                    "severity": chunk["severity"],
                    "chunk_index": chunk["chunk_index"],
                    "vector": all_embeddings[i],
                    "created_at": datetime.now(timezone.utc).timestamp(),
                    "product_labels": product_labels,
                    "product_label_tags": product_label_tags,
                    **flattened_metadata,
                }
                documents_to_index.append(doc_for_index)

            # Step 7: Delete old chunks (do this after we have new embeddings ready)
            deleted_count = await self.delete_existing_chunks(document_hash)
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} old chunks for document {document_hash}")

            # Step 8: Create deterministic keys for Redis
            keys = [chunk["chunk_key"] for chunk in prepared_chunks]

            # Step 9: Index in Redis
            await self.index.load(data=documents_to_index, id_field="id", keys=keys)

            # Step 10: Update document metadata tracking
            await self.update_document_metadata(
                document_hash,
                {
                    "title": chunks[0].get("title", ""),
                    "source": chunks[0].get("source", ""),
                    "category": chunks[0].get("category", ""),
                    "chunk_count": len(chunks),
                    "total_content_length": sum(len(chunk.get("content", "")) for chunk in chunks),
                },
            )

            logger.info(
                f"Successfully indexed {len(documents_to_index)} chunks for document {document_hash} "
                f"({len(chunks_to_embed)} new embeddings, {len(reused_embeddings)} reused)"
            )
            return len(documents_to_index)

        except Exception as e:
            logger.error(f"Failed to replace chunks for document {document_hash}: {e}")
            raise

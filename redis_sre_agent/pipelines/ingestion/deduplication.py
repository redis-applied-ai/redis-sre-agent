"""
Document deduplication and replacement logic for ingestion pipeline.
"""

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
        """Find all existing chunk keys for a document."""
        try:
            # Connect the index if not already connected
            if not self.index.client:
                await self.index.connect()

            # Get Redis client from the index
            redis_client = self.index.client

            # Search for all chunks with this document hash
            pattern = RedisKeys.knowledge_chunk_pattern(document_hash)
            existing_keys = []

            async for key in redis_client.scan_iter(match=pattern):
                if isinstance(key, bytes):
                    key = key.decode("utf-8")
                existing_keys.append(key)

            logger.debug(f"Found {len(existing_keys)} existing chunks for document {document_hash}")
            return existing_keys

        except Exception as e:
            logger.error(f"Failed to find existing chunks for {document_hash}: {e}")
            return []

    async def delete_existing_chunks(self, document_hash: str) -> int:
        """Delete all existing chunks for a document."""
        existing_keys = await self.find_existing_chunks(document_hash)

        if not existing_keys:
            return 0

        try:
            # Connect the index if not already connected
            if not self.index.client:
                await self.index.connect()

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
            # Connect the index if not already connected
            if not self.index.client:
                await self.index.connect()

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
            # Connect the index if not already connected
            if not self.index.client:
                await self.index.connect()

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
        """Replace all chunks for a document atomically."""
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
            # Step 1: Delete existing chunks
            deleted_count = await self.delete_existing_chunks(document_hash)
            if deleted_count > 0:
                logger.info(
                    f"Replaced {deleted_count} existing chunks for document {document_hash}"
                )

            # Step 2: Prepare chunks with deterministic keys
            prepared_chunks = self.prepare_chunks_for_replacement(chunks)

            # Step 3: Generate embeddings
            chunk_texts = [chunk["content"] for chunk in prepared_chunks]
            embeddings = []
            for text in chunk_texts:
                embedding = vectorizer.embed(text, as_buffer=True)
                embeddings.append(embedding)

            # Step 4: Prepare documents for indexing
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
                    "title": chunk["title"],
                    "content": chunk["content"],
                    "source": chunk["source"],
                    "category": chunk["category"],
                    "doc_type": chunk["doc_type"],
                    "severity": chunk["severity"],
                    "chunk_index": chunk["chunk_index"],
                    "vector": embeddings[i],
                    "created_at": datetime.now(timezone.utc).timestamp(),
                    "product_labels": product_labels,
                    "product_label_tags": product_label_tags,
                    **flattened_metadata,
                }
                documents_to_index.append(doc_for_index)

            # Step 5: Create deterministic keys for Redis
            keys = [chunk["chunk_key"] for chunk in prepared_chunks]

            # Step 6: Index in Redis
            await self.index.load(data=documents_to_index, id_field="id", keys=keys)

            # Step 7: Update document metadata tracking
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
                f"Successfully indexed {len(documents_to_index)} chunks for document {document_hash}"
            )
            return len(documents_to_index)

        except Exception as e:
            logger.error(f"Failed to replace chunks for document {document_hash}: {e}")
            raise

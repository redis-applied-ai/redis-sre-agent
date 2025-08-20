"""Document ingestion and processing for vector store."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ulid import ULID

from ...core.redis import get_knowledge_index, get_vectorizer
from ...pipelines.scraper.base import ArtifactStorage, ScrapedDocument

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Processes scraped documents for vector store ingestion."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = {
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "min_chunk_size": 100,
            "max_chunks_per_doc": 10,
            **(config or {}),
        }

    def chunk_document(self, document: ScrapedDocument) -> List[Dict[str, Any]]:
        """Split document into chunks for vector storage."""
        content = document.content

        if len(content) <= self.config["chunk_size"]:
            # Document is small enough, use as single chunk
            return [self._create_chunk(document, content, 0)]

        # Split into overlapping chunks
        chunks = []
        chunk_size = self.config["chunk_size"]
        overlap = self.config["chunk_overlap"]
        max_chunks = self.config["max_chunks_per_doc"]

        start = 0
        chunk_index = 0

        while start < len(content) and chunk_index < max_chunks:
            end = start + chunk_size

            # Try to break at word boundaries
            if end < len(content):
                # Look for sentence ending
                sentence_break = content.rfind(".", start, end)
                if sentence_break > start + chunk_size // 2:
                    end = sentence_break + 1
                else:
                    # Look for word boundary
                    word_break = content.rfind(" ", start, end)
                    if word_break > start + chunk_size // 2:
                        end = word_break

            chunk_content = content[start:end].strip()

            if len(chunk_content) >= self.config["min_chunk_size"]:
                chunks.append(self._create_chunk(document, chunk_content, chunk_index))
                chunk_index += 1

            # Move start position with overlap
            start = end - overlap
            if start >= end:  # Prevent infinite loop
                break

        return chunks

    def _create_chunk(
        self, document: ScrapedDocument, content: str, chunk_index: int
    ) -> Dict[str, Any]:
        """Create a chunk object for vector storage."""
        chunk_id = str(ULID())

        # Create title for chunk
        if chunk_index == 0:
            chunk_title = document.title
        else:
            chunk_title = f"{document.title} (Part {chunk_index + 1})"

        return {
            "id": chunk_id,
            "document_hash": document.content_hash,
            "title": chunk_title,
            "content": content,
            "source": document.source_url,
            "category": document.category.value,
            "doc_type": document.doc_type.value,
            "severity": document.severity.value,
            "chunk_index": chunk_index,
            "metadata": {
                **document.metadata,
                "original_title": document.title,
                "chunk_size": len(content),
                "processed_at": datetime.now(timezone.utc).isoformat(),
            },
        }


class IngestionPipeline:
    """Main ingestion pipeline for processing artifact batches."""

    def __init__(self, storage: ArtifactStorage, config: Optional[Dict[str, Any]] = None):
        self.storage = storage
        self.processor = DocumentProcessor(config)
        self.config = config or {}

    async def ingest_batch(self, batch_date: str) -> Dict[str, Any]:
        """Ingest a complete batch of scraped documents."""
        logger.info(f"Starting ingestion for batch: {batch_date}")

        # Get batch manifest
        manifest = self.storage.get_batch_manifest(batch_date)
        if not manifest:
            raise ValueError(f"No manifest found for batch {batch_date}")

        batch_path = self.storage.base_path / batch_date
        if not batch_path.exists():
            raise ValueError(f"Batch directory not found: {batch_path}")

        # Initialize tracking
        ingestion_stats = {
            "batch_date": batch_date,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "documents_processed": 0,
            "chunks_created": 0,
            "chunks_indexed": 0,
            "categories_processed": {},
            "errors": [],
            "success": False,
        }

        try:
            # Get Redis components
            index = get_knowledge_index()
            vectorizer = get_vectorizer()

            # Process each category
            for category in ["oss", "enterprise", "shared"]:
                category_path = batch_path / category
                if not category_path.exists():
                    continue

                category_stats = await self._process_category(
                    category_path, category, index, vectorizer
                )

                ingestion_stats["categories_processed"][category] = category_stats
                ingestion_stats["documents_processed"] += category_stats["documents_processed"]
                ingestion_stats["chunks_created"] += category_stats["chunks_created"]
                ingestion_stats["chunks_indexed"] += category_stats["chunks_indexed"]
                ingestion_stats["errors"].extend(category_stats["errors"])

            ingestion_stats["completed_at"] = datetime.now(timezone.utc).isoformat()
            ingestion_stats["success"] = True

            # Save ingestion manifest
            await self._save_ingestion_manifest(batch_date, ingestion_stats)

            logger.info(f"Ingestion completed for batch {batch_date}: {ingestion_stats}")

        except Exception as e:
            logger.error(f"Ingestion failed for batch {batch_date}: {e}")
            ingestion_stats["error"] = str(e)
            ingestion_stats["completed_at"] = datetime.now(timezone.utc).isoformat()
            raise

        return ingestion_stats

    async def _process_category(
        self, category_path: Path, category: str, index: Any, vectorizer: Any
    ) -> Dict[str, Any]:
        """Process all documents in a category folder."""
        logger.info(f"Processing category: {category}")

        stats = {
            "category": category,
            "documents_processed": 0,
            "chunks_created": 0,
            "chunks_indexed": 0,
            "errors": [],
        }

        # Find all JSON files in category
        json_files = list(category_path.glob("*.json"))
        logger.info(f"Found {len(json_files)} documents in {category}")

        for json_file in json_files:
            try:
                # Load document
                with open(json_file, "r", encoding="utf-8") as f:
                    doc_data = json.load(f)

                document = ScrapedDocument.from_dict(doc_data)

                # Process document into chunks
                chunks = self.processor.chunk_document(document)
                stats["chunks_created"] += len(chunks)

                # Index chunks
                indexed_count = await self._index_chunks(chunks, index, vectorizer)
                stats["chunks_indexed"] += indexed_count

                stats["documents_processed"] += 1
                logger.debug(f"Processed document: {document.title} ({len(chunks)} chunks)")

            except Exception as e:
                error_msg = f"Failed to process {json_file}: {str(e)}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)

        return stats

    async def _index_chunks(self, chunks: List[Dict[str, Any]], index: Any, vectorizer: Any) -> int:
        """Index document chunks in the vector store."""
        if not chunks:
            return 0

        try:
            # Generate embeddings for all chunks
            chunk_texts = [chunk["content"] for chunk in chunks]
            embeddings = await vectorizer.embed_many(chunk_texts)

            # Prepare documents for indexing
            documents_to_index = []
            for i, chunk in enumerate(chunks):
                doc_for_index = {
                    **chunk,
                    "vector": embeddings[i],
                    "created_at": datetime.now(timezone.utc).timestamp(),
                }
                documents_to_index.append(doc_for_index)

            # Create keys for each document
            keys = [f"sre_knowledge:{chunk['id']}" for chunk in chunks]

            # Index in Redis
            await index.load(data=documents_to_index, id_field="id", keys=keys)

            logger.debug(f"Indexed {len(documents_to_index)} chunks")
            return len(documents_to_index)

        except Exception as e:
            logger.error(f"Failed to index chunks: {e}")
            raise

    async def _save_ingestion_manifest(self, batch_date: str, stats: Dict[str, Any]) -> None:
        """Save ingestion manifest with processing results."""
        manifest_path = self.storage.base_path / batch_date / "ingestion_manifest.json"

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, default=str)

        logger.info(f"Saved ingestion manifest: {manifest_path}")

    async def list_ingested_batches(self) -> List[Dict[str, Any]]:
        """List all batches that have been ingested."""
        batches = []

        for batch_date in self.storage.list_available_batches():
            batch_info = {"batch_date": batch_date}

            # Check if ingested
            ingestion_manifest = self.storage.base_path / batch_date / "ingestion_manifest.json"
            if ingestion_manifest.exists():
                with open(ingestion_manifest, "r", encoding="utf-8") as f:
                    ingestion_data = json.load(f)
                batch_info.update(ingestion_data)
            else:
                batch_info["ingested"] = False

            batches.append(batch_info)

        return sorted(batches, key=lambda x: x["batch_date"], reverse=True)

    async def reindex_batch(self, batch_date: str) -> Dict[str, Any]:
        """Re-ingest a batch (useful for schema changes or corrections)."""
        logger.info(f"Re-indexing batch: {batch_date}")

        # TODO: Optionally clear existing documents from this batch first
        # This would require tracking which documents came from which batch

        return await self.ingest_batch(batch_date)

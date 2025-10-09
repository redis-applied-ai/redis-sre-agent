"""Document ingestion and processing for vector store."""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.keys import RedisKeys
from ...core.redis import get_knowledge_index, get_vectorizer
from ...pipelines.scraper.base import (
    ArtifactStorage,
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    SeverityLevel,
)
from .deduplication import DocumentDeduplicator

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Processes scraped documents for vector store ingestion."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, knowledge_settings=None):
        # Use knowledge settings if provided, otherwise fall back to config or defaults
        if knowledge_settings:
            self.config = {
                "chunk_size": knowledge_settings.chunk_size,
                "chunk_overlap": knowledge_settings.chunk_overlap,
                "min_chunk_size": 100,  # Keep this as a reasonable minimum
                "max_chunks_per_doc": knowledge_settings.max_documents_per_batch,
                "splitting_strategy": knowledge_settings.splitting_strategy,
                "enable_metadata_extraction": knowledge_settings.enable_metadata_extraction,
                "enable_semantic_chunking": knowledge_settings.enable_semantic_chunking,
                "similarity_threshold": knowledge_settings.similarity_threshold,
                "embedding_model": knowledge_settings.embedding_model,
            }
        else:
            self.config = {
                "chunk_size": 1000,
                "chunk_overlap": 200,
                "min_chunk_size": 100,
                "max_chunks_per_doc": 10,
                "splitting_strategy": "recursive",
                "enable_metadata_extraction": True,
                "enable_semantic_chunking": False,
                "similarity_threshold": 0.7,
                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
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
        # Use document hash + chunk index for deterministic IDs instead of random ULID
        # This allows proper deduplication when re-ingesting the same document

        # Create title for chunk
        if chunk_index == 0:
            chunk_title = document.title
        else:
            chunk_title = f"{document.title} (Part {chunk_index + 1})"

        # Generate deterministic ID based on document hash and chunk index
        chunk_id = f"{document.content_hash}_{chunk_index}"

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

    def __init__(
        self,
        storage: ArtifactStorage,
        config: Optional[Dict[str, Any]] = None,
        knowledge_settings=None,
    ):
        self.storage = storage
        self.processor = DocumentProcessor(config, knowledge_settings)
        self.config = config or {}
        self.knowledge_settings = knowledge_settings

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

            # Initialize deduplicator
            deduplicator = DocumentDeduplicator(index)

            # Process each category
            for category in ["oss", "enterprise", "shared"]:
                category_path = batch_path / category
                if not category_path.exists():
                    continue

                category_stats = await self._process_category(
                    category_path, category, index, vectorizer, deduplicator
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
        self,
        category_path: Path,
        category: str,
        index: Any,
        vectorizer: Any,
        deduplicator: DocumentDeduplicator,
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

                # Index chunks with deduplication
                indexed_count = await deduplicator.replace_document_chunks(chunks, vectorizer)
                stats["chunks_indexed"] += indexed_count

                stats["documents_processed"] += 1
                logger.debug(f"Processed document: {document.title} ({len(chunks)} chunks)")

            except Exception as e:
                error_msg = f"Failed to process {json_file}: {str(e)}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)

        return stats

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

    def _parse_markdown_metadata(self, content: str) -> Dict[str, str]:
        """Extract metadata from markdown document."""
        metadata = {}

        # Extract title (first # heading)
        title_match = re.search(r"^# (.+)", content, re.MULTILINE)
        if title_match:
            metadata["title"] = title_match.group(1).strip()

        # Extract metadata lines (**Key**: value)
        metadata_pattern = r"^\*\*(\w+)\*\*:\s*(.+)$"
        for match in re.finditer(metadata_pattern, content, re.MULTILINE):
            key = match.group(1).lower()
            value = match.group(2).strip()
            metadata[key] = value

        return metadata

    def _create_scraped_document_from_markdown(self, md_file: Path) -> ScrapedDocument:
        """Convert a markdown file to a ScrapedDocument for processing."""
        content = md_file.read_text(encoding="utf-8")
        metadata = self._parse_markdown_metadata(content)

        # Extract or generate title
        title = metadata.get("title", md_file.stem.replace("-", " ").title())

        # Determine category from explicit metadata or directory structure
        category = self._determine_document_category(md_file, metadata)

        # Map severity strings to SeverityLevel enum
        severity_str = metadata.get("severity", "medium")
        severity_map = {
            "critical": SeverityLevel.CRITICAL,
            "high": SeverityLevel.HIGH,
            "warning": SeverityLevel.MEDIUM,
            "medium": SeverityLevel.MEDIUM,
            "low": SeverityLevel.LOW,
            "info": SeverityLevel.LOW,
        }
        severity = severity_map.get(severity_str.lower(), SeverityLevel.MEDIUM)

        return ScrapedDocument(
            title=title,
            source_url=f"file://{md_file.absolute()}",
            content=content,
            category=category,
            doc_type=DocumentType.RUNBOOK,
            severity=severity,
            metadata={
                "file_path": str(md_file),
                "file_size": md_file.stat().st_size,
                "original_category": metadata.get("category", "shared").lower(),
                "original_severity": severity_str,
                "determined_category": category.value,
                **metadata,
            },
        )

    def _determine_document_category(
        self, md_file: Path, metadata: Dict[str, Any]
    ) -> DocumentCategory:
        """Determine document category from explicit metadata or directory structure."""

        # 1. Check for explicit category in metadata
        explicit_category = metadata.get("category", "").lower()
        if explicit_category in ["oss", "enterprise", "shared", "cloud"]:
            category_map = {
                "oss": DocumentCategory.OSS,
                "enterprise": DocumentCategory.ENTERPRISE,
                "shared": DocumentCategory.SHARED,
                "cloud": DocumentCategory.SHARED,  # Cloud is a type of shared knowledge
            }
            return category_map[explicit_category]

        # 2. Determine from directory structure
        # Check if file is in a categorized subdirectory
        path_parts = md_file.parts
        for part in path_parts:
            if part in ["oss", "enterprise", "shared", "cloud"]:
                category_map = {
                    "oss": DocumentCategory.OSS,
                    "enterprise": DocumentCategory.ENTERPRISE,
                    "shared": DocumentCategory.SHARED,
                    "cloud": DocumentCategory.SHARED,
                }
                return category_map[part]

        # 3. Legacy handling: if no explicit category, default to shared
        # This handles existing documents that haven't been categorized yet
        return DocumentCategory.SHARED

    async def ingest_source_documents(self, source_dir: Path) -> List[Dict[str, Any]]:
        """Ingest runbook source documents from the source_documents directory."""
        logger.info(f"Ingesting source documents from: {source_dir}")

        if not source_dir.exists():
            raise ValueError(f"Source directory does not exist: {source_dir}")

        # Find all markdown files (excluding README files)
        markdown_files = list(source_dir.rglob("*.md"))
        markdown_files = [f for f in markdown_files if f.name.lower() != "readme.md"]

        if not markdown_files:
            logger.warning(f"No markdown files found in {source_dir}")
            return []

        logger.info(f"Found {len(markdown_files)} markdown files to process")

        # Get Redis components
        index = get_knowledge_index()
        vectorizer = get_vectorizer()

        # Initialize deduplicator
        deduplicator = DocumentDeduplicator(index)

        results = []

        for md_file in markdown_files:
            logger.info(f"Processing: {md_file.name}")

            try:
                # Convert markdown to ScrapedDocument
                document = self._create_scraped_document_from_markdown(md_file)

                # Process document into chunks
                chunks = self.processor.chunk_document(document)

                # Index chunks with deduplication
                indexed_count = await deduplicator.replace_document_chunks(chunks, vectorizer)

                result = {
                    "file": md_file.name,
                    "title": document.title,
                    "category": document.category,
                    "severity": document.severity,
                    "status": "success",
                    "chunks_created": len(chunks),
                    "chunks_indexed": indexed_count,
                }

                results.append(result)
                logger.info(
                    f"✅ Processed {md_file.name}: {len(chunks)} chunks, {indexed_count} indexed"
                )

            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Failed to process {md_file.name}: {error_msg}")

                result = {"file": md_file.name, "status": "error", "error": error_msg}
                results.append(result)

        return results

    async def prepare_source_artifacts(self, source_dir: Path, batch_date: str) -> int:
        """Prepare source documents as batch artifacts without ingesting."""
        logger.info(f"Preparing source artifacts from: {source_dir} for batch: {batch_date}")

        if not source_dir.exists():
            raise ValueError(f"Source directory does not exist: {source_dir}")

        # Find all markdown files (excluding README files)
        markdown_files = list(source_dir.rglob("*.md"))
        markdown_files = [f for f in markdown_files if f.name.lower() != "readme.md"]

        if not markdown_files:
            logger.warning(f"No markdown files found in {source_dir}")
            return 0

        logger.info(f"Found {len(markdown_files)} markdown files to prepare")

        prepared_count = 0
        prepared_documents = []

        for md_file in markdown_files:
            logger.info(f"Preparing artifact for: {md_file.name}")

            try:
                # Convert markdown to ScrapedDocument
                document = self._create_scraped_document_from_markdown(md_file)

                # Save as artifact using storage
                self.storage.save_document(document)
                prepared_documents.append(document)
                prepared_count += 1

                logger.info(f"✅ Prepared artifact for {md_file.name}")

            except Exception as e:
                logger.error(f"❌ Failed to prepare artifact for {md_file.name}: {e}")
                # Continue with other files rather than failing completely

        # Create batch manifest with all prepared documents
        if prepared_documents:
            self.storage.save_batch_manifest(prepared_documents)
            logger.info(f"✅ Created batch manifest for {len(prepared_documents)} documents")

        logger.info(f"Prepared {prepared_count} source documents as batch artifacts")
        return prepared_count

    async def ingest_prepared_batch(self, batch_date: str) -> List[Dict[str, Any]]:
        """Ingest a prepared batch using the standard batch ingestion process."""
        logger.info(f"Ingesting prepared batch: {batch_date}")

        # Use the existing batch ingestion logic from the main ingest_batch method
        batch_result = await self.ingest_batch(batch_date)

        # Convert the result format to match what the CLI expects
        if batch_result.get("success", False):
            return [{"status": "success", "batch_date": batch_date, **batch_result}]
        else:
            return [
                {"status": "error", "batch_date": batch_date, "error": "Batch ingestion failed"}
            ]

    async def _index_chunks(self, chunks: List[Dict[str, Any]], index: Any, vectorizer: Any) -> int:
        """Index chunks in the vector store.

        Args:
            chunks: List of chunk dictionaries to index
            index: Vector store index instance
            vectorizer: Vectorizer instance for embedding generation

        Returns:
            Number of chunks successfully indexed
        """
        if not chunks:
            return 0

        try:
            # Extract content for vectorization
            texts = [chunk["content"] for chunk in chunks]

            # Generate embeddings
            embeddings = await vectorizer.embed_many(texts)

            # Prepare chunks with embeddings for indexing
            indexed_chunks = []
            keys = []
            for chunk, embedding in zip(chunks, embeddings):
                chunk_with_embedding = {
                    **chunk,
                    "vector": embedding,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                indexed_chunks.append(chunk_with_embedding)
                keys.append(RedisKeys.knowledge_document(chunk["id"]))

            # Load chunks into index with expected parameters
            await index.load(id_field="id", keys=keys, data=indexed_chunks)

            return len(chunks)

        except Exception as e:
            logger.error(f"Failed to index {len(chunks)} chunks: {e}")
            raise

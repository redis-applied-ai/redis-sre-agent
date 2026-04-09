"""Document ingestion and processing for vector store."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.keys import RedisKeys

# Avoid importing Redis/vectorizer at module import time to keep optional deps lazy
from ...pipelines.scraper.base import ArtifactStorage, ScrapedDocument
from .deduplication import DocumentDeduplicator
from .document_processor import DocumentProcessor
from .pipeline_workflow_mixin import PipelineWorkflowMixin
from .processor_indexing_helpers import index_processed_document

logger = logging.getLogger(__name__)


# Expose patchable wrappers so tests can monkeypatch these names
async def get_knowledge_index():
    from ...core.redis import get_knowledge_index as _get_knowledge_index

    return await _get_knowledge_index()


async def get_skills_index():
    from ...core.redis import get_skills_index as _get_skills_index

    return await _get_skills_index()


async def get_support_tickets_index():
    from ...core.redis import get_support_tickets_index as _get_support_tickets_index

    return await _get_support_tickets_index()


def get_vectorizer():
    from ...core.redis import get_vectorizer as _get_vectorizer

    return _get_vectorizer()


class IngestionPipeline(PipelineWorkflowMixin):
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

    async def _build_deduplicators(self) -> Dict[str, DocumentDeduplicator]:
        """Initialize index-specific deduplicators."""
        knowledge_index = await get_knowledge_index()
        skills_index = await get_skills_index()
        support_tickets_index = await get_support_tickets_index()
        return {
            "knowledge": DocumentDeduplicator(knowledge_index, key_prefix="sre_knowledge"),
            "skill": DocumentDeduplicator(skills_index, key_prefix="sre_skills"),
            "support_ticket": DocumentDeduplicator(
                support_tickets_index,
                key_prefix="sre_support_tickets",
            ),
        }

    async def _list_tracked_source_documents(
        self, deduplicators: Dict[str, DocumentDeduplicator]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Collect tracked source-document records across all indices."""
        tracked_by_path: Dict[str, List[Dict[str, Any]]] = {}
        for deduplicator_key, deduplicator in deduplicators.items():
            tracked_documents = await deduplicator.list_tracked_source_documents()
            for source_document_path, metadata in tracked_documents.items():
                tracked_by_path.setdefault(source_document_path, []).append(
                    {"deduplicator_key": deduplicator_key, **metadata}
                )
        return tracked_by_path

    @staticmethod
    def _path_in_scope(source_document_path: str, scope_prefixes: set[str]) -> bool:
        """Return True when a tracked source file belongs to the active ingest scope."""
        if not scope_prefixes:
            return False
        if "" in scope_prefixes:
            return True
        return any(source_document_path.startswith(prefix) for prefix in scope_prefixes if prefix)

    @staticmethod
    def _empty_source_change_summary() -> Dict[str, Any]:
        """Create an empty source-document change summary payload."""
        return {
            "added": 0,
            "updated": 0,
            "deleted": 0,
            "unchanged": 0,
            "files": [],
            "scope_prefixes": [],
        }

    def _record_source_change(
        self,
        summary: Dict[str, Any],
        *,
        path: str,
        action: str,
        doc_type: Optional[str] = None,
        title: Optional[str] = None,
    ) -> None:
        """Accumulate source-document change reporting."""
        action_map = {
            "add": "added",
            "added": "added",
            "update": "updated",
            "updated": "updated",
            "delete": "deleted",
            "deleted": "deleted",
            "unchanged": "unchanged",
        }
        action_key = action_map.get(action)
        if not action_key:
            return
        summary[action_key] += 1
        summary["files"].append(
            {
                "path": path,
                "action": {
                    "added": "add",
                    "updated": "update",
                    "deleted": "delete",
                    "unchanged": "unchanged",
                }[action_key],
                "doc_type": doc_type or "",
                "title": title or "",
            }
        )

    async def _delete_stale_source_documents(
        self,
        deduplicators: Dict[str, DocumentDeduplicator],
        tracked_by_path: Dict[str, List[Dict[str, Any]]],
        current_paths: set[str],
        scope_prefixes: set[str],
    ) -> List[Dict[str, Any]]:
        """Delete source documents that were removed from the current ingest scope."""
        deletions: List[Dict[str, Any]] = []
        for source_document_path, tracked_entries in tracked_by_path.items():
            if not self._path_in_scope(source_document_path, scope_prefixes):
                continue
            if source_document_path in current_paths:
                continue
            for tracked_entry in tracked_entries:
                deduplicator = deduplicators[tracked_entry["deduplicator_key"]]
                await deduplicator.delete_tracked_source_document(
                    str(tracked_entry.get("document_hash") or ""),
                    source_document_path,
                )
                deletions.append(
                    {
                        "path": source_document_path,
                        "action": "delete",
                        "title": str(tracked_entry.get("title") or ""),
                        "doc_type": str(tracked_entry.get("doc_type") or ""),
                    }
                )
        return deletions

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
            "source_document_changes": self._empty_source_change_summary(),
            "errors": [],
            "success": False,
        }

        try:
            deduplicators = await self._build_deduplicators()
            vectorizer = get_vectorizer()
            tracked_source_documents = await self._list_tracked_source_documents(deduplicators)
            current_source_paths: set[str] = set()
            source_scope_prefixes: set[str] = set()

            # Process each category
            for category in ["oss", "enterprise", "shared"]:
                category_path = batch_path / category
                if not category_path.exists():
                    continue

                category_stats = await self._process_category(
                    category_path,
                    category,
                    vectorizer,
                    deduplicators,
                    tracked_source_documents=tracked_source_documents,
                )

                ingestion_stats["categories_processed"][category] = category_stats
                ingestion_stats["documents_processed"] += category_stats["documents_processed"]
                ingestion_stats["chunks_created"] += category_stats["chunks_created"]
                ingestion_stats["chunks_indexed"] += category_stats["chunks_indexed"]
                ingestion_stats["errors"].extend(category_stats["errors"])
                current_source_paths.update(category_stats.get("source_document_paths", []))
                source_scope_prefixes.update(category_stats.get("source_document_scopes", []))

                for change in category_stats.get("source_document_changes", []):
                    self._record_source_change(
                        ingestion_stats["source_document_changes"],
                        path=change["path"],
                        action=change["action"],
                        doc_type=change.get("doc_type"),
                        title=change.get("title"),
                    )

            stale_source_documents = await self._delete_stale_source_documents(
                deduplicators,
                tracked_source_documents,
                current_source_paths,
                source_scope_prefixes,
            )
            for deletion in stale_source_documents:
                self._record_source_change(
                    ingestion_stats["source_document_changes"],
                    path=deletion["path"],
                    action="deleted",
                    doc_type=deletion.get("doc_type"),
                    title=deletion.get("title"),
                )

            ingestion_stats["source_document_changes"]["scope_prefixes"] = sorted(
                source_scope_prefixes
            )

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
        vectorizer: Any,
        deduplicators: Dict[str, DocumentDeduplicator],
        tracked_source_documents: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """Process all documents in a category folder."""
        logger.info(f"Processing category: {category}")

        stats = {
            "category": category,
            "documents_processed": 0,
            "chunks_created": 0,
            "chunks_indexed": 0,
            "source_document_changes": [],
            "source_document_paths": [],
            "source_document_scopes": [],
            "errors": [],
        }

        # Find all JSON files in category
        json_files = list(category_path.glob("*.json"))

        # Optionally filter to latest-only
        if self.config.get("latest_only"):

            def include_file(path: Path) -> bool:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    src = data.get("source_url") or ""
                    meta = data.get("metadata", {})
                    rel = str(meta.get("relative_path", ""))
                    blob = f"{src} {rel}"
                    import re

                    # Skip versioned paths like /7.8/
                    if re.search(r"/\d+\.\d+/", blob):
                        return False
                    # Prefer latest subtree for Enterprise docs
                    if "operate/rs" in blob and "/latest/" not in blob:
                        return False
                    return True
                except Exception:
                    # If in doubt, keep the file
                    return True

            before = len(json_files)
            json_files = [p for p in json_files if include_file(p)]
            logger.info(
                f"Filtered latest-only: {before} -> {len(json_files)} documents in {category}"
            )

        logger.info(f"Found {len(json_files)} documents in {category}")

        # Process documents in parallel batches
        async def process_document(json_file: Path) -> Dict[str, Any]:
            """Process a single document and return stats."""
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    doc_data = json.load(f)

                document = ScrapedDocument.from_dict(doc_data)
                chunks = self.processor.chunk_document(document)
                indexed = await index_processed_document(
                    document=document,
                    chunks=chunks,
                    vectorizer=vectorizer,
                    deduplicators=deduplicators,
                    tracked_source_documents=tracked_source_documents,
                )
                logger.debug(f"Processed document: {document.title} ({len(chunks)} chunks)")
                return {"success": True, **indexed}

            except Exception as e:
                error_msg = f"Failed to process {json_file.name}: {str(e)}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                }

        # Process documents in parallel batches (e.g., 10 at a time)
        batch_size = 10
        for i in range(0, len(json_files), batch_size):
            batch = json_files[i : i + batch_size]
            logger.info(
                f"Processing batch {i // batch_size + 1}/{(len(json_files) + batch_size - 1) // batch_size} ({len(batch)} documents)"
            )

            # Process batch in parallel
            results = await asyncio.gather(*[process_document(f) for f in batch])

            # Aggregate stats
            for result in results:
                if result["success"]:
                    stats["documents_processed"] += 1
                    stats["chunks_created"] += result["chunks_created"]
                    stats["chunks_indexed"] += result["chunks_indexed"]
                    if result.get("source_document_change"):
                        stats["source_document_changes"].append(result["source_document_change"])
                    if result.get("source_document_path"):
                        stats["source_document_paths"].append(result["source_document_path"])
                        stats["source_document_scopes"].append(
                            result.get("source_document_scope", "")
                        )
                else:
                    stats["errors"].append(result["error"])

        return stats

    async def _save_ingestion_manifest(self, batch_date: str, stats: Dict[str, Any]) -> None:
        """Save ingestion manifest with processing results."""
        manifest_path = self.storage.base_path / batch_date / "ingestion_manifest.json"

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, default=str)

        logger.info(f"Saved ingestion manifest: {manifest_path}")

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
            embeddings = await vectorizer.aembed_many(texts)

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

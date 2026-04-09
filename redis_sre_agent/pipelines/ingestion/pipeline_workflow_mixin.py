"""Shared ingestion workflow methods for the pipeline."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from .processor_indexing_helpers import index_processed_document
from .processor_source_helpers import create_scraped_document_from_markdown, find_markdown_files

logger = logging.getLogger(__name__)


class PipelineWorkflowMixin:
    """Higher-level batch and source-document workflows for ingestion."""

    @staticmethod
    def _load_source_markdown_files(source_dir: Path, *, action: str) -> List[Path]:
        """Validate a source directory and return its markdown files."""
        if not source_dir.exists():
            raise ValueError(f"Source directory does not exist: {source_dir}")

        markdown_files = find_markdown_files(source_dir)
        if not markdown_files:
            logger.warning("No markdown files found in %s", source_dir)
            return []

        logger.info("Found %s markdown files to %s", len(markdown_files), action)
        return markdown_files

    async def list_ingested_batches(self) -> List[Dict[str, Any]]:
        """List all batches that have been ingested."""
        batches = []

        for batch_date in self.storage.list_available_batches():
            batch_info = {"batch_date": batch_date}
            ingestion_manifest = self.storage.base_path / batch_date / "ingestion_manifest.json"
            if ingestion_manifest.exists():
                with open(ingestion_manifest, "r", encoding="utf-8") as f:
                    batch_info.update(json.load(f))
            else:
                batch_info["ingested"] = False
            batches.append(batch_info)

        return sorted(batches, key=lambda item: item["batch_date"], reverse=True)

    async def reindex_batch(self, batch_date: str) -> Dict[str, Any]:
        """Re-ingest a batch using the normal batch path."""
        logger.info("Re-indexing batch: %s", batch_date)
        return await self.ingest_batch(batch_date)

    async def ingest_source_documents(self, source_dir: Path) -> List[Dict[str, Any]]:
        """Ingest markdown files directly from a source_documents tree."""
        logger.info("Ingesting source documents from: %s", source_dir)
        markdown_files = self._load_source_markdown_files(source_dir, action="process")
        if not markdown_files:
            logger.warning("No markdown files found in %s", source_dir)
            return []

        deduplicators = await self._build_deduplicators()
        from ._processor_impl import get_vectorizer

        vectorizer = get_vectorizer()
        tracked_source_documents = await self._list_tracked_source_documents(deduplicators)

        results = []
        current_source_paths: set[str] = set()
        scope_prefixes: set[str] = set()

        for md_file in markdown_files:
            logger.info("Processing: %s", md_file.name)
            try:
                document = create_scraped_document_from_markdown(md_file, source_dir)
                chunks = self.processor.chunk_document(document)
                indexed = await index_processed_document(
                    document=document,
                    chunks=chunks,
                    vectorizer=vectorizer,
                    deduplicators=deduplicators,
                    tracked_source_documents=tracked_source_documents,
                )
                source_document_path = str(indexed.get("source_document_path") or "")
                source_document_scope = str(indexed.get("source_document_scope") or "")
                if source_document_path:
                    current_source_paths.add(source_document_path)
                scope_prefixes.add(source_document_scope)

                results.append(
                    {
                        "file": source_document_path or md_file.name,
                        "title": document.title,
                        "category": document.category,
                        "severity": document.severity,
                        "status": "success",
                        "action": indexed["source_document_change"]["action"],
                        "chunks_created": indexed["chunks_created"],
                        "chunks_indexed": indexed["chunks_indexed"],
                    }
                )
                logger.info(
                    "Processed %s: %s chunks, %s indexed",
                    md_file.name,
                    len(chunks),
                    results[-1]["chunks_indexed"],
                )
            except Exception as e:
                logger.error("Failed to process %s: %s", md_file.name, e)
                results.append({"file": md_file.name, "status": "error", "error": str(e)})

        stale_source_documents = await self._delete_stale_source_documents(
            deduplicators,
            tracked_source_documents,
            current_source_paths,
            scope_prefixes,
        )
        for deletion in stale_source_documents:
            results.append(
                {
                    "file": deletion["path"],
                    "title": deletion.get("title", ""),
                    "status": "success",
                    "action": "delete",
                    "chunks_created": 0,
                    "chunks_indexed": 0,
                }
            )

        return results

    async def prepare_source_artifacts(self, source_dir: Path, batch_date: str) -> int:
        """Convert source markdown files into stored batch artifacts."""
        logger.info("Preparing source artifacts from: %s for batch: %s", source_dir, batch_date)
        markdown_files = self._load_source_markdown_files(source_dir, action="prepare")
        if not markdown_files:
            return 0

        prepared_count = 0
        prepared_documents = []

        for md_file in markdown_files:
            logger.info("Preparing artifact for: %s", md_file.name)
            try:
                document = create_scraped_document_from_markdown(md_file, source_dir)
                self.storage.save_document(document)
                prepared_documents.append(document)
                prepared_count += 1
                logger.info("Prepared artifact for %s", md_file.name)
            except Exception as e:
                logger.error("Failed to prepare artifact for %s: %s", md_file.name, e)

        if prepared_documents:
            self.storage.save_batch_manifest(prepared_documents)
            logger.info("Created batch manifest for %s documents", len(prepared_documents))

        logger.info("Prepared %s source documents as batch artifacts", prepared_count)
        return prepared_count

    async def ingest_prepared_batch(self, batch_date: str) -> List[Dict[str, Any]]:
        """Ingest a previously prepared batch and normalize the CLI response."""
        logger.info("Ingesting prepared batch: %s", batch_date)
        batch_result = await self.ingest_batch(batch_date)
        if batch_result.get("success", False):
            return [{"status": "success", "batch_date": batch_date, **batch_result}]
        return [{"status": "error", "batch_date": batch_date, "error": "Batch ingestion failed"}]

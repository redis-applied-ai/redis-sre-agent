"""Shared ingestion workflow methods for the pipeline."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from redis_sre_agent.core.config import settings as app_settings
from redis_sre_agent.skills.discovery import (
    discover_skill_packages,
    find_skill_package_root,
    skill_package_to_documents,
)

from .processor_indexing_helpers import index_processed_document
from .processor_source_helpers import (
    create_scraped_document_from_markdown,
    find_markdown_files,
)

logger = logging.getLogger(__name__)


class PipelineWorkflowMixin:
    """Higher-level batch and source-document workflows for ingestion."""

    @staticmethod
    def _load_source_markdown_files(source_dir: Path, *, action: str) -> List[Path]:
        """Validate a source directory and return non-package markdown files."""
        if not source_dir.exists():
            raise ValueError(f"Source directory does not exist: {source_dir}")

        markdown_files = [
            path
            for path in find_markdown_files(source_dir)
            if not _is_agent_skills_package_path(path, boundary=source_dir)
        ]
        if not markdown_files:
            logger.warning("No markdown files found in %s", source_dir)
            return []

        logger.info("Found %s markdown files to %s", len(markdown_files), action)
        return markdown_files

    def _configured_skill_roots(self, source_dir: Path) -> List[Path]:
        """Resolve all roots that should be scanned for Agent Skills packages."""
        roots: list[Path] = []
        configured_roots: list[str] = []
        pipeline_settings = getattr(self, "settings", None)
        configured_roots.extend(getattr(pipeline_settings, "skill_roots", None) or [])
        configured_roots.extend(getattr(app_settings, "skill_roots", None) or [])
        configured_roots.extend(getattr(self.knowledge_settings, "skill_roots", None) or [])
        for configured_root in configured_roots:
            candidate = Path(configured_root).resolve()
            if candidate.exists():
                roots.append(candidate)
        nested_skills_root = source_dir / "skills"
        if nested_skills_root.is_dir():
            roots.append(nested_skills_root.resolve())
        elif source_dir.name == "skills":
            roots.append(source_dir.resolve())

        unique_roots: list[Path] = []
        seen: set[Path] = set()
        for root in roots:
            if root in seen:
                continue
            seen.add(root)
            unique_roots.append(root)
        return unique_roots

    def _load_source_documents(self, source_dir: Path, *, action: str) -> List[Any]:
        """Load markdown source documents plus Agent Skills package resources."""
        documents: list[Any] = []
        markdown_files = self._load_source_markdown_files(source_dir, action=action)
        for md_file in markdown_files:
            try:
                documents.append(create_scraped_document_from_markdown(md_file, source_dir))
            except Exception as exc:
                logger.error("Failed to load source markdown %s: %s", md_file, exc)

        for skill_root in self._configured_skill_roots(source_dir):
            try:
                packages = discover_skill_packages(skill_root)
            except Exception as exc:
                logger.error("Failed to discover Agent Skills packages in %s: %s", skill_root, exc)
                continue
            if packages:
                logger.info(
                    "Found %s Agent Skills packages to %s in %s", len(packages), action, skill_root
                )
            for package in packages:
                try:
                    documents.extend(
                        skill_package_to_documents(
                            package,
                            source_root=skill_root,
                            source_root_label=skill_root.name,
                        )
                    )
                except Exception as exc:
                    logger.error("Failed to expand Agent Skills package %s: %s", package.root, exc)

        if not documents:
            logger.warning("No source documents found in %s", source_dir)
            return []

        logger.info("Loaded %s source documents/resources to %s", len(documents), action)
        return documents

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
        documents = self._load_source_documents(source_dir, action="process")
        if not documents:
            logger.warning("No markdown files found in %s", source_dir)
            return []

        deduplicators = await self._build_deduplicators()
        from ._processor_impl import get_vectorizer

        vectorizer = get_vectorizer()
        tracked_source_documents = await self._list_tracked_source_documents(deduplicators)

        results = []
        current_source_paths: set[str] = set()
        scope_prefixes: set[str] = set()

        for document in documents:
            logger.info("Processing: %s", document.title)
            source_document_path = str(document.metadata.get("source_document_path") or "")
            source_document_scope = str(document.metadata.get("source_document_scope") or "")
            if source_document_path:
                current_source_paths.add(source_document_path)
                scope_prefixes.add(source_document_scope)
            try:
                chunks = self.processor.chunk_document(document)
                indexed = await index_processed_document(
                    document=document,
                    chunks=chunks,
                    vectorizer=vectorizer,
                    deduplicators=deduplicators,
                    tracked_source_documents=tracked_source_documents,
                )
                source_document_change = indexed.get("source_document_change") or {}

                results.append(
                    {
                        "file": source_document_path or document.title,
                        "title": document.title,
                        "category": document.category,
                        "severity": document.severity,
                        "status": "success",
                        "action": str(source_document_change.get("action") or ""),
                        "chunks_created": indexed["chunks_created"],
                        "chunks_indexed": indexed["chunks_indexed"],
                    }
                )
                logger.info(
                    "Processed %s: %s chunks, %s indexed",
                    document.title,
                    len(chunks),
                    results[-1]["chunks_indexed"],
                )
            except Exception as e:
                logger.error("Failed to process %s: %s", document.title, e)
                results.append(
                    {
                        "file": source_document_path or document.title,
                        "status": "error",
                        "error": str(e),
                    }
                )

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
                    "category": deletion.get("category", ""),
                    "severity": deletion.get("severity", ""),
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
        documents = self._load_source_documents(source_dir, action="prepare")
        if not documents:
            return 0

        prepared_count = 0
        prepared_documents = []

        for document in documents:
            logger.info("Preparing artifact for: %s", document.title)
            try:
                self.storage.save_document(document)
                prepared_documents.append(document)
                prepared_count += 1
                logger.info("Prepared artifact for %s", document.title)
            except Exception as e:
                logger.error("Failed to prepare artifact for %s: %s", document.title, e)

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


def _is_agent_skills_package_path(path: Path, *, boundary: Path | None = None) -> bool:
    """Return True when a file lives inside an Agent Skills package directory."""
    return find_skill_package_root(path, boundary=boundary) is not None

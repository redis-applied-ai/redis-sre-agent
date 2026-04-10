"""Document ingestion and processing for vector store."""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.keys import RedisKeys

# Avoid importing Redis/vectorizer at module import time to keep optional deps lazy
from ...pipelines.scraper.base import (
    ArtifactStorage,
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    SeverityLevel,
)
from .deduplication import DocumentDeduplicator

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
                # New defaults for better doc handling
                "strip_front_matter": True,
                "whole_doc_threshold": 6000,
                "whole_api_threshold": 12000,
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
                "strip_front_matter": True,
                "whole_doc_threshold": 6000,
                "whole_api_threshold": 12000,
                **(config or {}),
            }

    def chunk_document(self, document: ScrapedDocument) -> List[Dict[str, Any]]:
        """Split document into chunks for vector storage.

        Improvements:
        - Strip YAML front-matter by default
        - Keep short docs as a single chunk (threshold)
        - Fall back to existing length-based chunking otherwise
        """
        content = document.content or ""

        # Optional: strip YAML front matter at top of file
        if self.config.get("strip_front_matter", True) and content.startswith("---"):
            content, _ = self._strip_yaml_front_matter(content)

        # Guard: skip documents with no body after front-matter stripping
        if not content.strip():
            logger.warning(
                f"Skipping empty document body after front-matter strip: {document.title}"
            )
            return []

        # Keep small/medium CLI reference docs whole so usage blocks stay intact
        whole_threshold = int(self.config.get("whole_doc_threshold", 6000))
        src = (document.source_url or "").lower()
        title = (document.title or "").lower()
        is_cli_doc = (
            "rladmin" in content.lower()
            or "rladmin" in title
            or "cli-utilities" in src
            or "/rladmin/" in src
        )
        if is_cli_doc and len(content) <= whole_threshold:
            return [self._create_chunk(document, content, 0)]

        # Treat RS Admin REST API docs as whole documents (to preserve full examples)
        is_api_doc = (
            "/references/rest-api/" in src
            or "/rest-api/requests/" in src
            or "/operate/rs/references/rest-api/" in src
        )
        whole_api_threshold = int(self.config.get("whole_api_threshold", 12000))
        if is_api_doc and len(content) <= whole_api_threshold:
            return [self._create_chunk(document, content, 0)]

        # If not a CLI/API doc, still keep truly small docs as a single chunk
        if len(content) <= self.config["chunk_size"]:
            return [self._create_chunk(document, content, 0)]

        # Split into overlapping chunks (legacy behavior)
        chunks: List[Dict[str, Any]] = []
        chunk_size = int(self.config["chunk_size"])
        overlap = int(self.config["chunk_overlap"])
        max_chunks = int(self.config["max_chunks_per_doc"])

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

        # Extract version from metadata, default to "latest"
        version = document.metadata.get("version", "latest")
        doc_type = document.doc_type.value
        name = str(document.metadata.get("name") or document.title or "").strip()
        summary = document.metadata.get("summary")
        summary_str = str(summary).strip() if summary is not None else ""
        priority = str(document.metadata.get("priority") or "normal").strip().lower() or "normal"
        pinned = self._parse_bool(document.metadata.get("pinned"), default=False)

        return {
            "id": chunk_id,
            "document_hash": document.content_hash,
            "title": chunk_title,
            "content": content,
            "source": document.source_url,
            "category": document.category.value,
            "doc_type": doc_type,
            "name": name,
            "summary": summary_str,
            "priority": priority,
            "pinned": "true" if pinned else "false",
            "severity": document.severity.value,
            "version": version,
            "chunk_index": chunk_index,
            "source_document_path": str(document.metadata.get("source_document_path") or ""),
            "source_document_scope": str(document.metadata.get("source_document_scope") or ""),
            "metadata": {
                **document.metadata,
                "original_title": document.title,
                "chunk_size": len(content),
                "processed_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    @staticmethod
    def _parse_bool(value: Any, default: bool = False) -> bool:
        """Best-effort boolean parser for chunk metadata fields."""
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
        return default

    def _strip_yaml_front_matter(self, text: str) -> tuple[str, bool]:
        """Remove YAML front-matter delimited by leading --- blocks.

        Returns:
            (processed_text, removed) where removed indicates if front-matter was found.
        """
        if not text.startswith("---"):
            return text, False

        try:
            # Find closing '---' after the first line
            end_idx = text.find("\n---", 3)
            if end_idx == -1:
                return text, False
            # Include the trailing --- line
            closing_line_end = end_idx + len("\n---")
            remainder = text[closing_line_end:]
            # Trim a single leading newline if present
            if remainder.startswith("\n"):
                remainder = remainder[1:]
            return remainder, True
        except Exception:
            return text, False


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
            source_document_path = ""
            source_document_scope = None
            try:
                # Load document
                with open(json_file, "r", encoding="utf-8") as f:
                    doc_data = json.load(f)

                metadata = doc_data.get("metadata", {})
                if isinstance(metadata, dict):
                    source_document_path = str(metadata.get("source_document_path") or "").strip()
                    source_document_scope = str(metadata.get("source_document_scope") or "").strip()

                document = ScrapedDocument.from_dict(doc_data)

                # Process document into chunks
                chunks = self.processor.chunk_document(document)

                doc_type_key = str(document.doc_type.value).strip().lower() or "knowledge"
                deduplicator = deduplicators.get(doc_type_key) or deduplicators["knowledge"]
                source_document_path = str(
                    document.metadata.get("source_document_path") or source_document_path
                ).strip()
                source_document_scope = str(
                    document.metadata.get("source_document_scope") or source_document_scope or ""
                ).strip()
                tracked_entries = []
                if tracked_source_documents and source_document_path:
                    tracked_entries = tracked_source_documents.get(source_document_path, [])

                existed_before = bool(tracked_entries)
                for tracked_entry in tracked_entries:
                    tracked_deduplicator_key = tracked_entry["deduplicator_key"]
                    if tracked_deduplicator_key == doc_type_key:
                        continue
                    await deduplicators[tracked_deduplicator_key].delete_tracked_source_document(
                        str(tracked_entry.get("document_hash") or ""),
                        source_document_path,
                    )

                # Index chunks with deduplication
                if source_document_path:
                    replacement = await deduplicator.replace_source_document_chunks(
                        chunks, vectorizer
                    )
                    action = replacement.get("action", "unchanged")
                    if existed_before and action == "add":
                        action = "update"
                    indexed_count = int(replacement.get("indexed_count", 0))
                else:
                    indexed_count = await deduplicator.replace_document_chunks(chunks, vectorizer)
                    action = None

                logger.debug(f"Processed document: {document.title} ({len(chunks)} chunks)")

                return {
                    "success": True,
                    "chunks_created": len(chunks),
                    "chunks_indexed": indexed_count,
                    "source_document_change": (
                        {
                            "path": source_document_path,
                            "action": action,
                            "title": document.title,
                            "doc_type": doc_type_key,
                        }
                        if source_document_path
                        else None
                    ),
                    "source_document_path": source_document_path,
                    "source_document_scope": source_document_scope,
                }

            except Exception as e:
                error_msg = f"Failed to process {json_file.name}: {str(e)}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "source_document_path": source_document_path,
                    "source_document_scope": source_document_scope,
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
                if result.get("source_document_path"):
                    stats["source_document_paths"].append(result["source_document_path"])
                    stats["source_document_scopes"].append(
                        str(result.get("source_document_scope") or "")
                    )
                elif result.get("source_document_scope") is not None:
                    logger.debug(
                        "Ignoring source scope without source path for processed document result"
                    )

                if result["success"]:
                    stats["documents_processed"] += 1
                    stats["chunks_created"] += result["chunks_created"]
                    stats["chunks_indexed"] += result["chunks_indexed"]
                    if result.get("source_document_change"):
                        stats["source_document_changes"].append(result["source_document_change"])
                else:
                    stats["errors"].append(result["error"])

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
        metadata: Dict[str, str] = {}

        # Extract optional YAML front matter at top of file.
        front_matter_match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", content, re.DOTALL)
        if front_matter_match:
            front_matter = front_matter_match.group(1)
            for line in front_matter.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                normalized_key = self._normalize_metadata_key(key)
                metadata[normalized_key] = value.strip().strip('"').strip("'")

        # Extract title (first # heading) if front matter did not define one.
        title_match = re.search(r"^# (.+)", content, re.MULTILINE)
        if title_match and "title" not in metadata:
            metadata["title"] = title_match.group(1).strip()

        # Extract metadata lines (**Key**: value)
        metadata_pattern = r"^\*\*([^*]+)\*\*:\s*(.+)$"
        for match in re.finditer(metadata_pattern, content, re.MULTILINE):
            key = self._normalize_metadata_key(match.group(1))
            # Frontmatter is canonical. Do not let body metadata override it.
            if key in metadata:
                continue
            value = match.group(2).strip()
            metadata[key] = value

        return metadata

    def _normalize_metadata_key(self, key: str) -> str:
        """Normalize metadata keys into snake_case aliases."""
        normalized = re.sub(r"[\s-]+", "_", key.strip().lower())
        return re.sub(r"[^\w]", "", normalized)

    def _normalize_doc_type(self, doc_type_raw: str) -> tuple[DocumentType, str]:
        """Normalize canonical doc_type values."""
        normalized = re.sub(r"[\s-]+", "_", (doc_type_raw or "").strip().lower())
        if not normalized:
            normalized = "knowledge"

        try:
            return DocumentType(normalized), normalized
        except ValueError:
            logger.debug("Unknown document type '%s'; defaulting to knowledge", doc_type_raw)
            return DocumentType.KNOWLEDGE, "knowledge"

    def _normalize_priority(self, priority_raw: Any) -> str:
        """Normalize priority values to the ADR enum."""
        normalized = str(priority_raw or "").strip().lower()
        if normalized in {"low", "normal", "high", "critical"}:
            return normalized
        return "normal"

    @staticmethod
    def _find_source_documents_root(source_dir: Path) -> Path:
        """Resolve the canonical source_documents root when ingesting a subtree."""
        resolved_source_dir = source_dir.resolve()
        for candidate in (resolved_source_dir, *resolved_source_dir.parents):
            if candidate.name == "source_documents":
                return candidate
        return resolved_source_dir

    def _resolve_source_document_identity(self, md_file: Path, source_dir: Path) -> tuple[str, str]:
        """Return the stable source path and scope prefix for a source document."""
        resolved_file = md_file.resolve()
        resolved_source_dir = source_dir.resolve()
        source_root = self._find_source_documents_root(source_dir)

        try:
            source_document_path = resolved_file.relative_to(source_root).as_posix()
        except ValueError:
            source_document_path = resolved_file.relative_to(resolved_source_dir).as_posix()

        try:
            scope_prefix = resolved_source_dir.relative_to(source_root).as_posix()
        except ValueError:
            scope_prefix = ""

        if scope_prefix in {".", ""}:
            return source_document_path, ""
        return source_document_path, f"{scope_prefix.rstrip('/')}/"

    def _create_scraped_document_from_markdown(
        self, md_file: Path, source_dir: Optional[Path] = None
    ) -> ScrapedDocument:
        """Convert a markdown file to a ScrapedDocument for processing."""
        content = md_file.read_text(encoding="utf-8")
        metadata = self._parse_markdown_metadata(content)
        source_document_path = ""
        source_document_scope = ""
        if source_dir is not None:
            source_document_path, source_document_scope = self._resolve_source_document_identity(
                md_file, source_dir
            )

        # Extract or generate title
        title = metadata.get("title", md_file.stem.replace("-", " ").title())

        # Determine category from explicit metadata or directory structure
        category = self._determine_document_category(md_file, metadata)

        priority = self._normalize_priority(metadata.get("priority"))
        # Support legacy `severity` while allowing ADR `priority`-based severity defaults.
        severity_str = str(metadata.get("severity") or priority).strip().lower()

        # Map severity strings to SeverityLevel enum
        severity_map = {
            "critical": SeverityLevel.CRITICAL,
            "high": SeverityLevel.HIGH,
            "warning": SeverityLevel.MEDIUM,
            "medium": SeverityLevel.MEDIUM,
            "normal": SeverityLevel.MEDIUM,
            "low": SeverityLevel.LOW,
            "info": SeverityLevel.LOW,
        }
        severity = severity_map.get(severity_str.lower(), SeverityLevel.MEDIUM)

        # Determine document type from canonical front-matter key.
        # ADR default is `knowledge`.
        doc_type_raw = str(metadata.get("doc_type", "knowledge"))
        doc_type, normalized_doc_type = self._normalize_doc_type(doc_type_raw)

        name = str(metadata.get("name") or md_file.stem).strip() or md_file.stem
        summary_raw = metadata.get("summary")
        summary = str(summary_raw).strip() if summary_raw is not None else ""
        pinned = DocumentProcessor._parse_bool(metadata.get("pinned"), default=False)
        reserved_metadata_keys = {
            "file_path",
            "file_size",
            "original_category",
            "original_severity",
            "original_doc_type",
            "determined_category",
            "doc_type",
            "name",
            "summary",
            "priority",
            "pinned",
            "source_document_path",
            "source_document_scope",
        }
        passthrough_metadata = {
            key: value for key, value in metadata.items() if key not in reserved_metadata_keys
        }

        return ScrapedDocument(
            title=title,
            source_url=f"file://{md_file.absolute()}",
            content=content,
            category=category,
            doc_type=doc_type,
            severity=severity,
            metadata={
                **passthrough_metadata,
                "file_path": str(md_file),
                "file_size": md_file.stat().st_size,
                "original_category": metadata.get("category", "shared").lower(),
                "original_severity": severity_str,
                "original_doc_type": doc_type_raw,
                "determined_category": category.value,
                "doc_type": normalized_doc_type,
                "name": name,
                "summary": summary or None,
                "priority": priority,
                "pinned": pinned,
                "source_document_path": source_document_path,
                "source_document_scope": source_document_scope,
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

        deduplicators = await self._build_deduplicators()
        vectorizer = get_vectorizer()
        tracked_source_documents = await self._list_tracked_source_documents(deduplicators)

        results = []
        current_source_paths: set[str] = set()
        scope_prefixes: set[str] = set()

        for md_file in markdown_files:
            logger.info(f"Processing: {md_file.name}")
            source_document_path, source_document_scope = self._resolve_source_document_identity(
                md_file, source_dir
            )
            if source_document_path:
                current_source_paths.add(source_document_path)
            scope_prefixes.add(source_document_scope)

            try:
                # Convert markdown to ScrapedDocument
                document = self._create_scraped_document_from_markdown(md_file, source_dir)

                # Process document into chunks
                chunks = self.processor.chunk_document(document)

                doc_type_key = str(document.doc_type.value).strip().lower() or "knowledge"
                deduplicator = deduplicators.get(doc_type_key) or deduplicators["knowledge"]
                source_document_path = str(
                    document.metadata.get("source_document_path") or ""
                ).strip()
                source_document_scope = str(
                    document.metadata.get("source_document_scope") or ""
                ).strip()
                tracked_entries = tracked_source_documents.get(source_document_path, [])
                existed_before = bool(tracked_entries)
                for tracked_entry in tracked_entries:
                    tracked_deduplicator_key = tracked_entry["deduplicator_key"]
                    if tracked_deduplicator_key == doc_type_key:
                        continue
                    await deduplicators[tracked_deduplicator_key].delete_tracked_source_document(
                        str(tracked_entry.get("document_hash") or ""),
                        source_document_path,
                    )

                # Index chunks with deduplication
                replacement = await deduplicator.replace_source_document_chunks(chunks, vectorizer)
                action = replacement.get("action", "unchanged")
                if existed_before and action == "add":
                    action = "update"

                result = {
                    "file": source_document_path or md_file.name,
                    "title": document.title,
                    "category": document.category,
                    "severity": document.severity,
                    "status": "success",
                    "action": action,
                    "chunks_created": len(chunks),
                    "chunks_indexed": int(replacement.get("indexed_count", 0)),
                }

                results.append(result)
                logger.info(
                    f"✅ Processed {md_file.name}: {len(chunks)} chunks, {result['chunks_indexed']} indexed"
                )

            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Failed to process {md_file.name}: {error_msg}")

                result = {"file": md_file.name, "status": "error", "error": error_msg}
                results.append(result)

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
                document = self._create_scraped_document_from_markdown(md_file, source_dir)

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

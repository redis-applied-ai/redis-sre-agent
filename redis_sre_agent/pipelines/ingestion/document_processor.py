"""Document chunking logic for ingestion."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...pipelines.scraper.base import ScrapedDocument
from .processor_source_helpers import parse_bool, strip_yaml_front_matter

logger = logging.getLogger(__name__)
_PASSTHROUGH_TOP_LEVEL_FIELDS = (
    "skill_protocol",
    "resource_kind",
    "resource_path",
    "mime_type",
    "encoding",
    "package_hash",
    "entrypoint",
    "has_references",
    "has_scripts",
    "has_assets",
    "resource_title",
    "resource_description",
    "skill_description",
    "ui_metadata",
    "skill_manifest",
)


class DocumentProcessor:
    """Processes scraped documents for vector store ingestion."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, knowledge_settings=None):
        if knowledge_settings:
            self.config = {
                "chunk_size": knowledge_settings.chunk_size,
                "chunk_overlap": knowledge_settings.chunk_overlap,
                "min_chunk_size": 100,
                "max_chunks_per_doc": knowledge_settings.max_documents_per_batch,
                "splitting_strategy": knowledge_settings.splitting_strategy,
                "enable_metadata_extraction": knowledge_settings.enable_metadata_extraction,
                "enable_semantic_chunking": knowledge_settings.enable_semantic_chunking,
                "similarity_threshold": knowledge_settings.similarity_threshold,
                "embedding_model": knowledge_settings.embedding_model,
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
        """Split document into chunks for vector storage."""
        content = document.content or ""

        if self.config.get("strip_front_matter", True) and content.startswith("---"):
            content, _ = self._strip_yaml_front_matter(content)

        if not content.strip():
            logger.warning(
                "Skipping empty document body after front-matter strip: %s", document.title
            )
            return []

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

        is_api_doc = (
            "/references/rest-api/" in src
            or "/rest-api/requests/" in src
            or "/operate/rs/references/rest-api/" in src
        )
        whole_api_threshold = int(self.config.get("whole_api_threshold", 12000))
        if is_api_doc and len(content) <= whole_api_threshold:
            return [self._create_chunk(document, content, 0)]

        if len(content) <= self.config["chunk_size"]:
            return [self._create_chunk(document, content, 0)]

        chunks: List[Dict[str, Any]] = []
        chunk_size = int(self.config["chunk_size"])
        overlap = int(self.config["chunk_overlap"])
        max_chunks = int(self.config["max_chunks_per_doc"])

        start = 0
        chunk_index = 0

        while start < len(content) and chunk_index < max_chunks:
            end = start + chunk_size

            if end < len(content):
                sentence_break = content.rfind(".", start, end)
                if sentence_break > start + chunk_size // 2:
                    end = sentence_break + 1
                else:
                    word_break = content.rfind(" ", start, end)
                    if word_break > start + chunk_size // 2:
                        end = word_break

            chunk_content = content[start:end].strip()
            if len(chunk_content) >= self.config["min_chunk_size"]:
                chunks.append(self._create_chunk(document, chunk_content, chunk_index))
                chunk_index += 1

            start = end - overlap
            if start >= end:
                break

        return chunks

    def _create_chunk(
        self, document: ScrapedDocument, content: str, chunk_index: int
    ) -> Dict[str, Any]:
        """Create a chunk object for vector storage."""
        chunk_title = (
            document.title if chunk_index == 0 else f"{document.title} (Part {chunk_index + 1})"
        )
        chunk_id = f"{document.content_hash}_{chunk_index}"
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
            **{
                field: document.metadata.get(field, "")
                for field in _PASSTHROUGH_TOP_LEVEL_FIELDS
                if document.metadata.get(field) not in (None, "")
            },
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
        return parse_bool(value, default=default)

    def _strip_yaml_front_matter(self, text: str) -> tuple[str, bool]:
        """Remove YAML front-matter delimited by leading --- blocks."""
        return strip_yaml_front_matter(text)

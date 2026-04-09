"""Helpers for routing processed documents into the correct indices."""

from typing import Any, Dict, List, Optional

from ...pipelines.scraper.base import ScrapedDocument
from .deduplication import DocumentDeduplicator


def get_source_tracking_fields(document: ScrapedDocument) -> tuple[str, str]:
    """Extract stable source path metadata from a scraped document."""
    source_document_path = str(document.metadata.get("source_document_path") or "").strip()
    source_document_scope = str(document.metadata.get("source_document_scope") or "").strip()
    return source_document_path, source_document_scope


def select_deduplicator(
    document: ScrapedDocument, deduplicators: Dict[str, DocumentDeduplicator]
) -> tuple[str, DocumentDeduplicator]:
    """Choose the correct deduplicator for a document type."""
    doc_type_key = str(document.doc_type.value).strip().lower() or "knowledge"
    return doc_type_key, deduplicators.get(doc_type_key) or deduplicators["knowledge"]


async def delete_cross_index_tracked_entries(
    *,
    deduplicators: Dict[str, DocumentDeduplicator],
    tracked_entries: List[Dict[str, Any]],
    doc_type_key: str,
    source_document_path: str,
) -> bool:
    """Delete stale tracked copies when a source document changes target index."""
    existed_before = bool(tracked_entries)
    for tracked_entry in tracked_entries:
        tracked_deduplicator_key = tracked_entry["deduplicator_key"]
        if tracked_deduplicator_key == doc_type_key:
            continue
        await deduplicators[tracked_deduplicator_key].delete_tracked_source_document(
            str(tracked_entry.get("document_hash") or ""),
            source_document_path,
        )
    return existed_before


async def index_processed_document(
    *,
    document: ScrapedDocument,
    chunks: List[Dict[str, Any]],
    vectorizer: Any,
    deduplicators: Dict[str, DocumentDeduplicator],
    tracked_source_documents: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Index one processed document and return normalized ingestion stats."""
    doc_type_key, deduplicator = select_deduplicator(document, deduplicators)
    source_document_path, source_document_scope = get_source_tracking_fields(document)
    tracked_entries = []
    if tracked_source_documents and source_document_path:
        tracked_entries = tracked_source_documents.get(source_document_path, [])

    if source_document_path:
        existed_before = await delete_cross_index_tracked_entries(
            deduplicators=deduplicators,
            tracked_entries=tracked_entries,
            doc_type_key=doc_type_key,
            source_document_path=source_document_path,
        )
        replacement = await deduplicator.replace_source_document_chunks(chunks, vectorizer)
        action = replacement.get("action", "unchanged")
        if existed_before and action == "add":
            action = "update"
        indexed_count = int(replacement.get("indexed_count", 0))
    else:
        existed_before = False
        indexed_count = await deduplicator.replace_document_chunks(chunks, vectorizer)
        action = None

    return {
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

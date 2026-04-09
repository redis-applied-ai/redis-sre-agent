"""Public ingestion processor exports."""

from ._processor_impl import (
    IngestionPipeline,
    get_knowledge_index,
    get_skills_index,
    get_support_tickets_index,
    get_vectorizer,
)
from .document_processor import DocumentProcessor

__all__ = [
    "DocumentProcessor",
    "IngestionPipeline",
    "get_knowledge_index",
    "get_skills_index",
    "get_support_tickets_index",
    "get_vectorizer",
]

"""Base classes for data scraping pipeline."""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class DocumentCategory(str, Enum):
    """Document categorization for Redis SRE knowledge."""

    OSS = "oss"
    ENTERPRISE = "enterprise"
    SHARED = "shared"


class DocumentType(str, Enum):
    """Document type classification."""

    RUNBOOK = "runbook"
    DOCUMENTATION = "documentation"
    BLOG_POST = "blog_post"
    TUTORIAL = "tutorial"
    TROUBLESHOOTING = "troubleshooting"
    REFERENCE = "reference"
    API_DOC = "api_doc"


class SeverityLevel(str, Enum):
    """Document severity/priority level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScrapedDocument:
    """Represents a scraped document with metadata."""

    def __init__(
        self,
        title: str,
        content: str,
        source_url: str,
        category: DocumentCategory,
        doc_type: DocumentType,
        severity: SeverityLevel = SeverityLevel.MEDIUM,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.title = title
        self.content = content
        self.source_url = source_url
        self.category = category
        self.doc_type = doc_type
        self.severity = severity
        self.metadata = metadata or {}
        self.scraped_at = datetime.now(timezone.utc)
        self.content_hash = self._generate_content_hash()

    def _generate_content_hash(self) -> str:
        """Generate a hash of the content for deduplication."""
        import hashlib

        content_str = f"{self.title}||{self.content}||{self.source_url}"
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Convert document to dictionary for serialization."""
        return {
            "title": self.title,
            "content": self.content,
            "source_url": self.source_url,
            "category": self.category.value,
            "doc_type": self.doc_type.value,
            "severity": self.severity.value,
            "metadata": self.metadata,
            "scraped_at": self.scraped_at.isoformat(),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScrapedDocument":
        """Create document from dictionary."""
        doc = cls(
            title=data["title"],
            content=data["content"],
            source_url=data["source_url"],
            category=DocumentCategory(data["category"]),
            doc_type=DocumentType(data["doc_type"]),
            severity=SeverityLevel(data["severity"]),
            metadata=data.get("metadata", {}),
        )

        # Restore scraped_at if available
        if "scraped_at" in data:
            doc.scraped_at = datetime.fromisoformat(data["scraped_at"].replace("Z", "+00:00"))

        return doc


class ArtifactStorage:
    """Manages artifact storage with dated folders."""

    def __init__(self, base_path: Union[str, Path]):
        self.base_path = Path(base_path)
        self.current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.current_batch_path = self.base_path / self.current_date

        # Create directories
        self.current_batch_path.mkdir(parents=True, exist_ok=True)

        # Create category subdirectories
        for category in DocumentCategory:
            (self.current_batch_path / category.value).mkdir(exist_ok=True)

    def save_document(self, document: ScrapedDocument) -> Path:
        """Save document to appropriate category folder."""
        category_path = self.current_batch_path / document.category.value

        # Create filename from title and hash
        safe_title = "".join(
            c for c in document.title if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        safe_title = safe_title.replace(" ", "_")[:50]  # Limit filename length

        filename = f"{safe_title}_{document.content_hash}.json"
        file_path = category_path / filename

        # Save document
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(document.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info(f"Saved document: {file_path}")
        return file_path

    def save_batch_manifest(self, documents: List[ScrapedDocument]) -> Path:
        """Save manifest file with batch summary."""
        manifest = {
            "batch_date": self.current_date,
            "total_documents": len(documents),
            "categories": {},
            "document_types": {},
            "sources": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Count by category and type
        for doc in documents:
            category = doc.category.value
            doc_type = doc.doc_type.value

            manifest["categories"][category] = manifest["categories"].get(category, 0) + 1
            manifest["document_types"][doc_type] = manifest["document_types"].get(doc_type, 0) + 1

            if doc.source_url not in manifest["sources"]:
                manifest["sources"].append(doc.source_url)

        manifest_path = self.current_batch_path / "batch_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Saved batch manifest: {manifest_path}")
        return manifest_path

    def list_available_batches(self) -> List[str]:
        """List all available batch dates."""
        if not self.base_path.exists():
            return []

        batches = []
        for item in self.base_path.iterdir():
            if item.is_dir() and item.name.match(r"^\d{4}-\d{2}-\d{2}$"):
                batches.append(item.name)

        return sorted(batches)

    def get_batch_manifest(self, batch_date: str) -> Optional[Dict[str, Any]]:
        """Get manifest for a specific batch."""
        manifest_path = self.base_path / batch_date / "batch_manifest.json"
        if not manifest_path.exists():
            return None

        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)


class BaseScraper(ABC):
    """Abstract base class for document scrapers."""

    def __init__(self, storage: ArtifactStorage, config: Optional[Dict[str, Any]] = None):
        self.storage = storage
        self.config = config or {}
        self.scraped_documents: List[ScrapedDocument] = []
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def scrape(self) -> List[ScrapedDocument]:
        """Scrape documents from the source. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Get the name of this scraper's source."""
        pass

    async def run_scraping_job(self) -> Dict[str, Any]:
        """Run the complete scraping job and save artifacts."""
        self.logger.info(f"Starting scraping job for {self.get_source_name()}")

        try:
            # Scrape documents
            documents = await self.scrape()

            # Save documents to storage
            saved_paths = []
            for doc in documents:
                path = self.storage.save_document(doc)
                saved_paths.append(str(path))

            # Update scraped documents list
            self.scraped_documents.extend(documents)

            # Create job summary
            summary = {
                "source": self.get_source_name(),
                "documents_scraped": len(documents),
                "documents_saved": len(saved_paths),
                "categories": {},
                "document_types": {},
                "batch_date": self.storage.current_date,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

            # Count by category and type
            for doc in documents:
                category = doc.category.value
                doc_type = doc.doc_type.value
                summary["categories"][category] = summary["categories"].get(category, 0) + 1
                summary["document_types"][doc_type] = summary["document_types"].get(doc_type, 0) + 1

            self.logger.info(f"Scraping job completed: {summary}")
            return summary

        except Exception as e:
            self.logger.error(f"Scraping job failed for {self.get_source_name()}: {e}")
            raise

    def _clean_content(self, content: str) -> str:
        """Clean and normalize content text."""
        if not content:
            return ""

        # Remove excessive whitespace
        content = "\n".join(line.strip() for line in content.split("\n"))
        content = "\n".join(line for line in content.split("\n") if line)  # Remove empty lines

        # Limit content length for vector storage
        max_length = self.config.get("max_content_length", 50000)
        if len(content) > max_length:
            content = content[:max_length] + "... [truncated]"

        return content

    def _extract_metadata(self, source_data: Any) -> Dict[str, Any]:
        """Extract metadata from source data. Override in subclasses."""
        return {
            "scraper": self.get_source_name(),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

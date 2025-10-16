"""Redis documentation scraper for local clone of redis/docs repo."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    ArtifactStorage,
    BaseScraper,
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    SeverityLevel,
)

logger = logging.getLogger(__name__)


class RedisDocsLocalScraper(BaseScraper):
    """Scraper for local clone of redis/docs repository.

    This scraper reads markdown files from a local clone of:
    https://github.com/redis/docs

    Much faster than web scraping and provides complete access to all docs.
    """

    def __init__(self, storage: ArtifactStorage, config: Optional[Dict[str, Any]] = None):
        super().__init__(storage, config)

        # Default configuration
        self.config = {
            # Path to local clone of redis/docs repo
            "docs_repo_path": "./redis-docs",
            # Subdirectories to scrape within content/
            "content_paths": [
                "commands",  # Redis commands reference
                "develop",  # Development guides
                "integrate",  # Integration guides
                "operate",  # Operations and SRE content
                "latest/operate/rs",  # Redis Enterprise Software
            ],
            # File patterns to include
            "include_patterns": ["*.md", "*.markdown"],
            # File patterns to exclude
            "exclude_patterns": ["README.md", "readme.md", "_index.md"],
            **self.config,
        }

    def get_source_name(self) -> str:
        return "redis_documentation_local"

    async def scrape(self) -> List[ScrapedDocument]:
        """Scrape Redis documentation from local repo clone."""
        documents = []

        docs_path = Path(self.config["docs_repo_path"])

        if not docs_path.exists():
            self.logger.error(
                f"Docs repo not found at {docs_path}. "
                f"Please clone https://github.com/redis/docs to {docs_path}"
            )
            return documents

        content_dir = docs_path / "content"
        if not content_dir.exists():
            self.logger.error(f"Content directory not found: {content_dir}")
            return documents

        self.logger.info(f"Scanning local docs repo at: {docs_path}")

        # Discover all markdown files
        markdown_files = self._discover_markdown_files(content_dir)
        total = len(markdown_files)

        self.logger.info(f"Found {total} markdown files to process")

        # Process each file
        for i, md_file in enumerate(markdown_files, 1):
            try:
                doc = self._process_markdown_file(md_file, content_dir)
                if doc:
                    documents.append(doc)

                    # Progress logging
                    if i % 50 == 0 or i == total:
                        pct = i * 100 // total
                        self.logger.info(
                            f"Progress: [{i}/{total}] ({pct}%) - Latest: {doc.title[:50]}"
                        )

            except Exception as e:
                self.logger.error(f"Failed to process {md_file}: {e}")
                continue

        self.logger.info(f"Successfully processed {len(documents)}/{total} files")
        return documents

    def _discover_markdown_files(self, content_dir: Path) -> List[Path]:
        """Discover all markdown files to process."""
        markdown_files = []

        for content_path in self.config["content_paths"]:
            search_dir = content_dir / content_path

            if not search_dir.exists():
                self.logger.warning(f"Path not found: {search_dir}")
                continue

            # Find all markdown files recursively
            for pattern in self.config["include_patterns"]:
                for md_file in search_dir.rglob(pattern):
                    # Skip excluded files
                    if any(md_file.name == exclude for exclude in self.config["exclude_patterns"]):
                        continue

                    # Skip if already added
                    if md_file not in markdown_files:
                        markdown_files.append(md_file)

        return sorted(markdown_files)

    def _process_markdown_file(self, md_file: Path, content_dir: Path) -> Optional[ScrapedDocument]:
        """Process a single markdown file into a ScrapedDocument."""

        # Read file content
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            self.logger.error(f"Failed to read {md_file}: {e}")
            return None

        # Parse frontmatter if present
        metadata = self._parse_frontmatter(content)

        # Determine title
        title = metadata.get("title") or self._extract_title_from_content(content)
        if not title:
            title = md_file.stem.replace("-", " ").replace("_", " ").title()

        # Determine category and doc type from path
        category, doc_type, severity = self._categorize_from_path(md_file, content_dir)

        # Create relative path for source URL
        rel_path = md_file.relative_to(content_dir)
        source_url = f"https://github.com/redis/docs/blob/main/content/{rel_path}"

        return ScrapedDocument(
            title=title,
            content=content,
            source_url=source_url,
            category=category,
            doc_type=doc_type,
            severity=severity,
            metadata={
                "file_path": str(md_file),
                "relative_path": str(rel_path),
                "file_size": md_file.stat().st_size,
                **metadata,
            },
        )

    def _parse_frontmatter(self, content: str) -> Dict[str, Any]:
        """Parse YAML frontmatter from markdown content."""
        metadata = {}

        if not content.startswith("---"):
            return metadata

        try:
            # Find the closing ---
            end_idx = content.find("---", 3)
            if end_idx == -1:
                return metadata

            frontmatter = content[3:end_idx].strip()

            # Simple key: value parsing (not full YAML)
            for line in frontmatter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip().strip('"').strip("'")

        except Exception as e:
            self.logger.debug(f"Failed to parse frontmatter: {e}")

        return metadata

    def _extract_title_from_content(self, content: str) -> Optional[str]:
        """Extract title from first H1 heading in content."""
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        return None

    def _categorize_from_path(
        self, md_file: Path, content_dir: Path
    ) -> tuple[DocumentCategory, DocumentType, SeverityLevel]:
        """Determine category, doc type, and severity from file path."""

        rel_path = str(md_file.relative_to(content_dir))

        # Determine category
        if "operate/rs" in rel_path or "enterprise" in rel_path.lower():
            category = DocumentCategory.ENTERPRISE
        elif "operate/oss" in rel_path or "oss" in rel_path.lower():
            category = DocumentCategory.OSS
        else:
            category = DocumentCategory.SHARED

        # Determine doc type
        if "commands" in rel_path:
            doc_type = DocumentType.REFERENCE
            severity = SeverityLevel.MEDIUM
        elif "operate" in rel_path or "troubleshoot" in rel_path.lower():
            doc_type = DocumentType.RUNBOOK
            severity = SeverityLevel.HIGH
        elif "cli-utilities" in rel_path or "rladmin" in rel_path.lower():
            doc_type = DocumentType.REFERENCE
            severity = SeverityLevel.CRITICAL  # CLI tools are critical for SRE
        elif "develop" in rel_path:
            doc_type = DocumentType.DOCUMENTATION
            severity = SeverityLevel.MEDIUM
        elif "integrate" in rel_path:
            doc_type = DocumentType.DOCUMENTATION
            severity = SeverityLevel.MEDIUM
        else:
            doc_type = DocumentType.DOCUMENTATION
            severity = SeverityLevel.LOW

        return category, doc_type, severity

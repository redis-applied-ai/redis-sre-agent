"""Tests for RedisDocsLocalScraper."""

from pathlib import Path

import pytest

from redis_sre_agent.pipelines.scraper.base import ArtifactStorage
from redis_sre_agent.pipelines.scraper.redis_docs_local import RedisDocsLocalScraper


def _write_markdown(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\nBody text.\n", encoding="utf-8")


def test_extract_version_from_rel_path(tmp_path):
    """Test version extraction from docs repo relative paths."""
    storage = ArtifactStorage(tmp_path / "artifacts")
    scraper = RedisDocsLocalScraper(storage)

    assert (
        scraper._extract_version_from_rel_path(Path("operate/rs/7.22/references/terminology.md"))
        == "7.22"
    )
    assert (
        scraper._extract_version_from_rel_path(Path("operate/rs/references/terminology.md"))
        == "latest"
    )


def test_source_document_path_is_relative_not_github_url(tmp_path):
    """Local mirror keys docs by their relative path, not the github-URL default."""
    docs_repo = tmp_path / "redis-docs"
    content_dir = docs_repo / "content"
    md = content_dir / "operate/rs/clustering.md"
    _write_markdown(md, "Clustering")

    storage = ArtifactStorage(tmp_path / "artifacts")
    scraper = RedisDocsLocalScraper(storage, config={"docs_repo_path": str(docs_repo)})

    doc = scraper._process_markdown_file(md, content_dir)

    assert doc.metadata["source_document_path"] == "operate/rs/clustering.md"
    # The github blob URL remains the human-facing source, but is NOT the identity.
    assert doc.source_url.startswith("https://github.com/redis/docs/blob/")
    assert "github.com" not in doc.metadata["source_document_path"]


@pytest.mark.asyncio
async def test_scrape_sets_version_metadata_from_path(tmp_path):
    """Test scraped docs include normalized version metadata."""
    docs_repo = tmp_path / "redis-docs"
    content_dir = docs_repo / "content"

    _write_markdown(
        content_dir / "operate/rs/7.22/references/terminology.md",
        "Versioned Terminology",
    )
    _write_markdown(
        content_dir / "operate/rs/references/terminology.md",
        "Latest Terminology",
    )

    storage = ArtifactStorage(tmp_path / "artifacts")
    scraper = RedisDocsLocalScraper(storage, config={"docs_repo_path": str(docs_repo)})

    docs = await scraper.scrape()
    by_title = {doc.title: doc for doc in docs}

    assert by_title["Versioned Terminology"].metadata["version"] == "7.22"
    assert by_title["Latest Terminology"].metadata["version"] == "latest"

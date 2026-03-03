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

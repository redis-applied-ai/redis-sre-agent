"""Tests for the Redis documentation scraper."""

from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.pipelines.scraper.base import (
    ArtifactStorage,
    DocumentCategory,
    DocumentType,
    SeverityLevel,
)
from redis_sre_agent.pipelines.scraper.redis_docs import RedisDocsScraper


class _FakeResponse:
    def __init__(self, url: str):
        self.url = url
        self.status = 200

    async def text(self) -> str:
        return "<html><body>redis docs</body></html>"


class _FakeRequestContext:
    def __init__(self, url: str, requested_urls: list[str]):
        self._response = _FakeResponse(url)
        self._requested_urls = requested_urls
        self._url = url

    async def __aenter__(self) -> _FakeResponse:
        self._requested_urls.append(self._url)
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeSession:
    def __init__(self):
        self.requested_urls: list[str] = []

    def get(self, url: str) -> _FakeRequestContext:
        return _FakeRequestContext(url, self.requested_urls)


@pytest.mark.asyncio
async def test_scrape_section_skips_revisited_urls(tmp_path):
    """Recursive traversal should fetch each normalized URL at most once."""
    scraper = RedisDocsScraper(ArtifactStorage(tmp_path), {"max_pages": 20})
    scraper.session = _FakeSession()

    graph = {
        "https://redis.io/docs": [
            "https://redis.io/docs/a/",
            "https://redis.io/docs/b/",
        ],
        "https://redis.io/docs/a": [
            "https://redis.io/docs/b/",
            "https://redis.io/docs/c/",
        ],
        "https://redis.io/docs/b": [
            "https://redis.io/docs/c/",
        ],
        "https://redis.io/docs/c": [],
    }

    async def fake_extract(_soup, url):
        return {
            "title": f"Doc for {url}",
            "content": "x" * 200,
            "metadata": {},
        }

    async def fake_links(_soup, base_url):
        return graph[base_url]

    with (
        patch.object(scraper, "_extract_page_content", side_effect=fake_extract),
        patch.object(scraper, "_find_documentation_links", side_effect=fake_links),
        patch("redis_sre_agent.pipelines.scraper.redis_docs.asyncio.sleep", new=AsyncMock()),
    ):
        docs = await scraper._scrape_section(
            "https://redis.io/docs/",
            DocumentCategory.OSS,
            DocumentType.DOCUMENTATION,
            SeverityLevel.MEDIUM,
            max_depth=4,
        )

    assert len(scraper.session.requested_urls) == 4
    assert scraper.session.requested_urls == [
        "https://redis.io/docs",
        "https://redis.io/docs/a",
        "https://redis.io/docs/b",
        "https://redis.io/docs/c",
    ]
    assert len(docs) == 4


@pytest.mark.asyncio
async def test_scrape_section_honors_max_pages_budget(tmp_path):
    """Traversal should stop once the configured page budget is exhausted."""
    scraper = RedisDocsScraper(ArtifactStorage(tmp_path), {"max_pages": 2})
    scraper.session = _FakeSession()

    async def fake_extract(_soup, url):
        return {
            "title": f"Doc for {url}",
            "content": "x" * 200,
            "metadata": {},
        }

    async def fake_links(_soup, _base_url):
        return [
            "https://redis.io/docs/a/",
            "https://redis.io/docs/b/",
        ]

    with (
        patch.object(scraper, "_extract_page_content", side_effect=fake_extract),
        patch.object(scraper, "_find_documentation_links", side_effect=fake_links),
        patch("redis_sre_agent.pipelines.scraper.redis_docs.asyncio.sleep", new=AsyncMock()),
    ):
        docs = await scraper._scrape_section(
            "https://redis.io/docs/",
            DocumentCategory.OSS,
            DocumentType.DOCUMENTATION,
            SeverityLevel.MEDIUM,
            max_depth=4,
        )

    assert len(scraper.session.requested_urls) == 2
    assert scraper.session.requested_urls == [
        "https://redis.io/docs",
        "https://redis.io/docs/a",
    ]
    assert len(docs) == 2

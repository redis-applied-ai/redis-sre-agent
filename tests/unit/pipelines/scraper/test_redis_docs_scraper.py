"""Unit tests for Redis documentation scraper."""

from unittest.mock import AsyncMock

import pytest

from redis_sre_agent.pipelines.scraper.base import (
    ArtifactStorage,
    DocumentCategory,
    DocumentType,
    SeverityLevel,
)
from redis_sre_agent.pipelines.scraper.redis_docs import RedisDocsScraper


class _MockAsyncContextManager:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class _MockResponse:
    def __init__(self, text: str, status: int = 200):
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text


class _MockSession:
    def __init__(self, html_by_url):
        self._html_by_url = html_by_url
        self.calls: list[str] = []

    def get(self, url: str):
        self.calls.append(url)
        response = _MockResponse(self._html_by_url.get(url, "<html></html>"))
        return _MockAsyncContextManager(response)


class TestRedisDocsScraper:
    @pytest.fixture
    def scraper(self, tmp_path):
        return RedisDocsScraper(
            ArtifactStorage(tmp_path),
            {
                "delay_between_requests": 0,
                "timeout": 5,
                "max_pages": 3,
            },
        )

    def test_normalize_documentation_url(self, scraper):
        assert (
            scraper._normalize_documentation_url(
                "https://redis.io/docs/latest/develop/clients/redis-rb/?x=1#install"
            )
            == "https://redis.io/docs/latest/develop/clients/redis-rb"
        )
        assert (
            scraper._normalize_documentation_url("https://redis.io/docs/latest/operate/")
            == "https://redis.io/docs/latest/operate"
        )

    @pytest.mark.asyncio
    async def test_scrape_section_avoids_cycles_and_duplicate_urls(self, scraper):
        html_by_url = {
            "https://redis.io/docs/root": "<html><body><main>root</main></body></html>",
            "https://redis.io/docs/a": "<html><body><main>a</main></body></html>",
            "https://redis.io/docs/b": "<html><body><main>b</main></body></html>",
        }
        scraper.session = _MockSession(html_by_url)
        scraper._extract_page_content = AsyncMock(
            side_effect=lambda _soup, url: {
                "title": url.rsplit("/", 1)[-1] or "root",
                "content": f"content for {url}" * 20,
                "metadata": {"url": url},
            }
        )
        scraper._find_documentation_links = AsyncMock(
            side_effect=lambda _soup, url: {
                "https://redis.io/docs/root": [
                    "https://redis.io/docs/a/",
                    "https://redis.io/docs/b?foo=1",
                ],
                "https://redis.io/docs/a": [
                    "https://redis.io/docs/root#overview",
                    "https://redis.io/docs/b/",
                ],
                "https://redis.io/docs/b": [
                    "https://redis.io/docs/root",
                    "https://redis.io/docs/a#fragment",
                ],
            }.get(url, [])
        )

        docs = await scraper._scrape_section(
            "https://redis.io/docs/root",
            DocumentCategory.OSS,
            DocumentType.DOCUMENTATION,
            SeverityLevel.MEDIUM,
            max_depth=4,
        )

        assert [doc.source_url for doc in docs] == [
            "https://redis.io/docs/root",
            "https://redis.io/docs/a",
            "https://redis.io/docs/b",
        ]
        assert scraper.session.calls == [
            "https://redis.io/docs/root",
            "https://redis.io/docs/a",
            "https://redis.io/docs/b",
        ]
        assert scraper._extract_page_content.await_count == 3

    @pytest.mark.asyncio
    async def test_scrape_section_honors_max_pages(self, scraper):
        html_by_url = {
            "https://redis.io/docs/root": "<html><body><main>root</main></body></html>",
            "https://redis.io/docs/a": "<html><body><main>a</main></body></html>",
            "https://redis.io/docs/b": "<html><body><main>b</main></body></html>",
            "https://redis.io/docs/c": "<html><body><main>c</main></body></html>",
        }
        scraper.session = _MockSession(html_by_url)
        scraper._extract_page_content = AsyncMock(
            side_effect=lambda _soup, url: {
                "title": url.rsplit("/", 1)[-1] or "root",
                "content": f"content for {url}" * 20,
                "metadata": {"url": url},
            }
        )
        scraper._find_documentation_links = AsyncMock(
            side_effect=lambda _soup, url: {
                "https://redis.io/docs/root": [
                    "https://redis.io/docs/a",
                    "https://redis.io/docs/b",
                    "https://redis.io/docs/c",
                ],
            }.get(url, [])
        )

        docs = await scraper._scrape_section(
            "https://redis.io/docs/root",
            DocumentCategory.OSS,
            DocumentType.DOCUMENTATION,
            SeverityLevel.MEDIUM,
            max_depth=3,
        )

        assert len(docs) == 3
        assert [doc.source_url for doc in docs] == [
            "https://redis.io/docs/root",
            "https://redis.io/docs/a",
            "https://redis.io/docs/b",
        ]
        assert "https://redis.io/docs/c" not in scraper.session.calls

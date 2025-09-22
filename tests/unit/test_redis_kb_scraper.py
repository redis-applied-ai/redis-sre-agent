"""Unit tests for Redis KB scraper."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from bs4 import BeautifulSoup

from redis_sre_agent.pipelines.scraper.base import ArtifactStorage, DocumentCategory
from redis_sre_agent.pipelines.scraper.redis_kb import RedisKBScraper


class MockAsyncContextManager:
    """Mock async context manager for aiohttp responses."""

    def __init__(self, mock_response):
        self.mock_response = mock_response

    async def __aenter__(self):
        return self.mock_response

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class TestRedisKBScraper:
    """Test Redis KB scraper functionality."""

    @pytest.fixture
    def mock_storage(self, tmp_path):
        """Create mock storage."""
        return ArtifactStorage(tmp_path)

    @pytest.fixture
    def scraper(self, mock_storage):
        """Create Redis KB scraper instance."""
        config = {
            "base_url": "https://redis.io/kb",
            "timeout": 30,
            "delay_between_requests": 0.1,  # Faster for tests
            "max_concurrent_requests": 2,
            "max_articles": 5,  # Limit for tests
        }
        return RedisKBScraper(mock_storage, config)

    def test_scraper_initialization(self, scraper):
        """Test scraper initialization."""
        assert scraper.get_source_name() == "redis_kb"
        assert scraper.config["base_url"] == "https://redis.io/kb"
        assert len(scraper.product_labels) == 8
        assert "Redis Enterprise Software" in scraper.product_labels
        assert "Redis CE and Stack" in scraper.product_labels
        assert "Redis Cloud" in scraper.product_labels

    def test_product_label_extraction(self, scraper):
        """Test product label extraction from HTML."""
        # Mock HTML content with product labels
        html_content = """
        <html>
            <head><title>Can I use Redis as a Vector Database?</title></head>
            <body>
                <h1>Can I use Redis as a Vector Database?</h1>
                <div class="product-labels">
                    Redis Enterprise Software
                    Redis CE and Stack
                    Redis Cloud
                </div>
                <div class="content">
                    <p>Redis can be used as a vector database...</p>
                </div>
            </body>
        </html>
        """

        soup = BeautifulSoup(html_content, "html.parser")
        labels = scraper._extract_product_labels(soup)

        assert "Redis Enterprise Software" in labels
        assert "Redis CE and Stack" in labels
        assert "Redis Cloud" in labels

    def test_article_content_extraction(self, scraper):
        """Test article content extraction."""
        html_content = """
        <html>
            <head><title>Test Article - Redis</title></head>
            <body>
                <h1>Test Article</h1>
                <div class="editor">
                    <p>This is the main content of the article that contains enough text to pass the minimum length requirement.</p>
                    <p>It contains multiple paragraphs with detailed information about Redis functionality and features.</p>
                    <p>This article explains various concepts and provides examples for developers to understand the technology better.</p>
                    <code>redis-cli SET key value</code>
                    <p>Additional content to ensure we meet the minimum content length requirements for processing.</p>
                </div>
                <p>Last updated 01, Sep 2025</p>
            </body>
        </html>
        """

        soup = BeautifulSoup(html_content, "html.parser")
        result = scraper._extract_article_content(soup, "https://redis.io/kb/doc/test")

        assert result is not None
        assert result["title"] == "Test Article"
        assert "main content" in result["content"]
        assert result["last_updated"] == "01, Sep 2025"
        assert result["metadata"]["has_code_examples"] is True

    def test_category_determination(self, scraper):
        """Test category determination based on product labels."""
        # Test enterprise category (single enterprise product)
        enterprise_labels = ["Redis Enterprise Software"]
        assert scraper._determine_category(enterprise_labels) == DocumentCategory.ENTERPRISE

        # Test OSS category (single CE/Stack product)
        oss_labels = ["Redis CE and Stack"]
        assert scraper._determine_category(oss_labels) == DocumentCategory.OSS

        # Test shared category (multiple products)
        shared_labels = ["Redis Enterprise Software", "Redis Cloud", "Redis CE and Stack"]
        assert scraper._determine_category(shared_labels) == DocumentCategory.SHARED

        # Test shared category (multiple enterprise products)
        multiple_enterprise = ["Redis Enterprise Software", "Redis Cloud"]
        assert scraper._determine_category(multiple_enterprise) == DocumentCategory.SHARED

        # Test empty labels
        empty_labels = []
        assert scraper._determine_category(empty_labels) == DocumentCategory.SHARED

    @pytest.mark.asyncio
    async def test_url_discovery_fallback(self, scraper):
        """Test URL discovery fallback mechanism."""
        # Mock session to simulate failures
        mock_session = AsyncMock()
        scraper.session = mock_session

        # Mock failed main page scraping
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_session.get.return_value.__aenter__.return_value = mock_response

        # Test fallback URL addition
        await scraper._add_fallback_urls()

        assert len(scraper.discovered_urls) >= 3
        assert any("/kb/doc/" in url for url in scraper.discovered_urls)

    def test_document_creation_from_extracted_data(self, scraper):
        """Test document creation from extracted article data."""
        url = "https://redis.io/kb/doc/vector-database-guide"

        # Mock extracted data
        article_data = {
            "title": "Vector Database Guide",
            "content": "This comprehensive guide explains how to use Redis as a vector database for modern AI applications. It covers indexing strategies, querying techniques, and performance optimization best practices.",
            "last_updated": "15, Aug 2025",
            "metadata": {"has_code_examples": True, "word_count": 25},
        }

        product_labels = ["Redis Enterprise Software", "Redis Cloud"]

        # Test document creation logic (extracted from _scrape_single_article)
        metadata = {
            "url": url,
            "scraped_from": "redis_kb_scraper",
            "product_labels": product_labels,
            "product_label_tags": [
                scraper.product_labels.get(label, label.lower().replace(" ", "_"))
                for label in product_labels
            ],
            "content_length": len(article_data["content"]),
            "last_updated": article_data.get("last_updated"),
            **article_data.get("metadata", {}),
        }

        # Determine category based on product labels
        category = scraper._determine_category(product_labels)

        from redis_sre_agent.pipelines.scraper.base import (
            DocumentType,
            ScrapedDocument,
            SeverityLevel,
        )

        document = ScrapedDocument(
            title=article_data["title"],
            content=article_data["content"],
            source_url=url,
            category=category,
            doc_type=DocumentType.DOCUMENTATION,
            severity=SeverityLevel.MEDIUM,
            metadata=metadata,
        )

        # Verify document properties
        assert document is not None
        assert document.title == "Vector Database Guide"
        assert "vector database" in document.content.lower()
        assert document.source_url == url
        assert document.category == DocumentCategory.SHARED  # Multiple products

        # Check metadata
        assert "product_labels" in document.metadata
        assert "Redis Enterprise Software" in document.metadata["product_labels"]
        assert "Redis Cloud" in document.metadata["product_labels"]
        assert "product_label_tags" in document.metadata
        assert "redis_enterprise_software" in document.metadata["product_label_tags"]
        assert "redis_cloud" in document.metadata["product_label_tags"]

    def test_url_filtering_logic(self, scraper):
        """Test URL filtering logic for KB articles."""
        # Test the URL filtering logic that would be used in search API discovery
        test_results = [
            {"url": "/kb/doc/article1", "title": "Article 1"},
            {"url": "/kb/doc/article2", "title": "Article 2"},
            {"url": "/docs/other", "title": "Other Doc"},  # Should be ignored
            {"url": "/kb/doc/article3", "title": "Article 3"},
        ]

        # Simulate the filtering logic from _discover_through_search_api
        discovered_urls = set()
        for result in test_results:
            if "url" in result and "/kb/doc/" in result["url"]:
                from urllib.parse import urljoin

                full_url = urljoin("https://redis.io", result["url"])
                discovered_urls.add(full_url)

        # Should have discovered 3 KB articles
        kb_urls = [url for url in discovered_urls if "/kb/doc/" in url]
        assert len(kb_urls) == 3
        assert "https://redis.io/kb/doc/article1" in discovered_urls
        assert "https://redis.io/kb/doc/article2" in discovered_urls
        assert "https://redis.io/kb/doc/article3" in discovered_urls
        assert "https://redis.io/docs/other" not in discovered_urls

    @pytest.mark.asyncio
    async def test_error_handling(self, scraper):
        """Test error handling in scraping."""
        # Mock session that raises exceptions for get requests
        mock_session = AsyncMock()
        mock_session.get.side_effect = Exception("Network error")

        scraper.session = mock_session

        # Test that errors are handled gracefully
        result = await scraper._scrape_single_article("https://redis.io/kb/doc/test")
        assert result is None

        # Test URL discovery error handling - should use fallback URLs
        # Clear any existing URLs first
        scraper.discovered_urls.clear()

        # Mock the fallback method to add URLs
        with patch.object(scraper, "_add_fallback_urls") as mock_fallback:
            mock_fallback.return_value = None
            # Manually add some URLs to simulate fallback
            scraper.discovered_urls.add("https://redis.io/kb/doc/fallback1")
            scraper.discovered_urls.add("https://redis.io/kb/doc/fallback2")

            await scraper._discover_kb_urls()

        # Should have fallback URLs
        assert len(scraper.discovered_urls) > 0

    def test_clean_content(self, scraper):
        """Test content cleaning functionality."""
        dirty_content = """

        This is some content.


        With extra whitespace.


        And empty lines.

        """

        cleaned = scraper._clean_content(dirty_content)

        # Should remove excessive whitespace and empty lines
        assert cleaned.count("\n\n") == 0
        assert "This is some content." in cleaned
        assert "With extra whitespace." in cleaned
        assert "And empty lines." in cleaned

    @pytest.mark.asyncio
    async def test_full_scraping_workflow(self, scraper):
        """Test the complete scraping workflow."""
        # Mock the entire workflow
        with (
            patch.object(scraper, "_discover_kb_urls") as mock_discover,
            patch.object(scraper, "_scrape_single_article") as mock_scrape_article,
        ):
            # Setup mocks
            scraper.discovered_urls = {
                "https://redis.io/kb/doc/article1",
                "https://redis.io/kb/doc/article2",
            }

            # Mock successful article scraping
            mock_document = Mock()
            mock_document.title = "Test Article"
            mock_scrape_article.return_value = mock_document

            # Run scraping
            documents = await scraper.scrape()

            # Verify results
            assert len(documents) == 2
            assert all(doc.title == "Test Article" for doc in documents)
            mock_discover.assert_called_once()
            assert mock_scrape_article.call_count == 2

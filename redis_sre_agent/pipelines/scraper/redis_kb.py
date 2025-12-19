"""Redis Knowledge Base scraper for crawling redis.io/kb articles with product labels."""

import asyncio
import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from .base import (
    ArtifactStorage,
    BaseScraper,
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    SeverityLevel,
)

logger = logging.getLogger(__name__)


class RedisKBScraper(BaseScraper):
    """Scraper for Redis Knowledge Base articles with product label extraction."""

    def __init__(self, storage: ArtifactStorage, config: Optional[Dict[str, Any]] = None):
        default_config = {
            "base_url": "https://redis.io/kb",
            "timeout": 30,
            "delay_between_requests": 1.0,
            "max_concurrent_requests": 5,
            "max_articles": 500,  # Scrape all available KB articles
        }

        if config:
            default_config.update(config)

        super().__init__(storage, default_config)
        self.session: Optional[aiohttp.ClientSession] = None
        # Map URL -> set of product categories it was discovered in
        self.url_to_categories: Dict[str, Set[str]] = defaultdict(set)

        # Product label mappings (display name -> tag name)
        self.product_labels = {
            "Redis Enterprise Software": "redis_enterprise_software",
            "Redis CE and Stack": "redis_ce_stack",
            "Redis Cloud": "redis_cloud",
            "Redis Enterprise": "redis_enterprise",
            "Redis Insight": "redis_insight",
            "Redis Enterprise for K8s": "redis_enterprise_k8s",
            "Redis Enterprise for Kubernetes": "redis_enterprise_k8s",
            "Redis Data Integration": "redis_data_integration",
            "Client Libraries": "client_libraries",
            "Redis Client Libraries": "client_libraries",
        }

    def get_source_name(self) -> str:
        """Get the name of this scraper's source."""
        return "redis_kb"

    async def scrape(self) -> List[ScrapedDocument]:
        """Scrape Redis KB articles with product labels."""
        documents = []

        timeout = aiohttp.ClientTimeout(total=self.config["timeout"])
        connector = aiohttp.TCPConnector(limit=self.config["max_concurrent_requests"])

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            self.session = session

            # Step 1: Discover all KB article URLs by crawling product category pages
            self.logger.info("Discovering Redis KB article URLs...")
            await self._discover_kb_urls()

            self.logger.info(f"Found {len(self.url_to_categories)} KB articles to scrape")

            # Step 2: Scrape articles with concurrency control
            # Product labels are extracted from each article page (authoritative source)
            semaphore = asyncio.Semaphore(self.config["max_concurrent_requests"])
            tasks = []

            urls_to_scrape = list(self.url_to_categories.keys())[: self.config["max_articles"]]
            for url in urls_to_scrape:
                task = self._scrape_article_with_semaphore(semaphore, url)
                tasks.append(task)

            # Execute all scraping tasks
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"Scraping task failed: {result}")
                elif result:
                    documents.append(result)

                # Rate limiting between batches
                await asyncio.sleep(0.1)

        self.logger.info(f"Successfully scraped {len(documents)} Redis KB articles")
        return documents

    async def _discover_kb_urls(self) -> None:
        """Discover all KB article URLs using comprehensive product-based strategy."""
        try:
            # Scrape all product category pages with pagination
            self.logger.info("Starting comprehensive category-based URL discovery...")
            await self._discover_by_product_categories()
            self.logger.info(
                f"After category-based discovery: {len(self.url_to_categories)} URLs found"
            )

        except Exception as e:
            self.logger.error(f"Failed to discover KB URLs: {e}")

    async def _discover_by_product_categories(self) -> None:
        """Discover all KB article URLs by scraping each product category with pagination."""
        # Product category mappings from the HTML you provided
        categories = {
            "Redis CE and Stack": "2o9qogwfm6",
            "Redis Cloud": "1x5z2h4q4d",
            "Redis Enterprise Software": "1cmzkcxg2e",
            "Redis Enterprise for Kubernetes": "2kkfitpubo",
            "Redis Data Integration": "2ogjveqk6t",
            "Redis Insight": "116wz2xd3k",
            "Redis Client Libraries": "1z79fmce74",
        }

        for category_name, category_id in categories.items():
            try:
                self.logger.info(f"Scraping category: {category_name} (ID: {category_id})")
                await self._scrape_category_pages(category_id, category_name)

                # Rate limiting between categories
                await asyncio.sleep(1.0)

            except Exception as e:
                self.logger.error(f"Failed to scrape category {category_name}: {e}")
                continue

    async def _scrape_category_pages(self, category_id: str, category_name: str) -> None:
        """Scrape all pages of a specific category, following pagination."""
        page = 1
        articles_found = 0

        while page <= 20:  # Safety limit to prevent infinite loops
            try:
                url = f"https://redis.io/kb/public?cat={category_id}&page={page}"
                self.logger.debug(f"Scraping {category_name} page {page}: {url}")

                async with self.session.get(url) as response:
                    if response.status != 200:
                        self.logger.warning(f"HTTP {response.status} for {url}")
                        break

                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")

                    # Find article links in the table
                    article_links = self._extract_article_links_from_page(soup)

                    if not article_links:
                        self.logger.debug(f"No articles found on page {page} for {category_name}")
                        break

                    # Add all found article URLs with their category
                    for link in article_links:
                        full_url = urljoin("https://redis.io", link)
                        self.url_to_categories[full_url].add(category_name)
                        articles_found += 1

                    self.logger.debug(f"Found {len(article_links)} articles on page {page}")

                    # Check if there's a next page
                    if not self._has_next_page(soup, page):
                        self.logger.debug(f"No more pages for {category_name}")
                        break

                    page += 1

                    # Rate limiting between pages
                    await asyncio.sleep(0.5)

            except Exception as e:
                self.logger.error(f"Failed to scrape page {page} of {category_name}: {e}")
                break

        self.logger.info(f"Found {articles_found} articles in {category_name} across {page} pages")

    def _extract_article_links_from_page(self, soup: BeautifulSoup) -> List[str]:
        """Extract article links from a category page."""
        article_links = []

        # Look for article links in the table structure
        # Based on the HTML structure, articles are in table rows with links
        for row in soup.find_all("tr"):
            # Find the first cell which should contain the article title link
            first_cell = row.find("td")
            if first_cell:
                link = first_cell.find("a")
                if link and link.get("href"):
                    href = link.get("href")
                    # Only include KB article links
                    if "/kb/doc/" in href:
                        article_links.append(href)

        return article_links

    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        """Check if there's a next page in the pagination."""
        # Look for pagination section
        # The pagination shows: "Previous 1 2 (current) 3 4 5 Next Next"

        # Look for "Next" links that aren't disabled
        next_links = soup.find_all("a", string=lambda text: text and "Next" in text)

        # If we find any "Next" links, there's likely a next page
        if next_links:
            return True

        # Alternative: look for page numbers higher than current page
        page_links = soup.find_all("a", string=lambda text: text and text.isdigit())
        for link in page_links:
            try:
                page_num = int(link.get_text().strip())
                if page_num > current_page:
                    return True
            except (ValueError, AttributeError):
                continue

        return False

    async def _scrape_article_with_semaphore(
        self, semaphore: asyncio.Semaphore, url: str
    ) -> Optional[ScrapedDocument]:
        """Scrape a single article with semaphore control."""
        async with semaphore:
            try:
                return await self._scrape_single_article(url)
            except Exception as e:
                self.logger.error(f"Failed to scrape article {url}: {e}")
                return None
            finally:
                # Rate limiting
                await asyncio.sleep(self.config["delay_between_requests"])

    async def _scrape_single_article(self, url: str) -> Optional[ScrapedDocument]:
        """Scrape a single KB article, extracting product labels from page content."""
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    self.logger.warning(f"HTTP {response.status} for {url}")
                    return None

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

                # Extract article content
                article_data = self._extract_article_content(soup, url)
                if not article_data:
                    return None

                # Extract product labels from the article page (authoritative source)
                product_labels = self._extract_product_labels(soup)

                # Create document with enhanced metadata
                metadata = {
                    "url": url,
                    "scraped_from": "redis_kb_scraper",
                    "product_labels": product_labels,
                    "product_label_tags": [
                        self.product_labels.get(label, label.lower().replace(" ", "_"))
                        for label in product_labels
                    ],
                    "content_length": len(article_data["content"]),
                    "last_updated": article_data.get("last_updated"),
                    **article_data.get("metadata", {}),
                }

                # Determine category based on product labels
                category = self._determine_category(product_labels)

                document = ScrapedDocument(
                    title=article_data["title"],
                    content=article_data["content"],
                    source_url=url,
                    category=category,
                    doc_type=DocumentType.DOCUMENTATION,
                    severity=SeverityLevel.MEDIUM,
                    metadata=metadata,
                )

                self.logger.debug(
                    f"Scraped KB article: {article_data['title']} with labels: {product_labels}"
                )
                return document

        except Exception as e:
            self.logger.error(f"Failed to scrape article {url}: {e}")
            return None

    def _extract_article_content(self, soup: BeautifulSoup, url: str) -> Optional[Dict[str, Any]]:
        """Extract the main content from a KB article page."""
        try:
            # Extract title
            title_elem = soup.find("h1") or soup.find("title")
            title = title_elem.get_text().strip() if title_elem else "Untitled"

            # Clean up title
            if " - Redis" in title:
                title = title.replace(" - Redis", "")

            # Extract main content - look for the article content area
            content_selectors = [
                ".editor",  # Main content area based on the HTML structure
                "main",
                "article",
                ".content",
                ".kb-content",
            ]

            content = ""
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    # Remove navigation and other non-content elements
                    for unwanted in content_elem.find_all(
                        ["nav", "header", "footer", "script", "style"]
                    ):
                        unwanted.decompose()

                    content = content_elem.get_text(separator="\n", strip=True)
                    break

            if not content or len(content) < 50:  # Reduced threshold for tests
                return None

            # Extract last updated date
            last_updated = None
            date_elem = soup.find(text=re.compile(r"Last updated"))
            if date_elem:
                date_match = re.search(r"Last updated (\d{2}, \w+ \d{4})", str(date_elem))
                if date_match:
                    last_updated = date_match.group(1)

            # Clean content
            content = self._clean_content(content)

            return {
                "title": title,
                "content": content,
                "last_updated": last_updated,
                "metadata": {
                    "has_code_examples": bool(soup.find("code") or soup.find("pre")),
                    "word_count": len(content.split()),
                },
            }

        except Exception as e:
            self.logger.error(f"Failed to extract content from {url}: {e}")
            return None

    def _extract_product_labels(self, soup: BeautifulSoup) -> List[str]:
        """Extract Redis product labels from the article page using data-product attributes."""
        labels = []

        try:
            # Primary method: Extract from data-product attributes
            # These are the authoritative product labels displayed on the article
            # HTML structure: <span data-product="Redis CE and Stack">Redis CE and Stack</span>
            product_elements = soup.select("[data-product]")
            for elem in product_elements:
                product = elem.get("data-product", "").strip()
                if product and product in self.product_labels:
                    labels.append(product)

            # Remove duplicates while preserving order
            seen = set()
            unique_labels = []
            for label in labels:
                if label not in seen:
                    seen.add(label)
                    unique_labels.append(label)

            return unique_labels

        except Exception as e:
            self.logger.error(f"Failed to extract product labels: {e}")
            return []

    def _determine_category(self, product_labels: List[str]) -> DocumentCategory:
        """Determine document category based on product labels.

        Maps KB product categories to our document categories:
        - OSS: "Redis CE and Stack" only
        - ENTERPRISE: Enterprise Software, K8s, or Cloud only (all managed/commercial products)
        - SHARED: Multiple products or other categories (Insight, RDI, Client Libraries)
        """
        if not product_labels:
            return DocumentCategory.SHARED

        # Normalize to a set for easier checking
        labels_set = set(product_labels)

        # OSS-only categories
        oss_only = {"Redis CE and Stack"}

        # Enterprise/Commercial categories (including Cloud as it's a managed offering)
        enterprise_categories = {
            "Redis Enterprise Software",
            "Redis Enterprise for Kubernetes",
            "Redis Cloud",
        }

        # If all labels are OSS-only
        if labels_set.issubset(oss_only):
            return DocumentCategory.OSS

        # If all labels are enterprise/commercial categories
        if labels_set.issubset(enterprise_categories):
            return DocumentCategory.ENTERPRISE

        # Everything else is shared (multiple products, or Insight/RDI/Client Libraries)
        return DocumentCategory.SHARED

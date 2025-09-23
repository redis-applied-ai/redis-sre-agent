"""Redis Knowledge Base scraper for crawling redis.io/kb articles with product labels."""

import asyncio
import logging
import re
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
            "max_articles": 50,  # Reasonable limit for comprehensive coverage
        }

        if config:
            default_config.update(config)

        super().__init__(storage, default_config)
        self.session: Optional[aiohttp.ClientSession] = None
        self.discovered_urls: Set[str] = set()

        # Product label mappings
        self.product_labels = {
            "Redis Enterprise Software": "redis_enterprise_software",
            "Redis CE and Stack": "redis_ce_stack",
            "Redis Cloud": "redis_cloud",
            "Redis Enterprise": "redis_enterprise",
            "Redis Insight": "redis_insight",
            "Redis Enterprise for K8s": "redis_enterprise_k8s",
            "Redis Data Integration": "redis_data_integration",
            "Client Libraries": "client_libraries",
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

            # Step 1: Discover all KB article URLs
            self.logger.info("Discovering Redis KB article URLs...")
            await self._discover_kb_urls()

            self.logger.info(f"Found {len(self.discovered_urls)} KB articles to scrape")

            # Step 2: Scrape articles with concurrency control
            semaphore = asyncio.Semaphore(self.config["max_concurrent_requests"])
            tasks = []

            for url in list(self.discovered_urls)[: self.config["max_articles"]]:
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
            # Method 1: Scrape all product category pages with pagination
            self.logger.info("Starting comprehensive category-based URL discovery...")
            await self._discover_by_product_categories()
            self.logger.info(
                f"After category-based discovery: {len(self.discovered_urls)} URLs found"
            )

        except Exception as e:
            self.logger.error(f"Failed to discover KB URLs: {e}")

        # Always add fallback URLs if we don't have enough
        if len(self.discovered_urls) < 10:
            self.logger.info("Adding fallback URLs...")
            await self._add_fallback_urls()

    async def _scrape_main_kb_page(self) -> None:
        """Scrape the main KB page for article links."""
        try:
            async with self.session.get(self.config["base_url"]) as response:
                if response.status != 200:
                    self.logger.warning(f"HTTP {response.status} for main KB page")
                    return

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

                # Look for article links in the page
                for link in soup.find_all("a", href=True):
                    href = link["href"]

                    # Check if it's a KB article URL
                    if "/kb/doc/" in href:
                        full_url = urljoin(self.config["base_url"], href)
                        self.discovered_urls.add(full_url)

        except Exception as e:
            self.logger.error(f"Failed to scrape main KB page: {e}")

    async def _add_fallback_urls(self) -> None:
        """Add some known KB article URLs as fallback."""
        fallback_urls = [
            # Vector database and AI
            "https://redis.io/kb/doc/28x16buszr/can-i-use-redis-as-a-vector-database",
            # Migration and setup
            "https://redis.io/kb/doc/1iqt9z27dz/how-to-migrate-redis-oss-to-redis-enterprise",
            "https://redis.io/kb/doc/1yfuezjxdv/migrating-from-elasticache-to-redis-cloud-via-s3-bucket",
            # Performance and troubleshooting
            "https://redis.io/kb/doc/1mebipyp1e/performance-tuning-best-practices",
            "https://redis.io/kb/doc/2no7qfbtpf/how-to-troubleshoot-latency-issues",
            # High availability and disaster recovery
            "https://redis.io/kb/doc/21rbquorvb/considerations-about-consistency-and-data-loss-in-a-crdb-regional-failure",
            "https://redis.io/kb/doc/12ffgrmwbe/how-long-does-it-take-to-a-recover-a-large-database-from-persistence-rdb-aof",
            # Redis Enterprise specific
            "https://redis.io/kb/doc/164wz116f6/what-happens-if-a-redis-enterprise-license-expires",
            "https://redis.io/kb/doc/19yzdivas3/applying-license-to-a-redis-enterprise-cluster-in-kubernetes-deployment",
            "https://redis.io/kb/doc/1165ynamyu/the-cluster-keyslot-command-does-not-work-in-redis-enterprise-why",
            "https://redis.io/kb/doc/2pzjdqk77u/how-do-i-migrate-redis-enterprise-shards-and-endpoints-to-other-nodes",
            "https://redis.io/kb/doc/2d6sxrbhhj/does-redis-enterprise-support-logical-databases-using-the-select-command",
            "https://redis.io/kb/doc/1g3kwd7hca/error-from-web-console-when-creating-a-redis-enterprise-database-memory-limit-is-larger-than-amount-of-memory",
            "https://redis.io/kb/doc/1mjomfbkom/how-do-i-configure-the-dns-in-redis-enterprise",
            "https://redis.io/kb/doc/1sneb4qq3t/how-can-i-take-a-redis-enterprise-node-offline-safely-for-patching-upgrade",
            # Redis Cloud specific
            "https://redis.io/kb/doc/1hcgha9u9q/how-many-connections-can-be-established-to-a-redis-cloud-database",
            "https://redis.io/kb/doc/1jdtj3ryok/how-to-create-redis-cloud-vpc-peering-in-aws",
        ]

        for url in fallback_urls:
            self.discovered_urls.add(url)

        self.logger.info(f"Added {len(fallback_urls)} fallback URLs")
        self.logger.debug(f"Fallback URLs: {list(self.discovered_urls)}")

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

                    # Add all found article URLs
                    for link in article_links:
                        full_url = urljoin("https://redis.io", link)
                        self.discovered_urls.add(full_url)
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

        self.logger.info(
            f"Found {articles_found} articles in {category_name} across {page - 1} pages"
        )

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
        """Scrape a single KB article and extract product labels."""
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

                # Extract product labels
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
        """Extract Redis product labels from the article page."""
        labels = []

        try:
            # Method 1: Look for product labels in the article header/metadata area
            # Based on the KB article structure, labels appear near the title
            header_area = soup.find("h1") or soup.find(".kb-header")
            if header_area:
                # Look for labels in the vicinity of the title
                parent = header_area.parent
                if parent:
                    header_text = parent.get_text()
                    for product_name in self.product_labels.keys():
                        if product_name in header_text:
                            labels.append(product_name)

            # Method 2: Look for specific patterns in the page content
            # KB articles often have product labels displayed prominently
            page_text = soup.get_text()

            # Look for exact matches of product names
            for product_name in self.product_labels.keys():
                # Use word boundaries to avoid partial matches
                import re

                pattern = r"\b" + re.escape(product_name) + r"\b"
                if re.search(pattern, page_text, re.IGNORECASE):
                    labels.append(product_name)

            # Method 3: Look for specific CSS classes or data attributes
            label_selectors = [
                ".product-label",
                ".badge",
                ".tag",
                ".kb-tag",
                ".product-tag",
                "[data-product]",
                ".kb-product-tag",
                ".product-badge",
            ]

            for selector in label_selectors:
                elements = soup.select(selector)
                for elem in elements:
                    text = elem.get_text().strip()
                    # Check if the text matches any known product
                    for product_name in self.product_labels.keys():
                        if product_name.lower() in text.lower():
                            labels.append(product_name)

            # Method 4: Look in meta tags or structured data
            meta_tags = soup.find_all("meta")
            for meta in meta_tags:
                content = meta.get("content", "")
                for product_name in self.product_labels.keys():
                    if product_name in content:
                        labels.append(product_name)

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
        """Determine document category based on product labels."""
        if not product_labels:
            return DocumentCategory.SHARED

        # If it's only CE/Stack, categorize as OSS
        if len(product_labels) == 1 and product_labels[0] == "Redis CE and Stack":
            return DocumentCategory.OSS

        # If it mentions Enterprise and nothing else, categorize as enterprise
        enterprise_keywords = [
            "Redis Enterprise Software",
            "Redis Enterprise",
            "Redis Enterprise for K8s",
        ]
        if len(product_labels) == 1 and any(
            label in enterprise_keywords for label in product_labels
        ):
            return DocumentCategory.ENTERPRISE

        # If it applies to multiple products, it's shared
        return DocumentCategory.SHARED

"""Redis documentation scraper for OSS and Enterprise docs."""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

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


class RedisDocsScraper(BaseScraper):
    """Scraper for Redis documentation sites."""

    def __init__(self, storage: ArtifactStorage, config: Optional[Dict[str, Any]] = None):
        super().__init__(storage, config)

        # Default configuration
        self.config = {
            "oss_base_url": "https://redis.io/docs/",
            "enterprise_base_url": "https://docs.redis.com/latest/",
            "max_pages": 100,
            "delay_between_requests": 1.0,
            "timeout": 30,
            **self.config,
        }

        self.session: Optional[aiohttp.ClientSession] = None

    def get_source_name(self) -> str:
        return "redis_documentation"

    async def scrape(self) -> List[ScrapedDocument]:
        """Scrape Redis OSS and Enterprise documentation."""
        documents = []

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config["timeout"])
        ) as session:
            self.session = session

            # Scrape OSS documentation
            self.logger.info("Scraping Redis OSS documentation")
            oss_docs = await self._scrape_oss_docs()
            documents.extend(oss_docs)

            # Scrape Enterprise documentation
            self.logger.info("Scraping Redis Enterprise documentation")
            enterprise_docs = await self._scrape_enterprise_docs()
            documents.extend(enterprise_docs)

        self.logger.info(f"Scraped {len(documents)} Redis documentation pages")
        return documents

    async def _scrape_oss_docs(self) -> List[ScrapedDocument]:
        """Scrape Redis OSS documentation."""
        base_url = self.config["oss_base_url"]
        documents = []

        # Key OSS documentation sections
        oss_sections = [
            ("get-started/", DocumentType.TUTORIAL, SeverityLevel.HIGH),
            ("connect/", DocumentType.DOCUMENTATION, SeverityLevel.HIGH),
            ("data-types/", DocumentType.REFERENCE, SeverityLevel.MEDIUM),
            ("commands/", DocumentType.REFERENCE, SeverityLevel.MEDIUM),
            ("management/", DocumentType.RUNBOOK, SeverityLevel.HIGH),
            ("operate/", DocumentType.RUNBOOK, SeverityLevel.CRITICAL),
            ("latest/operate/", DocumentType.RUNBOOK, SeverityLevel.CRITICAL),
        ]

        for section, doc_type, severity in oss_sections:
            section_url = urljoin(base_url, section)

            try:
                section_docs = await self._scrape_section(
                    section_url, DocumentCategory.OSS, doc_type, severity, max_depth=2
                )
                documents.extend(section_docs)

                # Rate limiting
                await asyncio.sleep(self.config["delay_between_requests"])

            except Exception as e:
                self.logger.error(f"Failed to scrape OSS section {section}: {e}")
                continue

        return documents

    async def _scrape_enterprise_docs(self) -> List[ScrapedDocument]:
        """Scrape Redis Enterprise documentation."""
        base_url = self.config["enterprise_base_url"]
        documents = []

        # Key Enterprise documentation sections
        enterprise_sections = [
            ("rs/", DocumentType.DOCUMENTATION, SeverityLevel.HIGH),
            ("rc/", DocumentType.DOCUMENTATION, SeverityLevel.HIGH),
            ("ri/", DocumentType.DOCUMENTATION, SeverityLevel.MEDIUM),
            ("kubernetes/", DocumentType.RUNBOOK, SeverityLevel.HIGH),
            ("modules/", DocumentType.REFERENCE, SeverityLevel.MEDIUM),
        ]

        for section, doc_type, severity in enterprise_sections:
            section_url = urljoin(base_url, section)

            try:
                section_docs = await self._scrape_section(
                    section_url, DocumentCategory.ENTERPRISE, doc_type, severity, max_depth=2
                )
                documents.extend(section_docs)

                # Rate limiting
                await asyncio.sleep(self.config["delay_between_requests"])

            except Exception as e:
                self.logger.error(f"Failed to scrape Enterprise section {section}: {e}")
                continue

        return documents

    async def _scrape_section(
        self,
        section_url: str,
        category: DocumentCategory,
        doc_type: DocumentType,
        severity: SeverityLevel,
        max_depth: int = 2,
        current_depth: int = 0,
    ) -> List[ScrapedDocument]:
        """Recursively scrape a documentation section."""
        if current_depth >= max_depth:
            return []

        documents = []

        try:
            # Get section page
            async with self.session.get(section_url) as response:
                if response.status != 200:
                    self.logger.warning(f"HTTP {response.status} for {section_url}")
                    return []

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

            # Extract main content
            main_content = await self._extract_page_content(soup, section_url)
            if main_content:
                doc = ScrapedDocument(
                    title=main_content["title"],
                    content=main_content["content"],
                    source_url=section_url,
                    category=category,
                    doc_type=doc_type,
                    severity=severity,
                    metadata=main_content["metadata"],
                )
                documents.append(doc)

            # Find links to sub-pages (if not at max depth)
            if current_depth < max_depth - 1:
                links = await self._find_documentation_links(soup, section_url)

                for link_url in links[:10]:  # Limit to prevent excessive scraping
                    try:
                        subdocs = await self._scrape_section(
                            link_url, category, doc_type, severity, max_depth, current_depth + 1
                        )
                        documents.extend(subdocs)

                        # Rate limiting for sub-pages
                        await asyncio.sleep(0.5)

                    except Exception as e:
                        self.logger.error(f"Failed to scrape sub-page {link_url}: {e}")
                        continue

        except Exception as e:
            self.logger.error(f"Failed to scrape section {section_url}: {e}")

        return documents

    async def _extract_page_content(
        self, soup: BeautifulSoup, url: str
    ) -> Optional[Dict[str, Any]]:
        """Extract title, content, and metadata from a documentation page."""
        try:
            # Extract title
            title = None
            title_selectors = ["h1", "title", ".page-title", "#title"]

            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text().strip()
                    break

            if not title:
                title = f"Redis Documentation - {urlparse(url).path}"

            # Extract main content
            content = ""
            content_selectors = [
                "main",
                ".content",
                ".main-content",
                ".documentation-content",
                "#content",
                "article",
                ".article-content",
            ]

            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    content = content_elem.get_text().strip()
                    break

            # Fallback to body if no content found
            if not content:
                body = soup.select_one("body")
                if body:
                    content = body.get_text().strip()

            # Clean content
            content = self._clean_content(content)

            if len(content) < 100:  # Skip very short pages
                return None

            # Extract metadata
            metadata = {
                "url": url,
                "scraped_from": "redis_docs_scraper",
                "content_length": len(content),
                "has_code_examples": bool(soup.find("code") or soup.find("pre")),
                "section": self._extract_section_from_url(url),
            }

            # Try to extract description/summary
            description_elem = soup.select_one('meta[name="description"]')
            if description_elem:
                metadata["description"] = description_elem.get("content", "")

            return {"title": title, "content": content, "metadata": metadata}

        except Exception as e:
            self.logger.error(f"Failed to extract content from {url}: {e}")
            return None

    async def _find_documentation_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Find links to other documentation pages on the same site."""
        links = []
        base_domain = urlparse(base_url).netloc

        # Find all links
        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Convert relative URLs to absolute
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            # Only include links from the same domain
            if parsed.netloc == base_domain:
                # Exclude non-documentation links
                if any(
                    exclude in full_url
                    for exclude in [
                        "#",
                        "javascript:",
                        "mailto:",
                        ".pdf",
                        ".zip",
                        "/download",
                        "/blog",
                        "/community",
                        "/search",
                    ]
                ):
                    continue

                if full_url not in links and full_url != base_url:
                    links.append(full_url)

        return links[:20]  # Limit number of links

    def _extract_section_from_url(self, url: str) -> str:
        """Extract section name from URL path."""
        path = urlparse(url).path
        parts = [p for p in path.split("/") if p and p != "docs"]
        return parts[0] if parts else "general"


class RedisRunbookScraper(BaseScraper):
    """Scraper for Redis SRE runbooks and operational documentation."""

    def __init__(self, storage: ArtifactStorage, config: Optional[Dict[str, Any]] = None):
        super().__init__(storage, config)

        # Runbook sources
        self.config = {
            "github_repos": [
                "redis/redis-doc",
                "redis/redis",  # Redis source repo may have operational docs
            ],
            "runbook_paths": [
                "docs/ops/",
                "docs/operations/",
                "docs/deployment/",
                "docs/troubleshooting/",
                "runbooks/",
                "operations/",
            ],
            **self.config,
        }

    def get_source_name(self) -> str:
        return "redis_runbooks"

    async def scrape(self) -> List[ScrapedDocument]:
        """Scrape Redis operational runbooks."""
        documents = []

        # For now, create sample runbooks
        # In a real implementation, this would scrape from GitHub, internal repos, etc.
        sample_runbooks = await self._create_sample_runbooks()
        documents.extend(sample_runbooks)

        return documents

    async def _create_sample_runbooks(self) -> List[ScrapedDocument]:
        """Create sample SRE runbooks for demonstration."""
        runbooks = []

        # Memory troubleshooting runbook
        memory_runbook = ScrapedDocument(
            title="Redis Memory Troubleshooting Runbook",
            content="""
# Redis Memory Troubleshooting

## Overview
This runbook covers common Redis memory issues and resolution procedures.

## Symptoms
- High memory usage (>80%)
- Out of memory errors
- Slow performance
- Key evictions

## Diagnostic Steps

### 1. Check Memory Usage
```
INFO memory
CONFIG GET maxmemory*
```

### 2. Analyze Memory Breakdown
```
MEMORY USAGE <key>
MEMORY STATS
```

### 3. Check Eviction Policy
```
CONFIG GET maxmemory-policy
```

## Resolution Procedures

### High Memory Usage
1. Identify large keys: `MEMORY USAGE <key>`
2. Check TTL settings: `TTL <key>`
3. Review data structures
4. Consider memory optimization

### Memory Leaks
1. Monitor memory growth over time
2. Check for keys without TTL
3. Review application code for memory patterns
4. Use MEMORY DOCTOR for recommendations

## Prevention
- Set appropriate maxmemory limits
- Use appropriate eviction policies
- Monitor memory usage trends
- Regular memory analysis

## Escalation
Contact Redis DBA team if:
- Memory usage >95% for >30 minutes
- Multiple Redis instances affected
- Business impact observed
            """.strip(),
            source_url="internal://runbooks/redis-memory-troubleshooting",
            category=DocumentCategory.SHARED,
            doc_type=DocumentType.RUNBOOK,
            severity=SeverityLevel.CRITICAL,
            metadata={
                "tags": ["memory", "troubleshooting", "performance"],
                "last_updated": "2024-01-15",
                "owner": "sre-team",
            },
        )
        runbooks.append(memory_runbook)

        # Performance troubleshooting runbook
        performance_runbook = ScrapedDocument(
            title="Redis Performance Troubleshooting",
            content="""
# Redis Performance Troubleshooting

## Overview
Procedures for diagnosing and resolving Redis performance issues.

## Key Metrics
- Latency (p50, p95, p99)
- Operations per second
- Memory usage
- CPU utilization
- Network I/O

## Diagnostic Commands

### Performance Monitoring
```bash
# Latency monitoring
redis-cli --latency -h <host> -p <port>

# Monitor commands in real-time
redis-cli MONITOR

# Check slow log
SLOWLOG GET 10
SLOWLOG LEN
```

### System Analysis
```bash
# Redis statistics
INFO stats
INFO commandstats

# Client connections
CLIENT LIST
INFO clients
```

## Common Issues

### High Latency
1. Check slow log: `SLOWLOG GET`
2. Monitor active commands: `MONITOR`
3. Check memory usage and swapping
4. Review client connection patterns
5. Analyze command complexity

### Low Throughput
1. Check CPU utilization
2. Review persistence settings
3. Monitor network bandwidth
4. Check client connection pooling
5. Analyze command distribution

### Connection Issues
1. Check max connections: `CONFIG GET maxclients`
2. Monitor client list: `CLIENT LIST`
3. Review timeout settings
4. Check network connectivity

## Resolution Steps

### Immediate Actions
1. Identify problematic commands from slow log
2. Check for blocking operations
3. Review recent configuration changes
4. Monitor system resources

### Performance Optimization
1. Tune persistence settings
2. Optimize data structures
3. Review pipeline usage
4. Consider read replicas for read-heavy workloads

## Alerts and Thresholds
- Latency > 10ms: Warning
- Latency > 50ms: Critical
- CPU > 80%: Warning
- Memory > 90%: Critical
- Connections > 80% of max: Warning
            """.strip(),
            source_url="internal://runbooks/redis-performance",
            category=DocumentCategory.SHARED,
            doc_type=DocumentType.RUNBOOK,
            severity=SeverityLevel.HIGH,
            metadata={
                "tags": ["performance", "latency", "monitoring"],
                "last_updated": "2024-01-20",
                "owner": "sre-team",
            },
        )
        runbooks.append(performance_runbook)

        return runbooks

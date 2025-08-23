"""Runbook generator that scrapes URLs and standardizes content using GPT-4o."""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
import openai
from bs4 import BeautifulSoup

from ...core.config import settings
from .base import (
    ArtifactStorage,
    BaseScraper,
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    SeverityLevel,
)

logger = logging.getLogger(__name__)


class RunbookGenerator(BaseScraper):
    """Generates standardized runbooks from various web sources using GPT-4o."""

    def __init__(self, storage: ArtifactStorage, config: Optional[Dict[str, Any]] = None):
        super().__init__(storage, config)

        # Default configuration with initial URLs
        self.config = {
            "runbook_urls": [
                # GitLab Redis survival guide
                "https://gitlab.com/gitlab-com/runbooks/-/blob/e7f620058ff9f81bec864aa6aebf3a6320c4f6a0/docs/redis/redis-survival-guide-for-sres.md",
                # Shoreline Redis runbooks
                "https://www.shoreline.io/runbooks/redis/redis-rejected-connections",
                "https://www.shoreline.io/runbooks/redis/redis-missing-master",
                # Official Redis documentation
                "https://redis.io/docs/latest/operate/oss_and_stack/management/replication/",
                "https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/",
                "https://redis.io/docs/latest/operate/oss_and_stack/management/debugging/",
            ],
            "openai_model": "gpt-4o",
            "max_retries": 3,
            "delay_between_requests": 2.0,
            "timeout": 60,
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            **(config or {}),
        }

        # Initialize OpenAI client
        self.openai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

        # Standard runbook format template
        self.runbook_template = """
# {title}

## Overview
{overview}

## Symptoms
{symptoms}

## Diagnostic Steps
{diagnostic_steps}

## Resolution Procedures
{resolution_procedures}

## Prevention
{prevention}

## Escalation
{escalation}

## Related Resources
{related_resources}
"""

        # GPT-4o prompt for runbook standardization
        self.standardization_prompt = """
You are an expert SRE (Site Reliability Engineer) specializing in Redis operations. Your task is to convert the provided content into a standardized, professional runbook format.

INSTRUCTIONS:
1. Analyze the provided content and extract key information
2. Structure it according to the standard SRE runbook format
3. Ensure all procedures are clear, actionable, and safe
4. Add Redis-specific context where appropriate
5. Include proper escalation procedures
6. Use professional SRE terminology

REQUIRED SECTIONS:
- **Overview**: Brief description of the issue/procedure (2-3 sentences)
- **Symptoms**: Observable signs that indicate this issue (bullet points)
- **Diagnostic Steps**: Commands and checks to confirm the issue (numbered steps with actual Redis commands)
- **Resolution Procedures**: Step-by-step instructions to resolve (numbered steps, be specific)
- **Prevention**: How to prevent this issue in the future (bullet points)
- **Escalation**: When and how to escalate (specific conditions and contact procedures)
- **Related Resources**: Links to relevant documentation or tools

GUIDELINES:
- Use Redis-specific commands (INFO, CONFIG, MONITOR, etc.)
- Include specific metrics and thresholds where possible
- Provide both immediate fixes and long-term solutions
- Mention monitoring alerts that should trigger
- Include rollback procedures if applicable
- Use clear, imperative language ("Check...", "Run...", "Verify...")

FORMAT: Return ONLY the structured runbook content. Do not include explanations or meta-commentary.

SOURCE CONTENT TO STANDARDIZE:
{source_content}
"""

    def get_source_name(self) -> str:
        return "runbook_generator"

    async def scrape(self) -> List[ScrapedDocument]:
        """Generate standardized runbooks from configured URLs."""
        documents = []

        for url in self.config["runbook_urls"]:
            try:
                logger.info(f"Processing runbook URL: {url}")

                # Scrape the source content
                raw_content = await self._scrape_url_content(url)
                if not raw_content:
                    logger.warning(f"No content extracted from {url}")
                    continue

                # Generate multiple runbooks from the content
                runbook_documents = await self._generate_multiple_runbooks(raw_content, url)
                if not runbook_documents:
                    logger.warning(f"Failed to generate runbooks from {url}")
                    continue

                documents.extend(runbook_documents)
                logger.info(f"Generated {len(runbook_documents)} runbooks from {url}")

                # Rate limiting
                await asyncio.sleep(self.config["delay_between_requests"])

            except Exception as e:
                logger.error(f"Failed to process runbook URL {url}: {e}")
                continue

        logger.info(f"Generated {len(documents)} standardized runbooks")
        return documents

    async def _scrape_url_content(self, url: str) -> Optional[str]:
        """Scrape content from a URL with smart content extraction."""
        headers = {
            "User-Agent": self.config["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        timeout = aiohttp.ClientTimeout(total=self.config["timeout"])

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.warning(f"HTTP {response.status} for {url}")
                        return None

                    html = await response.text()

                    # Handle different URL types
                    if "gitlab.com" in url:
                        return await self._extract_gitlab_content(html, url)
                    elif "shoreline.io" in url:
                        return await self._extract_shoreline_content(html)
                    elif "redis.io" in url:
                        return await self._extract_redis_docs_content(html)
                    else:
                        return await self._extract_generic_content(html)

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    async def _extract_gitlab_content(self, html: str, url: str) -> Optional[str]:
        """Extract content from GitLab markdown files."""
        soup = BeautifulSoup(html, "html.parser")

        # GitLab renders markdown in specific containers
        content_selectors = [
            ".file-content .blob-content",
            ".markdown-body",
            ".file-holder .file-content",
            "article",
            ".content",
        ]

        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # Extract text and preserve some structure
                content = content_elem.get_text(separator="\n", strip=True)

                # Clean up GitLab-specific artifacts
                content = re.sub(r"\n{3,}", "\n\n", content)  # Reduce excessive newlines
                content = re.sub(r"```[a-z]*\n", "```\n", content)  # Clean code block language tags

                if len(content) > 500:  # Ensure we got substantial content
                    return content

        logger.warning(f"Could not extract meaningful content from GitLab URL: {url}")
        return None

    async def _extract_shoreline_content(self, html: str) -> Optional[str]:
        """Extract content from Shoreline runbook pages."""
        soup = BeautifulSoup(html, "html.parser")

        # Shoreline runbook structure
        content_parts = []

        # Try to find the main content area
        main_content = soup.select_one('.main-content, .content, article, [role="main"]')
        if main_content:
            # Extract title
            title = soup.select_one("h1, .title, .page-title")
            if title:
                content_parts.append(f"# {title.get_text().strip()}")

            # Extract sections
            sections = main_content.find_all(
                ["h1", "h2", "h3", "h4", "p", "ul", "ol", "pre", "code"]
            )

            current_section = ""
            for element in sections:
                if element.name in ["h1", "h2", "h3", "h4"]:
                    if current_section:
                        content_parts.append(current_section.strip())
                    current_section = f"\n## {element.get_text().strip()}\n"
                else:
                    text = element.get_text(strip=True)
                    if text:
                        if element.name in ["pre", "code"]:
                            current_section += f"\n```\n{text}\n```\n"
                        elif element.name in ["ul", "ol"]:
                            # Process list items
                            items = element.find_all("li")
                            for item in items:
                                current_section += f"- {item.get_text().strip()}\n"
                        else:
                            current_section += f"{text}\n"

            if current_section:
                content_parts.append(current_section.strip())

            content = "\n\n".join(content_parts)
            if len(content) > 200:
                return content

        # Fallback to simple text extraction
        body = soup.find("body")
        if body:
            content = body.get_text(separator="\n", strip=True)
            # Clean up
            content = re.sub(r"\n{3,}", "\n\n", content)
            content = re.sub(r"^\s*$", "", content, flags=re.MULTILINE)

            if len(content) > 500:
                return content

        return None

    async def _extract_redis_docs_content(self, html: str) -> Optional[str]:
        """Extract content from Redis official documentation."""
        soup = BeautifulSoup(html, "html.parser")

        # Redis.io documentation structure
        content_parts = []

        # Try to find the main article content
        main_content = soup.select_one(
            'article, .content, .doc-content, [role="main"], .main-content'
        )
        if not main_content:
            # Fallback to common content selectors
            main_content = soup.select_one(".markdown-body, .rst-content, #content")

        if main_content:
            # Extract title
            title = soup.select_one("h1, .page-title, .doc-title")
            if title:
                content_parts.append(f"# {title.get_text().strip()}")

            # Process content elements in order
            elements = main_content.find_all(
                [
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "p",
                    "ul",
                    "ol",
                    "pre",
                    "code",
                    "blockquote",
                    "div",
                ]
            )

            for element in elements:
                text = element.get_text(strip=True)
                if not text:
                    continue

                if element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                    # Headers - create markdown headers
                    level = int(element.name[1])
                    content_parts.append(f"\n{'#' * level} {text}\n")
                elif element.name == "p":
                    # Paragraphs
                    content_parts.append(f"{text}\n")
                elif element.name in ["ul", "ol"]:
                    # Lists - process list items
                    items = element.find_all("li")
                    for item in items:
                        item_text = item.get_text().strip()
                        if item_text:
                            content_parts.append(f"- {item_text}")
                    content_parts.append("")  # Add spacing after lists
                elif element.name in ["pre", "code"]:
                    # Code blocks
                    content_parts.append(f"\n```\n{text}\n```\n")
                elif element.name == "blockquote":
                    # Blockquotes
                    content_parts.append(f"> {text}\n")
                elif element.name == "div" and element.get("class"):
                    # Handle special div classes (alerts, notes, etc.)
                    classes = " ".join(element.get("class", []))
                    if any(
                        cls in classes.lower()
                        for cls in ["note", "warning", "alert", "tip", "important"]
                    ):
                        content_parts.append(f"**Note:** {text}\n")

            content = "\n".join(content_parts)

            # Clean up the content
            content = re.sub(r"\n{3,}", "\n\n", content)  # Reduce excessive newlines
            content = re.sub(r"^\s*$", "", content, flags=re.MULTILINE)  # Remove empty lines

            if len(content) > 300:  # Ensure we got substantial content
                return content.strip()

        # Fallback to generic extraction if the specific method fails
        return await self._extract_generic_content(html)

    async def _extract_generic_content(self, html: str) -> Optional[str]:
        """Extract content from generic web pages."""
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()

        # Try common content selectors
        content_selectors = [
            "main",
            "article",
            ".content",
            ".main-content",
            ".post-content",
            "#content",
            ".entry-content",
            ".page-content",
        ]

        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                content = content_elem.get_text(separator="\n", strip=True)
                if len(content) > 500:
                    return content

        # Fallback to body
        body = soup.find("body")
        if body:
            content = body.get_text(separator="\n", strip=True)
            # Clean up common web page artifacts
            content = re.sub(r"\n{3,}", "\n\n", content)
            if len(content) > 500:
                return content

        return None

    async def _generate_standardized_runbook(
        self, raw_content: str, source_url: str
    ) -> Optional[str]:
        """Use GPT-4o to generate a standardized runbook from raw content."""
        try:
            prompt = self.standardization_prompt.format(source_content=raw_content)

            response = await self.openai_client.chat.completions.create(
                model=self.config["openai_model"],
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert SRE specializing in Redis operations and runbook standardization.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,  # Low temperature for consistent, professional output
                max_tokens=4000,
            )

            standardized_content = response.choices[0].message.content.strip()

            # Validate that we got a proper runbook format
            if self._validate_runbook_format(standardized_content):
                return standardized_content
            else:
                logger.warning(
                    f"Generated runbook for {source_url} doesn't meet format requirements"
                )
                return None

        except Exception as e:
            logger.error(f"Error generating standardized runbook for {source_url}: {e}")
            return None

    def _validate_runbook_format(self, content: str) -> bool:
        """Validate that the generated content follows proper runbook format."""
        required_sections = [
            "overview",
            "symptoms",
            "diagnostic",
            "resolution",
            "prevention",
            "escalation",
        ]

        content_lower = content.lower()

        # Check for required sections (flexible matching)
        found_sections = 0
        for section in required_sections:
            if section in content_lower:
                found_sections += 1

        # Must have at least 4 of 6 required sections
        if found_sections < 4:
            return False

        # Must have reasonable length
        if len(content) < 500:
            return False

        # Should have some structure (headers)
        if not re.search(r"^#+ ", content, re.MULTILINE):
            return False

        return True

    async def _analyze_runbook_metadata(
        self, runbook_content: str, source_url: str
    ) -> Tuple[str, DocumentCategory, SeverityLevel]:
        """Analyze runbook to determine title, category, and severity."""

        # Extract title from first header
        title_match = re.search(r"^#+ (.+)", runbook_content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        else:
            # Fallback title based on URL
            title = f"Redis Runbook - {urlparse(source_url).path.split('/')[-1]}"

        # Determine category based on source and content
        content_lower = runbook_content.lower()
        if "gitlab" in source_url.lower():
            category = DocumentCategory.OSS  # GitLab is open source
        elif any(word in content_lower for word in ["enterprise", "commercial", "licensed"]):
            category = DocumentCategory.ENTERPRISE
        else:
            category = DocumentCategory.SHARED

        # Determine severity based on content keywords
        critical_keywords = ["outage", "down", "critical", "emergency", "data loss", "corruption"]
        high_keywords = ["performance", "slow", "latency", "memory", "cpu", "connection"]

        if any(word in content_lower for word in critical_keywords):
            severity = SeverityLevel.CRITICAL
        elif any(word in content_lower for word in high_keywords):
            severity = SeverityLevel.HIGH
        else:
            severity = SeverityLevel.MEDIUM

        return title, category, severity

    def _detect_source_type(self, url: str) -> str:
        """Detect the type of source based on URL."""
        if "gitlab.com" in url:
            return "gitlab_runbook"
        elif "shoreline.io" in url:
            return "shoreline_runbook"
        elif "redis.io" in url:
            return "redis_official_docs"
        elif "github.com" in url:
            return "github_repository"
        else:
            return "external_website"

    async def _generate_multiple_runbooks(
        self, raw_content: str, source_url: str
    ) -> List[ScrapedDocument]:
        """Generate multiple focused runbooks from a single source URL.

        For comprehensive documentation pages, this breaks down content into
        multiple focused runbooks rather than creating one large document.

        Args:
            raw_content: The scraped raw content from the URL
            source_url: The source URL being processed

        Returns:
            List of ScrapedDocument objects, each representing a focused runbook
        """
        documents = []

        try:
            # First, analyze the content to identify distinct topics/sections
            topics = await self._identify_runbook_topics(raw_content)

            if len(topics) <= 1:
                # If only one topic or unable to segment, fall back to single runbook
                logger.info(f"Single topic identified for {source_url}, creating one runbook")
                standardized_runbook = await self._generate_standardized_runbook(
                    raw_content, source_url
                )
                if standardized_runbook:
                    title, category, severity = await self._analyze_runbook_metadata(
                        standardized_runbook, source_url
                    )

                    document = ScrapedDocument(
                        title=title,
                        content=standardized_runbook,
                        source_url=source_url,
                        category=category,
                        doc_type=DocumentType.RUNBOOK,
                        severity=severity,
                        metadata={
                            "generated_by": "runbook_generator",
                            "source_type": self._detect_source_type(source_url),
                            "standardized_at": datetime.now(timezone.utc).isoformat(),
                            "original_length": len(raw_content),
                            "standardized_length": len(standardized_runbook),
                            "processing_model": self.config["openai_model"],
                            "runbook_count": 1,
                            "topic_index": 0,
                        },
                    )
                    documents.append(document)
                return documents

            # Generate focused runbooks for each identified topic
            logger.info(f"Identified {len(topics)} distinct topics in {source_url}")

            for i, topic in enumerate(topics):
                try:
                    # Extract relevant content for this topic
                    topic_content = await self._extract_topic_content(raw_content, topic)
                    if not topic_content:
                        logger.warning(f"No content extracted for topic: {topic['title']}")
                        continue

                    # Generate focused runbook for this topic
                    focused_runbook = await self._generate_focused_runbook(
                        topic_content, topic, source_url
                    )
                    if not focused_runbook:
                        logger.warning(f"Failed to generate runbook for topic: {topic['title']}")
                        continue

                    # Analyze metadata for this specific runbook
                    title, category, severity = await self._analyze_runbook_metadata(
                        focused_runbook, source_url
                    )

                    # Ensure title is unique and descriptive
                    if len(topics) > 1:
                        title = (
                            f"{title} - {topic['title']}"
                            if topic["title"].lower() not in title.lower()
                            else title
                        )

                    document = ScrapedDocument(
                        title=title,
                        content=focused_runbook,
                        source_url=source_url,
                        category=category,
                        doc_type=DocumentType.RUNBOOK,
                        severity=severity,
                        metadata={
                            "generated_by": "runbook_generator",
                            "source_type": self._detect_source_type(source_url),
                            "standardized_at": datetime.now(timezone.utc).isoformat(),
                            "original_length": len(raw_content),
                            "standardized_length": len(focused_runbook),
                            "processing_model": self.config["openai_model"],
                            "runbook_count": len(topics),
                            "topic_index": i,
                            "topic_title": topic["title"],
                            "topic_summary": topic.get("summary", ""),
                        },
                    )

                    documents.append(document)
                    logger.info(f"Generated focused runbook: {title}")

                except Exception as e:
                    logger.error(
                        f"Error generating runbook for topic '{topic.get('title', 'unknown')}': {e}"
                    )
                    continue

            return documents

        except Exception as e:
            logger.error(f"Error generating multiple runbooks from {source_url}: {e}")
            # Fallback to single runbook generation
            standardized_runbook = await self._generate_standardized_runbook(
                raw_content, source_url
            )
            if standardized_runbook:
                title, category, severity = await self._analyze_runbook_metadata(
                    standardized_runbook, source_url
                )

                document = ScrapedDocument(
                    title=title,
                    content=standardized_runbook,
                    source_url=source_url,
                    category=category,
                    doc_type=DocumentType.RUNBOOK,
                    severity=severity,
                    metadata={
                        "generated_by": "runbook_generator",
                        "source_type": self._detect_source_type(source_url),
                        "standardized_at": datetime.now(timezone.utc).isoformat(),
                        "original_length": len(raw_content),
                        "standardized_length": len(standardized_runbook),
                        "processing_model": self.config["openai_model"],
                        "runbook_count": 1,
                        "topic_index": 0,
                        "fallback_generation": True,
                    },
                )
                return [document]
            return []

    async def _identify_runbook_topics(self, content: str) -> List[Dict[str, str]]:
        """Identify distinct topics that could become separate runbooks.

        Args:
            content: Raw content to analyze

        Returns:
            List of topic dictionaries with 'title', 'summary', and 'keywords'
        """
        try:
            # Use GPT-4o to identify distinct runbook topics
            topic_analysis_prompt = """
Analyze the following technical content and identify distinct, actionable topics that could each become a separate SRE runbook.

Each topic should represent a specific problem, procedure, or operational task that an SRE would need to handle.

Return your analysis as a JSON array where each topic has:
- "title": Clear, specific title for the runbook (e.g., "Redis Memory Pressure Response", "Redis Replication Lag Troubleshooting")
- "summary": 2-3 sentence summary of what this runbook covers
- "keywords": Array of key terms that identify this topic in the content

Only identify topics that have enough actionable content to warrant a separate runbook (at least diagnostic steps and resolution procedures).

If the content represents a single cohesive topic, return an array with just one topic.

Content to analyze:
{content}

Respond with only the JSON array, no other text.
"""

            response = await self.openai_client.chat.completions.create(
                model=self.config["openai_model"],
                messages=[
                    {
                        "role": "user",
                        "content": topic_analysis_prompt.format(content=content[:8000]),
                    }  # Limit content length
                ],
                temperature=0.3,
                max_tokens=1500,
            )

            # Parse the JSON response
            import json

            topics_json = response.choices[0].message.content.strip()

            # Handle markdown code blocks if present
            if topics_json.startswith("```json"):
                topics_json = topics_json[7:]
            if topics_json.endswith("```"):
                topics_json = topics_json[:-3]
            topics_json = topics_json.strip()

            topics = json.loads(topics_json)

            # Validate topics structure
            validated_topics = []
            for topic in topics:
                if isinstance(topic, dict) and "title" in topic and "summary" in topic:
                    validated_topics.append(
                        {
                            "title": topic["title"][:100],  # Limit title length
                            "summary": topic["summary"][:500],  # Limit summary length
                            "keywords": topic.get("keywords", [])[:10],  # Limit keywords
                        }
                    )

            return validated_topics

        except Exception as e:
            logger.error(f"Error identifying topics: {e}")
            return []

    async def _extract_topic_content(
        self, raw_content: str, topic: Dict[str, str]
    ) -> Optional[str]:
        """Extract content relevant to a specific topic from the raw content.

        Args:
            raw_content: Full raw content
            topic: Topic dictionary with title, summary, keywords

        Returns:
            Content relevant to the specific topic, or None if extraction fails
        """
        try:
            extraction_prompt = """
Extract all content from the provided text that is relevant to the following specific topic:

**Topic Title**: {title}
**Topic Summary**: {summary}
**Keywords**: {keywords}

Instructions:
1. Extract all sections, paragraphs, commands, procedures, and examples related to this topic
2. Include relevant context but exclude unrelated sections
3. Maintain the original structure and formatting
4. If the content contains code blocks, commands, or procedures, include them exactly as written
5. Include any diagnostic steps, troubleshooting procedures, configuration examples, or best practices related to this topic

Source Content:
{content}

Return only the extracted relevant content, preserving formatting and structure.
"""

            response = await self.openai_client.chat.completions.create(
                model=self.config["openai_model"],
                messages=[
                    {
                        "role": "user",
                        "content": extraction_prompt.format(
                            title=topic["title"],
                            summary=topic["summary"],
                            keywords=", ".join(topic.get("keywords", [])),
                            content=raw_content,
                        ),
                    }
                ],
                temperature=0.1,  # Low temperature for accurate extraction
                max_tokens=4000,
            )

            extracted_content = response.choices[0].message.content.strip()

            # Validate that we got meaningful content
            if len(extracted_content) < 100:  # Too short to be useful
                logger.warning(f"Extracted content too short for topic: {topic['title']}")
                return None

            return extracted_content

        except Exception as e:
            logger.error(f"Error extracting content for topic '{topic['title']}': {e}")
            return None

    async def _generate_focused_runbook(
        self, topic_content: str, topic: Dict[str, str], source_url: str
    ) -> Optional[str]:
        """Generate a focused runbook for a specific topic.

        Args:
            topic_content: Content specific to this topic
            topic: Topic metadata
            source_url: Original source URL

        Returns:
            Standardized runbook content for the specific topic
        """
        try:
            focused_prompt = f"""
{self.standardization_prompt}

SPECIFIC TOPIC: {topic['title']}
TOPIC CONTEXT: {topic['summary']}

Convert the following content into a focused, actionable runbook specifically for: {topic['title']}

Ensure the runbook is:
1. Focused specifically on this topic/problem area
2. Contains actionable diagnostic steps and resolution procedures
3. Includes Redis-specific commands and examples where relevant
4. Provides clear escalation paths
5. Uses the standard SRE runbook format

Content to convert:
{topic_content}

Generate a complete, professional runbook following the standard format.
"""

            response = await self.openai_client.chat.completions.create(
                model=self.config["openai_model"],
                messages=[{"role": "user", "content": focused_prompt}],
                temperature=0.3,
                max_tokens=3000,
            )

            standardized_content = response.choices[0].message.content.strip()

            # Validate the runbook format
            if self._validate_runbook_format(standardized_content):
                return standardized_content
            else:
                logger.warning(
                    f"Generated focused runbook for '{topic['title']}' doesn't meet format requirements"
                )
                return None

        except Exception as e:
            logger.error(f"Error generating focused runbook for topic '{topic['title']}': {e}")
            return None

    async def add_runbook_url(self, url: str) -> bool:
        """Add a new URL to the runbook generation list."""
        if url not in self.config["runbook_urls"]:
            self.config["runbook_urls"].append(url)
            logger.info(f"Added new runbook URL: {url}")
            return True
        return False

    def get_configured_urls(self) -> List[str]:
        """Get the current list of configured URLs."""
        return self.config["runbook_urls"].copy()

    async def test_url_extraction(self, url: str) -> Dict[str, Any]:
        """Test content extraction from a URL without generating a full runbook."""
        try:
            raw_content = await self._scrape_url_content(url)

            return {
                "url": url,
                "success": raw_content is not None,
                "content_length": len(raw_content) if raw_content else 0,
                "content_preview": raw_content[:500] if raw_content else None,
                "source_type": self._detect_source_type(url),
            }
        except Exception as e:
            return {
                "url": url,
                "success": False,
                "error": str(e),
                "source_type": self._detect_source_type(url),
            }

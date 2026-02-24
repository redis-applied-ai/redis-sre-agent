"""Tests for runbook generator scraper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.pipelines.scraper.base import (
    ArtifactStorage,
    DocumentCategory,
    DocumentType,
    SeverityLevel,
)
from redis_sre_agent.pipelines.scraper.runbook_generator import RunbookGenerator


class TestRunbookGenerator:
    """Test runbook generator functionality."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create test storage."""
        return ArtifactStorage(tmp_path)

    @pytest.fixture
    def generator(self, storage):
        """Create runbook generator instance."""
        config = {
            "runbook_urls": [
                "https://gitlab.com/test-runbook.md",
                "https://github.com/test/repo",
                "https://example.com/test-guide",
            ],
            "openai_model": "gpt-4o",
            "timeout": 30,
            "delay_between_requests": 0.1,
        }
        return RunbookGenerator(storage, config)

    def test_init_with_default_urls(self, storage):
        """Test initialization includes GitLab runbook URL."""
        generator = RunbookGenerator(storage)

        expected_url = "https://gitlab.com/gitlab-com/runbooks/-/blob/e7f620058ff9f81bec864aa6aebf3a6320c4f6a0/docs/redis/redis-survival-guide-for-sres.md"

        assert expected_url in generator.config["runbook_urls"]
        # Should have exactly 1 default URL now
        assert len(generator.config["runbook_urls"]) == 1

    def test_get_source_name(self, generator):
        """Test source name identification."""
        assert generator.get_source_name() == "runbook_generator"

    def test_detect_source_type(self, generator):
        """Test URL source type detection."""
        test_cases = [
            ("https://gitlab.com/runbook", "gitlab_runbook"),
            ("https://github.com/redis/redis", "github_repository"),
            ("https://example.com/docs", "external_website"),
        ]

        for url, expected_type in test_cases:
            assert generator._detect_source_type(url) == expected_type

    def test_validate_runbook_format_valid(self, generator):
        """Test runbook format validation with valid content."""
        valid_runbook = """# Redis Memory Issues

## Overview
This runbook covers Redis memory troubleshooting and provides comprehensive diagnostic procedures for SRE teams.

## Symptoms
- High memory usage alerts from monitoring systems
- OOM killer activation in system logs

## Diagnostic Steps
1. Check INFO memory command output
2. Analyze memory usage patterns over time

## Resolution Procedures
1. Identify memory leaks using Redis tools
2. Optimize data structures and configurations

## Prevention
- Monitor memory metrics continuously
- Set memory limits appropriately

## Escalation
Contact Redis team if issues persist beyond initial troubleshooting
"""

        assert generator._validate_runbook_format(valid_runbook) is True

    def test_validate_runbook_format_invalid(self, generator):
        """Test runbook format validation with invalid content."""
        # Too short
        assert generator._validate_runbook_format("Too short") is False

        # Missing sections
        missing_sections = "# Title\n\nJust some content without proper sections."
        assert generator._validate_runbook_format(missing_sections) is False

        # No headers
        no_headers = "This is a long document without any headers. " * 50
        assert generator._validate_runbook_format(no_headers) is False

    @pytest.mark.asyncio
    async def test_analyze_runbook_metadata(self, generator):
        """Test metadata analysis from runbook content."""
        runbook_content = """# Redis Performance Optimization

This runbook covers critical Redis performance issues that can cause
outages and data loss if not addressed quickly.
"""

        title, category, severity = await generator._analyze_runbook_metadata(
            runbook_content, "https://redis.io/docs/performance"
        )

        assert title == "Redis Performance Optimization"
        assert category == DocumentCategory.SHARED
        assert severity == SeverityLevel.CRITICAL  # Contains "outages" and "data loss"

    @pytest.mark.asyncio
    async def test_extract_gitlab_content(self, generator):
        """Test GitLab content extraction."""
        gitlab_html = """
        <html>
        <body>
        <div class="file-content">
            <div class="blob-content">
                <h1>Redis Survival Guide</h1>
                <p>This comprehensive guide covers Redis operations and best practices for SRE teams. It provides detailed procedures for monitoring, troubleshooting, and maintaining Redis infrastructure in production environments.</p>
                <h2>Memory Management</h2>
                <p>Redis memory usage guidelines include monitoring memory consumption, setting appropriate limits, and understanding memory allocation patterns. Key commands include INFO memory, MEMORY USAGE, and configuration options for memory policies.</p>
                <h3>Diagnostic Commands</h3>
                <pre><code>INFO memory
MEMORY USAGE key_name
CONFIG GET maxmemory-policy</code></pre>
                <p>Additional content to ensure we meet the minimum length requirements for content extraction validation.</p>
            </div>
        </div>
        </body>
        </html>
        """

        content = await generator._extract_gitlab_content(gitlab_html, "https://gitlab.com/test")

        assert content is not None
        assert "Redis Survival Guide" in content
        assert "Memory Management" in content
        assert "INFO memory" in content

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_scrape_url_content_success(self, mock_get, generator):
        """Test successful URL content scraping."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html><body>Test content</body></html>")

        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock the content extraction method
        with patch.object(generator, "_extract_generic_content") as mock_extract:
            mock_extract.return_value = "Extracted test content"

            result = await generator._scrape_url_content("https://example.com/test")

            assert result == "Extracted test content"
            mock_extract.assert_called_once()

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_scrape_url_content_http_error(self, mock_get, generator):
        """Test URL scraping with HTTP error."""
        mock_response = AsyncMock()
        mock_response.status = 404

        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await generator._scrape_url_content("https://example.com/notfound")

        assert result is None

    @pytest.mark.asyncio
    @patch("openai.AsyncOpenAI")
    async def test_generate_standardized_runbook_success(self, mock_openai_class, generator):
        """Test successful runbook standardization with GPT-4o."""
        mock_openai = AsyncMock()
        mock_openai_class.return_value = mock_openai

        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """# Redis Memory Management

## Overview
Redis memory optimization procedures for production environments.

## Symptoms
- High memory usage alerts from monitoring systems
- Application performance degradation due to memory pressure

## Diagnostic Steps
1. Run INFO memory to check current usage
2. Analyze memory patterns over time

## Resolution Procedures
1. Optimize data structures and key patterns
2. Configure appropriate memory policies

## Prevention
- Monitor memory metrics continuously
- Set memory limits and alerts

## Escalation
Contact team lead for persistent memory issues
"""

        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        # Update the generator's OpenAI client (private attribute since openai_client is a lazy property)
        generator._openai_client = mock_openai

        result = await generator._generate_standardized_runbook(
            "Raw content about Redis memory", "https://example.com"
        )

        assert result is not None
        assert "# Redis Memory Management" in result
        assert "## Overview" in result
        assert "## Symptoms" in result

        # Verify OpenAI was called with correct parameters
        mock_openai.chat.completions.create.assert_called_once()
        call_args = mock_openai.chat.completions.create.call_args
        assert call_args[1]["model"] == "gpt-4o"
        # Temperature parameter removed for reasoning models

    @pytest.mark.asyncio
    @patch("openai.AsyncOpenAI")
    async def test_generate_standardized_runbook_invalid_format(self, mock_openai_class, generator):
        """Test runbook generation with invalid format response."""
        mock_openai = AsyncMock()
        mock_openai_class.return_value = mock_openai

        # Mock OpenAI response with invalid format
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Too short and invalid format"

        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
        generator._openai_client = mock_openai

        result = await generator._generate_standardized_runbook(
            "Raw content", "https://example.com"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_add_runbook_url(self, generator):
        """Test adding new runbook URL."""
        new_url = "https://redis.io/docs/new-guide"

        # URL should be added successfully
        result = await generator.add_runbook_url(new_url)
        assert result is True
        assert new_url in generator.config["runbook_urls"]

        # Adding same URL again should return False
        result = await generator.add_runbook_url(new_url)
        assert result is False

    def test_get_configured_urls(self, generator):
        """Test getting configured URLs."""
        urls = generator.get_configured_urls()

        assert isinstance(urls, list)
        assert len(urls) > 0
        assert "https://gitlab.com/test-runbook.md" in urls

    @pytest.mark.asyncio
    async def test_test_url_extraction_success(self, generator):
        """Test URL extraction testing method."""
        with patch.object(generator, "_scrape_url_content") as mock_scrape:
            mock_scrape.return_value = "Test content from URL"

            # Use GitLab URL since redis.io is now treated as external_website
            result = await generator.test_url_extraction("https://gitlab.com/test-runbook")

            assert result["success"] is True
            assert result["content_length"] == len("Test content from URL")
            assert result["source_type"] == "gitlab_runbook"
            assert "Test content" in result["content_preview"]

    @pytest.mark.asyncio
    async def test_test_url_extraction_failure(self, generator):
        """Test URL extraction testing with failure."""
        with patch.object(generator, "_scrape_url_content") as mock_scrape:
            mock_scrape.side_effect = Exception("Network error")

            result = await generator.test_url_extraction("https://invalid-url.com")

            assert result["success"] is False
            assert "error" in result
            assert result["source_type"] == "external_website"

    @pytest.mark.asyncio
    @patch.object(RunbookGenerator, "_scrape_url_content")
    @patch.object(RunbookGenerator, "_generate_standardized_runbook")
    @patch.object(RunbookGenerator, "_analyze_runbook_metadata")
    async def test_scrape_complete_workflow(
        self, mock_analyze, mock_generate, mock_scrape, generator
    ):
        """Test complete scraping workflow."""
        # Mock the workflow steps
        mock_scrape.return_value = "Raw content from URL"
        mock_generate.return_value = "# Standardized Runbook\n\n## Overview\nTest runbook"
        mock_analyze.return_value = ("Test Runbook", DocumentCategory.OSS, SeverityLevel.MEDIUM)

        # Set up a single URL for testing
        generator.config["runbook_urls"] = ["https://redis.io/docs/test"]

        documents = await generator.scrape()

        assert len(documents) == 1
        document = documents[0]

        assert document.title == "Test Runbook"
        assert document.category == DocumentCategory.OSS
        assert document.severity == SeverityLevel.MEDIUM
        assert document.doc_type == DocumentType.RUNBOOK
        assert "Standardized Runbook" in document.content

        # Verify all methods were called
        mock_scrape.assert_called_once()
        mock_generate.assert_called_once()
        mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrape_with_errors(self, generator):
        """Test scraping handles errors gracefully."""
        # Set up a URL that will fail
        generator.config["runbook_urls"] = ["https://invalid-url.example"]

        with patch.object(generator, "_scrape_url_content") as mock_scrape:
            mock_scrape.side_effect = Exception("Network error")

            documents = await generator.scrape()

            # Should return empty list when all URLs fail
            assert documents == []

    def test_runbook_template_format(self, generator):
        """Test runbook template has correct structure."""
        template = generator.runbook_template

        required_sections = [
            "{title}",
            "{overview}",
            "{symptoms}",
            "{diagnostic_steps}",
            "{resolution_procedures}",
            "{prevention}",
            "{escalation}",
            "{related_resources}",
        ]

        for section in required_sections:
            assert section in template

    def test_standardization_prompt_quality(self, generator):
        """Test standardization prompt includes key requirements."""
        prompt = generator.standardization_prompt

        required_elements = [
            "SRE",
            "standardized",
            "Overview",
            "Symptoms",
            "Diagnostic Steps",
            "Resolution Procedures",
            "Prevention",
            "Escalation",
            "Redis",
            "commands",
            "INFO",
            "CONFIG",
            "MONITOR",
        ]

        for element in required_elements:
            assert element in prompt

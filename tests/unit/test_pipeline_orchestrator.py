"""Tests for pipeline orchestrator."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.pipelines.orchestrator import PipelineOrchestrator
from redis_sre_agent.pipelines.scraper.base import (
    ArtifactStorage,
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    SeverityLevel,
)


class TestPipelineOrchestrator:
    """Test pipeline orchestrator functionality."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create test storage."""
        return ArtifactStorage(tmp_path)

    @pytest.fixture
    def orchestrator(self, tmp_path):
        """Create pipeline orchestrator instance."""
        config = {
            "redis_docs": {"source": "test"},
            "redis_runbooks": {"source": "test"},
            "runbook_generator": {"runbook_urls": ["https://test.com"]},
            "ingestion": {"chunk_size": 500},
        }
        return PipelineOrchestrator(str(tmp_path), config)

    @pytest.fixture
    def sample_document(self):
        """Create sample scraped document."""
        return ScrapedDocument(
            title="Test Redis Guide",
            content="This is test content for Redis operations and troubleshooting.",
            source_url="https://redis.io/docs/test",
            category=DocumentCategory.OSS,
            doc_type=DocumentType.DOCUMENTATION,
            severity=SeverityLevel.MEDIUM,
            metadata={"test": True},
        )

    def test_init_with_default_config(self, tmp_path):
        """Test orchestrator initialization with default configuration."""
        orchestrator = PipelineOrchestrator(str(tmp_path))

        assert orchestrator.artifacts_path == Path(tmp_path)
        assert isinstance(orchestrator.storage, ArtifactStorage)
        assert "redis_docs" in orchestrator.scrapers
        assert "redis_runbooks" in orchestrator.scrapers
        assert "runbook_generator" in orchestrator.scrapers
        assert orchestrator.ingestion is not None

    def test_init_with_custom_config(self, orchestrator):
        """Test orchestrator initialization with custom configuration."""
        assert orchestrator.config["ingestion"]["chunk_size"] == 500
        assert "redis_docs" in orchestrator.scrapers
        assert "runbook_generator" in orchestrator.scrapers

    @pytest.mark.asyncio
    async def test_run_scraping_pipeline_success(self, orchestrator):
        """Test successful scraping pipeline execution."""
        # Mock scraper results
        mock_scraper_result = {
            "source": "test_scraper",
            "documents_scraped": 3,
            "batch_date": "2025-01-20",
            "success": True,
        }

        # Mock sample documents
        sample_docs = [
            ScrapedDocument(
                title=f"Test Doc {i}",
                content=f"Content {i}",
                source_url=f"https://test.com/doc{i}",
                category=DocumentCategory.OSS,
                doc_type=DocumentType.DOCUMENTATION,
                severity=SeverityLevel.MEDIUM,
            )
            for i in range(3)
        ]

        # Patch scrapers to return mock results
        for scraper_name, scraper in orchestrator.scrapers.items():
            scraper.run_scraping_job = AsyncMock(return_value=mock_scraper_result)
            scraper.scraped_documents = sample_docs

        # Patch storage manifest saving
        with patch.object(orchestrator.storage, "save_batch_manifest") as mock_save:
            mock_save.return_value = Path("/test/manifest.json")

            result = await orchestrator.run_scraping_pipeline()

        assert result["success"] is True
        assert result["total_documents"] == 12  # Actual count from scrapers
        assert (
            len(result["scraper_results"]) == 4
        )  # 4 scrapers: redis_docs, redis_kb, redis_runbooks, runbook_generator
        assert "manifest_path" in result

        # Verify all scrapers were called
        for scraper in orchestrator.scrapers.values():
            scraper.run_scraping_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_scraping_pipeline_with_failures(self, orchestrator):
        """Test scraping pipeline handles scraper failures."""
        # Mock one scraper to fail
        orchestrator.scrapers["redis_docs"].run_scraping_job = AsyncMock(
            side_effect=Exception("Scraper failed")
        )
        orchestrator.scrapers["redis_docs"].scraped_documents = []

        # Mock other scrapers to succeed
        sample_docs = [
            ScrapedDocument(
                title="Test Doc",
                content="Test content",
                source_url="https://test.com",
                category=DocumentCategory.OSS,
                doc_type=DocumentType.DOCUMENTATION,
                severity=SeverityLevel.MEDIUM,
            )
        ]

        # Mock all other scrapers to succeed with 1 document each
        for scraper_name in ["redis_kb", "redis_runbooks", "runbook_generator"]:
            orchestrator.scrapers[scraper_name].run_scraping_job = AsyncMock(
                return_value={"documents_scraped": 1, "success": True}
            )
            orchestrator.scrapers[scraper_name].scraped_documents = [sample_docs[0]]

        with patch.object(orchestrator.storage, "save_batch_manifest") as mock_save:
            mock_save.return_value = Path("/test/manifest.json")

            result = await orchestrator.run_scraping_pipeline()

        assert result["success"] is True  # Pipeline continues despite one failure
        assert "error" in result["scraper_results"]["redis_docs"]
        assert result["scraper_results"]["redis_docs"]["documents_scraped"] == 0
        assert result["total_documents"] == 3  # 3 successful scrapers with 1 document each

    @pytest.mark.asyncio
    async def test_run_scraping_pipeline_with_specific_scrapers(self, orchestrator):
        """Test running scraping pipeline with specific scrapers only."""
        mock_result = {"documents_scraped": 1, "success": True}
        sample_doc = [
            ScrapedDocument(
                title="Test",
                content="Content",
                source_url="https://test.com",
                category=DocumentCategory.OSS,
                doc_type=DocumentType.DOCUMENTATION,
                severity=SeverityLevel.MEDIUM,
            )
        ]

        # Only mock the redis_docs scraper
        orchestrator.scrapers["redis_docs"].run_scraping_job = AsyncMock(return_value=mock_result)
        orchestrator.scrapers["redis_docs"].scraped_documents = sample_doc

        with patch.object(orchestrator.storage, "save_batch_manifest") as mock_save:
            mock_save.return_value = Path("/test/manifest.json")

            result = await orchestrator.run_scraping_pipeline(scrapers=["redis_docs"])

        assert result["success"] is True
        assert len(result["scraper_results"]) == 1
        assert "redis_docs" in result["scraper_results"]
        assert result["scrapers_run"] == ["redis_docs"]

    @pytest.mark.asyncio
    async def test_run_ingestion_pipeline_success(self, orchestrator, tmp_path):
        """Test successful ingestion pipeline execution."""
        batch_date = "2025-01-20"

        # Create mock batch directory structure
        batch_path = tmp_path / batch_date
        batch_path.mkdir()

        # Create manifest
        manifest = {
            "batch_date": batch_date,
            "documents": [{"title": "Test Doc", "category": "oss"}],
        }
        manifest_path = batch_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Mock ingestion result
        mock_ingestion_result = {
            "batch_date": batch_date,
            "documents_processed": 5,
            "chunks_indexed": 15,
            "success": True,
        }

        with patch.object(orchestrator.ingestion, "ingest_batch") as mock_ingest:
            mock_ingest.return_value = mock_ingestion_result

            result = await orchestrator.run_ingestion_pipeline(batch_date)

        assert result == mock_ingestion_result
        mock_ingest.assert_called_once_with(batch_date)

    @pytest.mark.asyncio
    async def test_run_full_pipeline_success(self, orchestrator):
        """Test successful full pipeline execution."""
        # Mock scraping results
        scraping_result = {"success": True, "total_documents": 10, "batch_date": "2025-01-20"}

        # Mock ingestion results
        ingestion_result = {"success": True, "documents_processed": 10, "chunks_indexed": 25}

        with patch.object(orchestrator, "run_scraping_pipeline") as mock_scrape:
            mock_scrape.return_value = scraping_result

            with patch.object(orchestrator, "run_ingestion_pipeline") as mock_ingest:
                mock_ingest.return_value = ingestion_result

                result = await orchestrator.run_full_pipeline()

        assert result["success"] is True
        assert result["scraping"] == scraping_result
        assert result["ingestion"] == ingestion_result
        assert "started_at" in result
        assert "completed_at" in result

        mock_scrape.assert_called_once()
        mock_ingest.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_full_pipeline_skip_ingestion(self, orchestrator):
        """Test full pipeline skips ingestion when no documents scraped."""
        # Mock scraping results with no documents
        scraping_result = {
            "success": True,
            "total_documents": 0,  # No documents scraped
            "batch_date": "2025-01-20",
        }

        with patch.object(orchestrator, "run_scraping_pipeline") as mock_scrape:
            mock_scrape.return_value = scraping_result

            with patch.object(orchestrator, "run_ingestion_pipeline") as mock_ingest:
                result = await orchestrator.run_full_pipeline()

        assert result["success"] is False  # No documents to process
        assert result["scraping"] == scraping_result
        assert result["ingestion"]["skipped"] is True
        assert result["ingestion"]["reason"] == "no_documents_scraped"

        mock_scrape.assert_called_once()
        mock_ingest.assert_not_called()  # Should not call ingestion

    @pytest.mark.asyncio
    async def test_get_pipeline_status(self, orchestrator):
        """Test getting pipeline status."""
        # Mock storage methods
        with patch.object(orchestrator.storage, "list_available_batches") as mock_batches:
            mock_batches.return_value = ["2025-01-20", "2025-01-19"]

            with patch.object(orchestrator.ingestion, "list_ingested_batches") as mock_ingested:
                mock_ingested.return_value = [
                    {"batch_date": "2025-01-20", "success": True},
                    {"batch_date": "2025-01-19", "success": False},
                ]

                status = await orchestrator.get_pipeline_status()

        assert "artifacts_path" in status
        assert "current_batch_date" in status
        assert status["available_batches"] == ["2025-01-20", "2025-01-19"]
        assert (
            len(status["scrapers"]) == 4
        )  # redis_docs, redis_kb, redis_runbooks, runbook_generator
        assert status["ingestion"]["batches_ingested"] == 1  # Only successful ones
        assert len(status["ingestion"]["recent_batches"]) == 2

    @pytest.mark.asyncio
    async def test_get_pipeline_status_with_ingestion_error(self, orchestrator):
        """Test pipeline status handles ingestion errors."""
        with patch.object(orchestrator.storage, "list_available_batches") as mock_batches:
            mock_batches.return_value = ["2025-01-20"]

            with patch.object(orchestrator.ingestion, "list_ingested_batches") as mock_ingested:
                mock_ingested.side_effect = Exception("Ingestion status error")

                status = await orchestrator.get_pipeline_status()

        assert "error" in status["ingestion"]
        assert "scrapers" in status
        assert status["available_batches"] == ["2025-01-20"]

    @pytest.mark.asyncio
    async def test_cleanup_old_batches(self, orchestrator, tmp_path):
        """Test cleanup of old batch directories."""
        from datetime import datetime, timedelta

        # Create some batch directories with different dates relative to today
        today = datetime.now()
        old_date = (today - timedelta(days=45)).strftime("%Y-%m-%d")  # More than 30 days old
        recent_date = (today - timedelta(days=15)).strftime("%Y-%m-%d")  # Recent
        current_date = orchestrator.storage.current_date

        # Create directories
        (tmp_path / old_date).mkdir(exist_ok=True)
        (tmp_path / recent_date).mkdir(exist_ok=True)
        (tmp_path / current_date).mkdir(exist_ok=True)

        with patch.object(orchestrator.storage, "list_available_batches") as mock_batches:
            mock_batches.return_value = [old_date, recent_date, current_date]

            result = await orchestrator.cleanup_old_batches(keep_days=30)

        assert old_date in result["batches_removed"]
        assert recent_date in result["batches_kept"]
        assert current_date in result["batches_kept"]
        assert len(result["errors"]) == 0

        # Verify old directory was actually removed
        assert not (tmp_path / old_date).exists()
        assert (tmp_path / recent_date).exists()

    @pytest.mark.asyncio
    async def test_cleanup_old_batches_with_errors(self, orchestrator, tmp_path):
        """Test cleanup handles removal errors gracefully."""
        old_date = "2024-12-20"

        # Create a directory but simulate permission error
        (tmp_path / old_date).mkdir()

        with patch.object(orchestrator.storage, "list_available_batches") as mock_batches:
            mock_batches.return_value = [old_date]

            # Mock shutil.rmtree to raise an error
            with patch("shutil.rmtree") as mock_rmtree:
                mock_rmtree.side_effect = OSError("Permission denied")

                result = await orchestrator.cleanup_old_batches(keep_days=30)

        assert old_date not in result["batches_removed"]
        assert len(result["errors"]) == 1
        assert "Permission denied" in result["errors"][0]


class TestConvenienceFunctions:
    """Test convenience functions for CLI usage."""

    @pytest.mark.asyncio
    async def test_run_scraping_only(self, tmp_path):
        """Test run_scraping_only convenience function."""
        from redis_sre_agent.pipelines.orchestrator import run_scraping_only

        with patch("redis_sre_agent.pipelines.orchestrator.PipelineOrchestrator") as mock_class:
            mock_orchestrator = AsyncMock()
            mock_result = {"success": True, "total_documents": 5}
            mock_orchestrator.run_scraping_pipeline.return_value = mock_result
            mock_class.return_value = mock_orchestrator

            result = await run_scraping_only(str(tmp_path))

            assert result == mock_result
            mock_class.assert_called_once_with(str(tmp_path), None)
            mock_orchestrator.run_scraping_pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_ingestion_only(self, tmp_path):
        """Test run_ingestion_only convenience function."""
        from redis_sre_agent.pipelines.orchestrator import run_ingestion_only

        batch_date = "2025-01-20"

        with patch("redis_sre_agent.pipelines.orchestrator.PipelineOrchestrator") as mock_class:
            mock_orchestrator = AsyncMock()
            mock_result = {"success": True, "documents_processed": 10}
            mock_orchestrator.run_ingestion_pipeline.return_value = mock_result
            mock_class.return_value = mock_orchestrator

            result = await run_ingestion_only(batch_date, str(tmp_path))

            assert result == mock_result
            mock_class.assert_called_once_with(str(tmp_path), None)
            mock_orchestrator.run_ingestion_pipeline.assert_called_once_with(batch_date)

    @pytest.mark.asyncio
    async def test_run_full_pipeline(self, tmp_path):
        """Test run_full_pipeline convenience function."""
        from redis_sre_agent.pipelines.orchestrator import run_full_pipeline

        with patch("redis_sre_agent.pipelines.orchestrator.PipelineOrchestrator") as mock_class:
            mock_orchestrator = AsyncMock()
            mock_result = {"success": True, "scraping": {}, "ingestion": {}}
            mock_orchestrator.run_full_pipeline.return_value = mock_result
            mock_class.return_value = mock_orchestrator

            result = await run_full_pipeline(str(tmp_path))

            assert result == mock_result
            mock_class.assert_called_once_with(str(tmp_path), None)
            mock_orchestrator.run_full_pipeline.assert_called_once()

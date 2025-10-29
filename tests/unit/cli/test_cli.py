"""Tests for CLI pipeline commands."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.pipeline import pipeline


@pytest.fixture
def cli_runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_artifacts_path():
    """Temporary artifacts directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_orchestrator():
    """Mock PipelineOrchestrator."""
    with patch("redis_sre_agent.cli.pipeline.PipelineOrchestrator") as mock_class:
        mock_instance = AsyncMock()
        mock_class.return_value = mock_instance
        yield mock_instance


class TestPipelineScrapeCLI:
    """Test pipeline scrape command."""

    def test_scrape_command_success(self, cli_runner, temp_artifacts_path, mock_orchestrator):
        """Test successful scrape command."""
        # Mock successful scraping results
        mock_orchestrator.run_scraping_pipeline.return_value = {
            "batch_date": "2025-08-20",
            "total_documents": 15,
            "scrapers_run": ["redis_docs", "redis_runbooks"],
            "scraper_results": {
                "redis_docs": {"documents_scraped": 10},
                "redis_runbooks": {"documents_scraped": 5},
            },
        }

        result = cli_runner.invoke(pipeline, ["scrape", "--artifacts-path", temp_artifacts_path])

        assert result.exit_code == 0
        assert "Starting scraping pipeline" in result.output
        assert "Scraping completed" in result.output
        assert "Total documents: 15" in result.output
        assert "redis_docs: 10 documents" in result.output

    def test_scrape_command_with_scrapers_filter(
        self, cli_runner, temp_artifacts_path, mock_orchestrator
    ):
        """Test scrape command with specific scrapers."""
        mock_orchestrator.run_scraping_pipeline.return_value = {
            "batch_date": "2025-08-20",
            "total_documents": 5,
            "scrapers_run": ["redis_docs"],
            "scraper_results": {"redis_docs": {"documents_scraped": 5}},
        }

        result = cli_runner.invoke(
            pipeline,
            ["scrape", "--artifacts-path", temp_artifacts_path, "--scrapers", "redis_docs"],
        )

        assert result.exit_code == 0
        mock_orchestrator.run_scraping_pipeline.assert_called_once_with(["redis_docs"])

    def test_scrape_command_with_error(self, cli_runner, temp_artifacts_path, mock_orchestrator):
        """Test scrape command with scraper error."""
        mock_orchestrator.run_scraping_pipeline.return_value = {
            "batch_date": "2025-08-20",
            "total_documents": 5,
            "scrapers_run": ["redis_docs", "redis_runbooks"],
            "scraper_results": {
                "redis_docs": {"documents_scraped": 5},
                "redis_runbooks": {"error": "Failed to connect"},
            },
        }

        result = cli_runner.invoke(pipeline, ["scrape", "--artifacts-path", temp_artifacts_path])

        assert result.exit_code == 0
        assert "redis_runbooks: Failed to connect" in result.output

    def test_scrape_command_exception(self, cli_runner, temp_artifacts_path, mock_orchestrator):
        """Test scrape command with exception."""
        mock_orchestrator.run_scraping_pipeline.side_effect = Exception("Connection failed")

        result = cli_runner.invoke(pipeline, ["scrape", "--artifacts-path", temp_artifacts_path])

        assert result.exit_code != 0
        assert "Scraping failed: Connection failed" in result.output


class TestPipelineIngestCLI:
    """Test pipeline ingest command."""

    def test_ingest_command_success(self, cli_runner, temp_artifacts_path, mock_orchestrator):
        """Test successful ingest command."""
        mock_orchestrator.run_ingestion_pipeline.return_value = {
            "batch_date": "2025-08-20",
            "documents_processed": 15,
            "chunks_created": 45,
            "chunks_indexed": 45,
            "categories_processed": {
                "monitoring": {"documents_processed": 10, "chunks_indexed": 30, "errors": []},
                "troubleshooting": {
                    "documents_processed": 5,
                    "chunks_indexed": 15,
                    "errors": ["Failed to process doc X"],
                },
            },
        }

        result = cli_runner.invoke(pipeline, ["ingest", "--artifacts-path", temp_artifacts_path])

        assert result.exit_code == 0
        assert "Starting ingestion pipeline" in result.output
        assert "Ingestion completed" in result.output
        assert "Documents processed: 15" in result.output
        assert "Chunks indexed: 45" in result.output
        assert "monitoring: 10 docs, 30 chunks" in result.output
        assert "1 errors" in result.output

    def test_ingest_command_with_batch_date(
        self, cli_runner, temp_artifacts_path, mock_orchestrator
    ):
        """Test ingest command with specific batch date."""
        mock_orchestrator.run_ingestion_pipeline.return_value = {
            "batch_date": "2025-08-19",
            "documents_processed": 10,
            "chunks_created": 30,
            "chunks_indexed": 30,
            "categories_processed": {},
        }

        result = cli_runner.invoke(
            pipeline,
            ["ingest", "--batch-date", "2025-08-19", "--artifacts-path", temp_artifacts_path],
        )

        assert result.exit_code == 0
        mock_orchestrator.run_ingestion_pipeline.assert_called_once_with("2025-08-19")

    def test_ingest_command_exception(self, cli_runner, temp_artifacts_path, mock_orchestrator):
        """Test ingest command with exception."""
        mock_orchestrator.run_ingestion_pipeline.side_effect = Exception("Redis connection failed")

        result = cli_runner.invoke(pipeline, ["ingest", "--artifacts-path", temp_artifacts_path])

        assert result.exit_code != 0
        assert "Ingestion failed: Redis connection failed" in result.output


class TestPipelineFullCLI:
    """Test pipeline full command."""

    def test_full_command_success(self, cli_runner, temp_artifacts_path, mock_orchestrator):
        """Test successful full pipeline command."""
        mock_orchestrator.run_full_pipeline.return_value = {
            "batch_date": "2025-08-20",
            "scraping": {
                "total_documents": 15,
                "scraper_results": {
                    "redis_docs": {"documents_scraped": 10},
                    "redis_runbooks": {"documents_scraped": 5},
                },
            },
            "ingestion": {"documents_processed": 15, "chunks_indexed": 45, "skipped": False},
        }

        result = cli_runner.invoke(pipeline, ["full", "--artifacts-path", temp_artifacts_path])

        assert result.exit_code == 0
        assert "Starting full pipeline" in result.output
        assert "Full pipeline completed" in result.output
        assert "Scraping: 15 documents" in result.output
        assert "Ingestion: 15 docs → 45 chunks" in result.output

    def test_full_command_with_skipped_ingestion(
        self, cli_runner, temp_artifacts_path, mock_orchestrator
    ):
        """Test full pipeline with skipped ingestion."""
        mock_orchestrator.run_full_pipeline.return_value = {
            "batch_date": "2025-08-20",
            "scraping": {"total_documents": 0, "scraper_results": {}},
            "ingestion": {"skipped": True, "reason": "No new documents to process"},
        }

        result = cli_runner.invoke(pipeline, ["full", "--artifacts-path", temp_artifacts_path])

        assert result.exit_code == 0
        assert "Ingestion: Skipped (No new documents to process)" in result.output


class TestPipelineStatusCLI:
    """Test pipeline status command."""

    def test_status_command_success(self, cli_runner, temp_artifacts_path, mock_orchestrator):
        """Test successful status command."""
        mock_orchestrator.get_pipeline_status.return_value = {
            "artifacts_path": temp_artifacts_path,
            "current_batch_date": "2025-08-20",
            "available_batches": ["2025-08-18", "2025-08-19", "2025-08-20"],
            "scrapers": {
                "redis_docs": {"source": "https://redis.io/docs"},
                "redis_runbooks": {"source": "internal_runbooks"},
            },
            "ingestion": {"batches_ingested": 2},
        }

        result = cli_runner.invoke(pipeline, ["status", "--artifacts-path", temp_artifacts_path])

        assert result.exit_code == 0
        assert "Pipeline Status" in result.output
        assert "Current batch: 2025-08-20" in result.output
        assert "Available batches: 3" in result.output
        assert "redis_docs: https://redis.io/docs" in result.output
        assert "Ingested batches: 2" in result.output


class TestPipelineShowBatchCLI:
    """Test pipeline show-batch command."""

    def test_show_batch_success(self, cli_runner, temp_artifacts_path):
        """Test successful show-batch command."""
        # Create mock batch manifest
        batch_path = Path(temp_artifacts_path) / "2025-08-20"
        batch_path.mkdir(parents=True, exist_ok=True)

        manifest_data = {
            "created_at": "2025-08-20T10:00:00Z",
            "total_documents": 15,
            "categories": {"monitoring": 10, "troubleshooting": 5},
            "document_types": {"runbook": 8, "alert": 7},
        }

        ingestion_data = {"success": True, "documents_processed": 15, "chunks_indexed": 45}

        with open(batch_path / "manifest.json", "w") as f:
            json.dump(manifest_data, f)

        with open(batch_path / "ingestion_manifest.json", "w") as f:
            json.dump(ingestion_data, f)

        with patch("redis_sre_agent.pipelines.scraper.base.ArtifactStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.get_batch_manifest.return_value = manifest_data
            mock_storage_class.return_value = mock_storage

            result = cli_runner.invoke(
                pipeline,
                [
                    "show-batch",
                    "--batch-date",
                    "2025-08-20",
                    "--artifacts-path",
                    temp_artifacts_path,
                ],
            )

        assert result.exit_code == 0
        assert "Batch Details: 2025-08-20" in result.output
        assert "Total documents: 15" in result.output
        assert "monitoring: 10 documents" in result.output
        assert "Status: ✅ Success" in result.output
        assert "Indexed: 45 chunks" in result.output

    def test_show_batch_no_manifest(self, cli_runner, temp_artifacts_path):
        """Test show-batch with missing manifest."""
        with patch("redis_sre_agent.pipelines.scraper.base.ArtifactStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.get_batch_manifest.return_value = None
            mock_storage_class.return_value = mock_storage

            result = cli_runner.invoke(
                pipeline,
                [
                    "show-batch",
                    "--batch-date",
                    "2025-08-20",
                    "--artifacts-path",
                    temp_artifacts_path,
                ],
            )

        assert result.exit_code == 0
        assert "No manifest found for batch 2025-08-20" in result.output


class TestPipelineCleanupCLI:
    """Test pipeline cleanup command."""

    def test_cleanup_command_success(self, cli_runner, temp_artifacts_path, mock_orchestrator):
        """Test successful cleanup command."""
        mock_orchestrator.cleanup_old_batches.return_value = {
            "cutoff_date": "2025-07-21",
            "batches_removed": ["2025-07-20", "2025-07-19"],
            "batches_kept": ["2025-08-20", "2025-08-19"],
            "errors": [],
        }

        result = cli_runner.invoke(
            pipeline,
            ["cleanup", "--keep-days", "30", "--artifacts-path", temp_artifacts_path],
            input="y\n",
        )

        assert result.exit_code == 0
        assert "Cleaning up batches older than 30 days" in result.output
        assert "Cleanup completed" in result.output
        assert "Batches removed: 2" in result.output
        assert "2025-07-20" in result.output

    def test_cleanup_command_with_errors(self, cli_runner, temp_artifacts_path, mock_orchestrator):
        """Test cleanup command with errors."""
        mock_orchestrator.cleanup_old_batches.return_value = {
            "cutoff_date": "2025-07-21",
            "batches_removed": ["2025-07-20"],
            "batches_kept": ["2025-08-20"],
            "errors": ["Failed to remove 2025-07-19: Permission denied"],
        }

        result = cli_runner.invoke(
            pipeline, ["cleanup", "--artifacts-path", temp_artifacts_path], input="y\n"
        )

        assert result.exit_code == 0
        assert "Permission denied" in result.output


class TestPipelineRunbooksCLI:
    """Test pipeline runbooks command."""

    def test_runbooks_list_urls(self, cli_runner, temp_artifacts_path, mock_orchestrator):
        """Test runbooks command with list-urls flag."""
        mock_generator = MagicMock()
        mock_generator.get_configured_urls.return_value = [
            "https://example.com/runbook1",
            "https://example.com/runbook2",
        ]
        mock_orchestrator.scrapers = {"runbook_generator": mock_generator}

        result = cli_runner.invoke(
            pipeline, ["runbooks", "--list-urls", "--artifacts-path", temp_artifacts_path]
        )

        assert result.exit_code == 0
        assert "Currently configured runbook URLs" in result.output
        # The actual URLs might be from configuration, so just check structure
        assert "1." in result.output and "2." in result.output

    def test_runbooks_test_url_failure(self, cli_runner, temp_artifacts_path):
        """Test runbooks command with test-url that fails."""
        result = cli_runner.invoke(
            pipeline,
            [
                "runbooks",
                "--test-url",
                "https://nonexistent-url-for-testing.invalid",
                "--artifacts-path",
                temp_artifacts_path,
            ],
        )

        assert result.exit_code == 0
        assert "Testing URL extraction" in result.output
        assert "Failed:" in result.output

    def test_runbooks_add_url_failure(self, cli_runner, temp_artifacts_path):
        """Test runbooks command with URL addition that fails."""
        result = cli_runner.invoke(
            pipeline,
            [
                "runbooks",
                "--url",
                "https://nonexistent-url-for-testing.invalid",
                "--artifacts-path",
                temp_artifacts_path,
            ],
        )

        assert result.exit_code == 0
        assert "Adding URL and generating runbook" in result.output
        assert "Failed to generate runbook" in result.output

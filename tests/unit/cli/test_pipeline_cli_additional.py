"""Additional CLI coverage for pipeline commands."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.pipeline import pipeline


@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture
def temp_artifacts_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_orchestrator():
    with patch("redis_sre_agent.cli.pipeline.PipelineOrchestrator") as mock_class:
        mock_instance = AsyncMock()
        mock_class.return_value = mock_instance
        yield mock_instance


def test_full_command_additional_branches(cli_runner, temp_artifacts_path, mock_orchestrator):
    mock_orchestrator.run_full_pipeline.return_value = {
        "batch_date": "2025-08-20",
        "scraping": {
            "total_documents": 2,
            "scraper_results": {
                "redis_docs": {"documents_scraped": 2},
                "redis_kb": {"error": "failed"},
            },
        },
        "ingestion": {"documents_processed": 2, "chunks_indexed": 4},
    }

    result = cli_runner.invoke(
        pipeline,
        [
            "full",
            "--artifacts-path",
            temp_artifacts_path,
            "--scrapers",
            "redis_docs, redis_kb",
        ],
    )

    assert result.exit_code == 0
    mock_orchestrator.run_full_pipeline.assert_called_once_with(["redis_docs", "redis_kb"])
    assert "redis_kb: failed" in result.output

    mock_orchestrator.run_full_pipeline.side_effect = Exception("full boom")
    failed = cli_runner.invoke(pipeline, ["full", "--artifacts-path", temp_artifacts_path])
    assert failed.exit_code != 0
    assert "Full pipeline failed: full boom" in failed.output


def test_status_exception_and_show_batch_not_ingested(
    cli_runner, temp_artifacts_path, mock_orchestrator
):
    mock_orchestrator.get_pipeline_status.side_effect = Exception("status boom")
    result = cli_runner.invoke(pipeline, ["status", "--artifacts-path", temp_artifacts_path])
    assert result.exit_code != 0
    assert "Status check failed: status boom" in result.output

    batch_path = Path(temp_artifacts_path) / "2025-08-20"
    batch_path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": "2025-08-20T10:00:00Z",
        "total_documents": 1,
        "categories": {"shared": 1},
        "document_types": {"knowledge": 1},
    }

    with patch("redis_sre_agent.pipelines.scraper.base.ArtifactStorage") as mock_storage_class:
        mock_storage = MagicMock()
        mock_storage.get_batch_manifest.return_value = manifest
        mock_storage_class.return_value = mock_storage

        show = cli_runner.invoke(
            pipeline,
            ["show-batch", "--batch-date", "2025-08-20", "--artifacts-path", temp_artifacts_path],
        )

    assert show.exit_code == 0
    assert "Ingestion: ⏳ Not ingested yet" in show.output


def test_cleanup_and_runbooks_additional_branches(cli_runner, temp_artifacts_path):
    with patch("redis_sre_agent.cli.pipeline.PipelineOrchestrator") as orchestrator_class:
        cleanup_orchestrator = AsyncMock()
        cleanup_orchestrator.cleanup_old_batches.side_effect = Exception("cleanup boom")
        orchestrator_class.return_value = cleanup_orchestrator

        result = cli_runner.invoke(
            pipeline,
            ["cleanup", "--artifacts-path", temp_artifacts_path],
            input="y\n",
        )
        assert result.exit_code != 0
        assert "Cleanup failed: cleanup boom" in result.output

    with patch("redis_sre_agent.pipelines.orchestrator.PipelineOrchestrator") as orchestrator_class:
        doc = MagicMock(title="Generated", category="shared", severity="high", content="x" * 10)

        class FakeGenerator:
            def __init__(self, storage=None, config=None):
                self.storage = storage
                self.config = config or {"existing": True}

            def get_configured_urls(self):
                return ["https://example.com"]

            async def test_url_extraction(self, url):
                return {
                    "success": True,
                    "content_length": 123,
                    "source_type": "html",
                    "content_preview": "preview text",
                }

            async def add_runbook_url(self, url):
                return False

            async def scrape(self):
                return [doc]

            async def run_scraping_job(self):
                return {
                    "documents_scraped": 2,
                    "documents_saved": 2,
                    "batch_date": "2025-08-20",
                    "categories": {"shared": 2},
                }

        generator = FakeGenerator()
        orchestrator = MagicMock(scrapers={"runbook_generator": generator})
        orchestrator_class.return_value = orchestrator

        with patch("redis_sre_agent.pipelines.scraper.base.ArtifactStorage") as storage_class:
            storage = MagicMock()
            storage.save_document.return_value = "/tmp/generated.json"
            storage_class.return_value = storage

            success = cli_runner.invoke(
                pipeline,
                [
                    "runbooks",
                    "--test-url",
                    "https://example.com",
                    "--artifacts-path",
                    temp_artifacts_path,
                ],
            )
            assert success.exit_code == 0
            assert "Content length: 123 chars" in success.output

            add = cli_runner.invoke(
                pipeline,
                [
                    "runbooks",
                    "--url",
                    "https://example.com",
                    "--artifacts-path",
                    temp_artifacts_path,
                ],
            )
            assert add.exit_code == 0
            assert "URL already in configuration" in add.output
            assert "Generated runbook: Generated" in add.output
            assert "Saved to: /tmp/generated.json" in add.output

        default = cli_runner.invoke(pipeline, ["runbooks", "--artifacts-path", temp_artifacts_path])
        assert default.exit_code == 0
        assert "Documents generated: 2" in default.output

        generator.run_scraping_job = AsyncMock(side_effect=Exception("runbooks boom"))
        failed = cli_runner.invoke(pipeline, ["runbooks", "--artifacts-path", temp_artifacts_path])
        assert failed.exit_code != 0
        assert "Runbook generation failed: runbooks boom" in failed.output


def test_prepare_sources_command_branches(cli_runner, temp_artifacts_path, tmp_path):
    missing = cli_runner.invoke(
        pipeline,
        [
            "prepare-sources",
            "--source-dir",
            str(tmp_path / "missing"),
            "--artifacts-path",
            temp_artifacts_path,
        ],
    )
    assert missing.exit_code == 0
    assert "Source directory does not exist" in missing.output

    source_dir = tmp_path / "source_documents"
    source_dir.mkdir()
    invalid = cli_runner.invoke(
        pipeline,
        [
            "prepare-sources",
            "--source-dir",
            str(source_dir),
            "--batch-date",
            "2025-99-99",
            "--artifacts-path",
            temp_artifacts_path,
        ],
    )
    assert invalid.exit_code == 0
    assert "Invalid batch date format" in invalid.output

    no_markdown = cli_runner.invoke(
        pipeline,
        [
            "prepare-sources",
            "--source-dir",
            str(source_dir),
            "--artifacts-path",
            temp_artifacts_path,
        ],
    )
    assert no_markdown.exit_code == 0
    assert "No markdown files found" in no_markdown.output

    doc_file = source_dir / "doc.md"
    doc_file.write_text("# Doc", encoding="utf-8")

    with (
        patch("redis_sre_agent.pipelines.scraper.base.ArtifactStorage") as storage_class,
        patch("redis_sre_agent.pipelines.ingestion.processor.IngestionPipeline") as pipeline_class,
    ):
        storage = MagicMock()
        storage.base_path = Path(temp_artifacts_path)
        storage.current_date = "2025-08-20"
        storage.current_batch_path = Path(temp_artifacts_path) / "2025-08-20"
        storage_class.return_value = storage

        ingest_pipeline = AsyncMock()
        ingest_pipeline.prepare_source_artifacts.return_value = 1
        ingest_pipeline.ingest_prepared_batch.return_value = [
            {
                "status": "success",
                "chunks_indexed": 3,
                "source_document_changes": {
                    "added": 1,
                    "updated": 1,
                    "deleted": 0,
                    "unchanged": 0,
                    "files": [
                        {"action": "add", "path": "shared/new.md"},
                        {"action": "update", "path": "shared/current.md"},
                    ],
                },
            },
            {"status": "error", "error": "bad doc"},
        ]
        pipeline_class.return_value = ingest_pipeline

        prepare_only = cli_runner.invoke(
            pipeline,
            [
                "prepare-sources",
                "--source-dir",
                str(source_dir),
                "--prepare-only",
                "--artifacts-path",
                temp_artifacts_path,
            ],
        )
        assert prepare_only.exit_code == 0
        assert "Artifacts prepared but not ingested" in prepare_only.output

        full = cli_runner.invoke(
            pipeline,
            [
                "prepare-sources",
                "--source-dir",
                str(source_dir),
                "--batch-date",
                "2025-08-21",
                "--verbose",
                "--artifacts-path",
                temp_artifacts_path,
            ],
        )
        assert full.exit_code == 0
        assert "Batch date: 2025-08-21" in full.output
        assert "Successfully ingested: 1 documents" in full.output
        assert "Failed to ingest: 1 documents" in full.output
        assert "add: shared/new.md" in full.output
        assert "update: shared/current.md" in full.output

        ingest_pipeline.prepare_source_artifacts.side_effect = Exception("prepare boom")
        failed = cli_runner.invoke(
            pipeline,
            [
                "prepare-sources",
                "--source-dir",
                str(source_dir),
                "--artifacts-path",
                temp_artifacts_path,
            ],
        )
        assert failed.exit_code != 0
        assert "Source preparation failed: prepare boom" in failed.output

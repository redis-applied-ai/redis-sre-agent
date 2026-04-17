"""Tests for task-backed pipeline execution helpers."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.pipeline_execution_helpers import (
    _build_pipeline_task_message,
    get_redis_url,
    queue_pipeline_operation_task,
    run_pipeline_operation_helper,
)


class TestRunPipelineOperationHelper:
    """Test pipeline operation execution helpers."""

    @pytest.mark.asyncio
    async def test_run_scrape_operation(self):
        """Scrape operation should build scraper config and run the orchestrator."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.run_scraping_pipeline = AsyncMock(
            return_value={"batch_date": "2026-03-25", "total_documents": 4, "success": True}
        )
        emitter = AsyncMock()

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.PipelineOrchestrator",
            return_value=mock_orchestrator,
        ) as mock_cls:
            result = await run_pipeline_operation_helper(
                operation="scrape",
                artifacts_path="/tmp/artifacts",
                scrapers=["redis_docs"],
                latest_only=True,
                docs_path="/tmp/docs",
                progress_emitter=emitter,
            )

        assert result["operation"] == "scrape"
        assert result["total_documents"] == 4
        mock_cls.assert_called_once_with(
            "/tmp/artifacts",
            {
                "redis_docs": {"latest_only": True},
                "redis_docs_local": {"latest_only": True, "docs_repo_path": "/tmp/docs"},
            },
            scrapers=["redis_docs"],
        )
        mock_orchestrator.run_scraping_pipeline.assert_awaited_once_with(
            ["redis_docs"], progress_callback=ANY
        )
        assert emitter.emit.await_count == 2

    @pytest.mark.asyncio
    async def test_run_ingest_operation(self):
        """Ingest operation should pass latest-only config and batch date."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.run_ingestion_pipeline = AsyncMock(
            return_value={"batch_date": "2026-03-25", "chunks_indexed": 12, "success": True}
        )

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.PipelineOrchestrator",
            return_value=mock_orchestrator,
        ) as mock_cls:
            result = await run_pipeline_operation_helper(
                operation="ingest",
                batch_date="2026-03-25",
                artifacts_path="/tmp/artifacts",
                latest_only=True,
            )

        assert result["operation"] == "ingest"
        assert result["chunks_indexed"] == 12
        mock_cls.assert_called_once_with(
            "/tmp/artifacts",
            {"ingestion": {"latest_only": True}},
        )
        mock_orchestrator.run_ingestion_pipeline.assert_awaited_once_with(
            "2026-03-25", progress_callback=ANY
        )

    @pytest.mark.asyncio
    async def test_run_full_operation(self):
        """Full operation should configure scrape and ingest settings."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.run_full_pipeline = AsyncMock(
            return_value={"batch_date": "2026-03-25", "success": True}
        )

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.PipelineOrchestrator",
            return_value=mock_orchestrator,
        ) as mock_cls:
            result = await run_pipeline_operation_helper(
                operation="full",
                artifacts_path="/tmp/artifacts",
                scrapers=["redis_docs_local"],
                latest_only=True,
                docs_path="/tmp/docs",
            )

        assert result["operation"] == "full"
        mock_cls.assert_called_once_with(
            "/tmp/artifacts",
            {
                "redis_docs": {"latest_only": True},
                "redis_docs_local": {"latest_only": True, "docs_repo_path": "/tmp/docs"},
                "ingestion": {"latest_only": True},
            },
            scrapers=["redis_docs_local"],
        )
        mock_orchestrator.run_full_pipeline.assert_awaited_once_with(
            ["redis_docs_local"], progress_callback=ANY
        )

    @pytest.mark.asyncio
    async def test_run_cleanup_operation(self):
        """Cleanup operation should run through the orchestrator."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.cleanup_old_batches = AsyncMock(
            return_value={"cutoff_date": "2026-03-01", "batches_removed": ["2026-02-01"]}
        )

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.PipelineOrchestrator",
            return_value=mock_orchestrator,
        ) as mock_cls:
            result = await run_pipeline_operation_helper(
                operation="cleanup",
                artifacts_path="/tmp/artifacts",
                keep_days=14,
            )

        assert result["operation"] == "cleanup"
        assert result["batches_removed"] == ["2026-02-01"]
        mock_cls.assert_called_once_with("/tmp/artifacts")
        mock_orchestrator.cleanup_old_batches.assert_awaited_once_with(14)

    @pytest.mark.asyncio
    async def test_run_runbooks_list_urls(self):
        """Runbooks list mode should return configured URLs directly."""
        mock_generator = MagicMock()
        mock_generator.get_configured_urls.return_value = ["https://example.com/runbook"]
        mock_orchestrator = MagicMock(scrapers={"runbook_generator": mock_generator})

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.PipelineOrchestrator",
            return_value=mock_orchestrator,
        ) as mock_cls:
            result = await run_pipeline_operation_helper(
                operation="runbooks",
                artifacts_path="/tmp/artifacts",
                list_urls=True,
            )

        assert result == {
            "operation": "runbooks",
            "mode": "list_urls",
            "configured_urls": ["https://example.com/runbook"],
        }
        mock_cls.assert_called_once_with("/tmp/artifacts", scrapers=["runbook_generator"])

    @pytest.mark.asyncio
    async def test_run_runbooks_test_url(self):
        """Runbooks test mode should proxy URL extraction results."""
        mock_generator = MagicMock()
        mock_generator.test_url_extraction = AsyncMock(
            return_value={"url": "https://example.com", "success": True}
        )
        mock_orchestrator = MagicMock(scrapers={"runbook_generator": mock_generator})

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.PipelineOrchestrator",
            return_value=mock_orchestrator,
        ):
            result = await run_pipeline_operation_helper(
                operation="runbooks",
                artifacts_path="/tmp/artifacts",
                test_url="https://example.com",
            )

        assert result == {
            "operation": "runbooks",
            "mode": "test_url",
            "url": "https://example.com",
            "result": {"url": "https://example.com", "success": True},
        }
        mock_generator.test_url_extraction.assert_awaited_once_with("https://example.com")

    @pytest.mark.asyncio
    async def test_run_runbooks_list_urls_does_not_emit_completion_on_failure(self):
        """List mode should not report completion if URL enumeration raises."""
        emitter = AsyncMock()
        mock_generator = MagicMock()
        mock_generator.get_configured_urls.side_effect = RuntimeError("boom")
        mock_orchestrator = MagicMock(scrapers={"runbook_generator": mock_generator})

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.PipelineOrchestrator",
            return_value=mock_orchestrator,
        ):
            with pytest.raises(RuntimeError, match="boom"):
                await run_pipeline_operation_helper(
                    operation="runbooks",
                    artifacts_path="/tmp/artifacts",
                    list_urls=True,
                    progress_emitter=emitter,
                )

        progress_events = [call.args[1] for call in emitter.emit.await_args_list]
        assert "pipeline_complete" not in progress_events

    @pytest.mark.asyncio
    async def test_run_runbooks_test_url_does_not_emit_completion_on_failure(self):
        """Test mode should not report completion if extraction fails."""
        emitter = AsyncMock()
        mock_generator = MagicMock()
        mock_generator.test_url_extraction = AsyncMock(side_effect=RuntimeError("boom"))
        mock_orchestrator = MagicMock(scrapers={"runbook_generator": mock_generator})

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.PipelineOrchestrator",
            return_value=mock_orchestrator,
        ):
            with pytest.raises(RuntimeError, match="boom"):
                await run_pipeline_operation_helper(
                    operation="runbooks",
                    artifacts_path="/tmp/artifacts",
                    test_url="https://example.com",
                    progress_emitter=emitter,
                )

        progress_events = [call.args[1] for call in emitter.emit.await_args_list]
        assert "pipeline_complete" not in progress_events

    @pytest.mark.asyncio
    async def test_run_runbooks_single_url(self):
        """Runbooks single-url mode should add the URL and run a dedicated job."""
        primary_generator = MagicMock()
        primary_generator.add_runbook_url = AsyncMock(return_value=True)
        primary_generator.config = {"runbook_urls": ["https://default.example"]}
        primary_orchestrator = MagicMock(scrapers={"runbook_generator": primary_generator})

        single_generator = MagicMock()
        single_generator.run_scraping_job = AsyncMock(
            return_value={"documents_scraped": 2, "documents_saved": 2}
        )
        single_orchestrator = MagicMock(scrapers={"runbook_generator": single_generator})

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.PipelineOrchestrator",
            side_effect=[primary_orchestrator, single_orchestrator],
        ) as mock_cls:
            result = await run_pipeline_operation_helper(
                operation="runbooks",
                artifacts_path="/tmp/artifacts",
                url="https://example.com/runbook",
            )

        assert result == {
            "operation": "runbooks",
            "mode": "single_url",
            "url": "https://example.com/runbook",
            "url_added": True,
            "documents_scraped": 2,
            "documents_saved": 2,
        }
        primary_generator.add_runbook_url.assert_awaited_once_with("https://example.com/runbook")
        assert mock_cls.call_count == 2
        single_generator.run_scraping_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_runbooks_default_generation(self):
        """Runbooks default mode should process configured URLs."""
        mock_generator = MagicMock()
        mock_generator.run_scraping_job = AsyncMock(return_value={"documents_scraped": 3})
        mock_orchestrator = MagicMock(scrapers={"runbook_generator": mock_generator})

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.PipelineOrchestrator",
            return_value=mock_orchestrator,
        ):
            result = await run_pipeline_operation_helper(
                operation="runbooks",
                artifacts_path="/tmp/artifacts",
            )

        assert result == {
            "operation": "runbooks",
            "mode": "configured_urls",
            "documents_scraped": 3,
        }
        mock_generator.run_scraping_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_prepare_sources_prepare_only(self, tmp_path):
        """Prepare-sources mode should prepare artifacts without ingesting them."""
        source_dir = tmp_path / "source_documents"
        source_dir.mkdir()
        (source_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
        (source_dir / "README.md").write_text("# Ignore me\n", encoding="utf-8")

        mock_pipeline = MagicMock()
        mock_pipeline.prepare_source_artifacts = AsyncMock(return_value=1)
        mock_pipeline.ingest_prepared_batch = AsyncMock()

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.IngestionPipeline",
            return_value=mock_pipeline,
        ):
            result = await run_pipeline_operation_helper(
                operation="prepare_sources",
                source_dir=str(source_dir),
                batch_date="2026-03-25",
                prepare_only=True,
                artifacts_path=str(tmp_path / "artifacts"),
            )

        assert result["operation"] == "prepare_sources"
        assert result["prepared_count"] == 1
        assert result["batch_date"] == "2026-03-25"
        assert result["ingestion"] == {"performed": False}
        assert result["source_documents"] == ["guide.md"]
        mock_pipeline.ingest_prepared_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_prepare_sources_with_ingestion(self, tmp_path):
        """Prepare-sources should summarize ingestion results when requested."""
        source_dir = tmp_path / "source_documents"
        source_dir.mkdir()
        (source_dir / "a.md").write_text("# A\n", encoding="utf-8")
        (source_dir / "nested").mkdir()
        (source_dir / "nested" / "b.md").write_text("# B\n", encoding="utf-8")

        mock_pipeline = MagicMock()
        mock_pipeline.prepare_source_artifacts = AsyncMock(return_value=2)
        mock_pipeline.ingest_prepared_batch = AsyncMock(
            return_value=[
                {"status": "success", "chunks_indexed": 4},
                {"status": "error", "error": "failed"},
            ]
        )

        with patch(
            "redis_sre_agent.core.pipeline_execution_helpers.IngestionPipeline",
            return_value=mock_pipeline,
        ):
            result = await run_pipeline_operation_helper(
                operation="prepare_sources",
                source_dir=str(source_dir),
                artifacts_path=str(tmp_path / "artifacts"),
            )

        assert result["operation"] == "prepare_sources"
        assert result["prepared_count"] == 2
        assert result["ingestion"]["performed"] is True
        assert result["ingestion"]["successful_documents"] == 1
        assert result["ingestion"]["failed_documents"] == 1
        assert result["ingestion"]["total_chunks_indexed"] == 4
        assert result["source_documents"] == ["a.md", "nested/b.md"]

    @pytest.mark.asyncio
    async def test_run_prepare_sources_requires_existing_directory(self, tmp_path):
        """Prepare-sources should fail on missing directories."""
        with pytest.raises(ValueError, match="does not exist"):
            await run_pipeline_operation_helper(
                operation="prepare_sources",
                source_dir=str(tmp_path / "missing"),
            )

    @pytest.mark.asyncio
    async def test_run_prepare_sources_requires_markdown_files(self, tmp_path):
        """Prepare-sources should fail when no markdown files are present."""
        source_dir = tmp_path / "source_documents"
        source_dir.mkdir()
        (source_dir / "README.md").write_text("# Ignore me\n", encoding="utf-8")

        with pytest.raises(ValueError, match="No markdown files found"):
            await run_pipeline_operation_helper(
                operation="prepare_sources",
                source_dir=str(source_dir),
            )

    @pytest.mark.asyncio
    async def test_run_prepare_sources_validates_batch_date(self, tmp_path):
        """Prepare-sources should validate batch-date formatting."""
        source_dir = tmp_path / "source_documents"
        source_dir.mkdir()
        (source_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid batch date format"):
            await run_pipeline_operation_helper(
                operation="prepare_sources",
                source_dir=str(source_dir),
                batch_date="03-25-2026",
            )

    @pytest.mark.asyncio
    async def test_run_runbooks_rejects_multiple_modes(self):
        """Runbooks helper should reject mutually-exclusive modes."""
        with pytest.raises(ValueError, match="Only one of"):
            await run_pipeline_operation_helper(
                operation="runbooks",
                url="https://example.com",
                test_url="https://example.com/test",
            )

    @pytest.mark.asyncio
    async def test_run_unknown_operation(self):
        """Unknown operations should fail clearly."""
        with pytest.raises(ValueError, match="Unknown pipeline operation"):
            await run_pipeline_operation_helper(operation="unknown")


class TestQueuePipelineOperationTask:
    """Test task queueing helpers for pipeline operations."""

    @pytest.mark.asyncio
    async def test_queue_pipeline_operation_task(self):
        """Queue helper should create a task and enqueue the Docket job."""
        mock_client = AsyncMock()
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
            "message": "Task created",
        }

        with (
            patch(
                "redis_sre_agent.core.pipeline_execution_helpers.get_redis_client",
                return_value=mock_client,
            ),
            patch(
                "redis_sre_agent.core.pipeline_execution_helpers.create_task",
                new_callable=AsyncMock,
            ) as mock_create_task,
            patch(
                "redis_sre_agent.core.pipeline_execution_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://test",
            ),
            patch("redis_sre_agent.core.pipeline_execution_helpers.Docket") as mock_docket,
        ):
            mock_create_task.return_value = mock_result
            docket_instance = AsyncMock()
            docket_instance.__aenter__.return_value = docket_instance
            docket_instance.__aexit__.return_value = False
            queued = AsyncMock()
            docket_instance.add.return_value = queued
            mock_docket.return_value = docket_instance

            result = await queue_pipeline_operation_task(
                operation="scrape",
                user_id="user-123",
                artifacts_path="/tmp/artifacts",
                scrapers=["redis_docs"],
                latest_only=True,
            )

        assert result == {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
            "message": "Pipeline scrape task queued for processing",
            "operation": "scrape",
        }
        mock_create_task.assert_awaited_once_with(
            message="Run pipeline scrape",
            context={
                "task_type": "pipeline",
                "pipeline_operation": "scrape",
                "user_id": "user-123",
            },
            redis_client=mock_client,
        )
        queued.assert_awaited_once_with(
            operation="scrape",
            task_id="task-456",
            thread_id="thread-123",
            artifacts_path="/tmp/artifacts",
            scrapers=["redis_docs"],
            latest_only=True,
        )

    @pytest.mark.asyncio
    async def test_queue_pipeline_operation_task_formats_messages(self):
        """Queue helper should produce operation-specific task subjects."""
        mock_client = AsyncMock()
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
        }

        with (
            patch(
                "redis_sre_agent.core.pipeline_execution_helpers.get_redis_client",
                return_value=mock_client,
            ),
            patch(
                "redis_sre_agent.core.pipeline_execution_helpers.create_task",
                new_callable=AsyncMock,
            ) as mock_create_task,
            patch(
                "redis_sre_agent.core.pipeline_execution_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://test",
            ),
            patch("redis_sre_agent.core.pipeline_execution_helpers.Docket") as mock_docket,
        ):
            mock_create_task.return_value = mock_result
            docket_instance = AsyncMock()
            docket_instance.__aenter__.return_value = docket_instance
            docket_instance.__aexit__.return_value = False
            docket_instance.add.return_value = AsyncMock()
            mock_docket.return_value = docket_instance

            await queue_pipeline_operation_task(
                operation="cleanup",
                keep_days=7,
                artifacts_path="/tmp/artifacts",
            )

        assert mock_create_task.call_args.kwargs["message"] == (
            "Cleanup pipeline batches older than 7 days"
        )

    @pytest.mark.asyncio
    async def test_queue_pipeline_operation_task_preserves_falsy_kwargs(self):
        """Queue helper should keep explicit falsy values and only drop None."""
        mock_client = AsyncMock()
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
        }

        with (
            patch(
                "redis_sre_agent.core.pipeline_execution_helpers.get_redis_client",
                return_value=mock_client,
            ),
            patch(
                "redis_sre_agent.core.pipeline_execution_helpers.create_task",
                new_callable=AsyncMock,
            ) as mock_create_task,
            patch(
                "redis_sre_agent.core.pipeline_execution_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://test",
            ),
            patch("redis_sre_agent.core.pipeline_execution_helpers.Docket") as mock_docket,
        ):
            mock_create_task.return_value = mock_result
            docket_instance = AsyncMock()
            docket_instance.__aenter__.return_value = docket_instance
            docket_instance.__aexit__.return_value = False
            queued = AsyncMock()
            docket_instance.add.return_value = queued
            mock_docket.return_value = docket_instance

            await queue_pipeline_operation_task(
                operation="scrape",
                latest_only=False,
                keep_days=0,
                docs_path="",
                batch_date=None,
            )

        queued.assert_awaited_once_with(
            operation="scrape",
            task_id="task-456",
            thread_id="thread-123",
            latest_only=False,
            keep_days=0,
            docs_path="",
        )


class TestPipelineExecutionHelperUtilities:
    """Test small helper utilities for full branch coverage."""

    def test_build_pipeline_task_message_variants(self):
        """Task subjects should match the requested pipeline operation."""
        assert _build_pipeline_task_message("ingest", {}) == "Run pipeline ingest"
        assert (
            _build_pipeline_task_message("ingest", {"batch_date": "2026-03-25"})
            == "Run pipeline ingest for batch 2026-03-25"
        )
        assert (
            _build_pipeline_task_message("prepare_sources", {})
            == "Prepare source documents from source_documents"
        )
        assert (
            _build_pipeline_task_message("runbooks", {"url": "https://example.com"})
            == "Generate pipeline runbooks for https://example.com"
        )
        assert (
            _build_pipeline_task_message("runbooks", {"test_url": "https://example.com/test"})
            == "Test pipeline runbook extraction for https://example.com/test"
        )
        assert (
            _build_pipeline_task_message("runbooks", {"list_urls": True})
            == "List configured pipeline runbook URLs"
        )
        assert _build_pipeline_task_message("runbooks", {}) == "Generate pipeline runbooks"
        assert _build_pipeline_task_message("scrape", {}) == "Run pipeline scrape"

    @pytest.mark.asyncio
    async def test_get_redis_url_wrapper(self):
        """Redis URL wrapper should delegate to the Docket task helper."""
        with patch(
            "redis_sre_agent.core.docket_tasks.get_redis_url",
            new_callable=AsyncMock,
            return_value="redis://test",
        ) as mock_get:
            result = await get_redis_url()

        assert result == "redis://test"
        mock_get.assert_awaited_once()

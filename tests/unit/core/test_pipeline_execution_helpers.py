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

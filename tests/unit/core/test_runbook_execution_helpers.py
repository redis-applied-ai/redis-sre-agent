"""Tests for runbook execution helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.agent.runbook_generator import (
    GeneratedRunbook,
    ResearchResult,
    RunbookEvaluation,
)
from redis_sre_agent.core.runbook_execution_helpers import (
    _build_runbook_task_message,
    get_redis_url,
    queue_runbook_operation_task,
    run_runbook_operation_helper,
)
from redis_sre_agent.mcp_server.task_contract import runtime_task_execution_context


class TestRunRunbookOperationHelper:
    """Test shared runbook execution helpers."""

    @pytest.fixture
    def generated_runbook(self):
        return GeneratedRunbook(
            title="Redis Memory Pressure - Operational Runbook",
            content="# Redis Memory Pressure\n\nRunbook content",
            category="operational_runbook",
            severity="warning",
            sources=["source-1"],
            generation_timestamp="2026-03-25T12:00:00",
        )

    @pytest.fixture
    def evaluation(self):
        return RunbookEvaluation(
            overall_score=4.2,
            technical_accuracy=4,
            completeness=4,
            actionability=5,
            production_readiness=4,
            strengths=["Clear structure"],
            weaknesses=["Needs more examples"],
            recommendations=["Add another remediation option"],
            evaluation_summary="Production-ready with minor gaps.",
        )

    @pytest.fixture
    def research(self):
        return ResearchResult(
            tavily_findings=[{"title": "External source"}],
            knowledge_base_results=[{"title": "Internal source"}],
            research_summary="Research summary",
        )

    @pytest.mark.asyncio
    async def test_generate_runbook_saves_and_ingests(
        self, tmp_path, generated_runbook, evaluation, research
    ):
        """Generate mode should serialize results, save output, and ingest on request."""
        mock_generator = MagicMock()
        mock_generator.generate_runbook = AsyncMock(
            return_value={
                "success": True,
                "runbook": generated_runbook,
                "evaluation": evaluation,
                "research": research,
                "iterations": 1,
            }
        )

        with (
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.RunbookGenerator",
                return_value=mock_generator,
            ),
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.ingest_sre_document_helper",
                new_callable=AsyncMock,
            ) as mock_ingest,
        ):
            result = await run_runbook_operation_helper(
                operation="generate",
                topic="Memory Pressure",
                scenario_description="Redis memory saturation on primaries",
                output_file=str(tmp_path / "runbook.md"),
                requirements=["Include INFO memory output"],
                ingest=True,
            )

        assert result["operation"] == "generate"
        assert result["success"] is True
        assert result["saved_path"] == str(tmp_path / "runbook.md")
        assert result["runbook"]["title"] == generated_runbook.title
        assert result["evaluation"]["overall_score"] == 4.2
        assert result["research"]["research_summary"] == "Research summary"
        assert (tmp_path / "runbook.md").read_text(encoding="utf-8") == generated_runbook.content
        mock_ingest.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_runbook_without_save_or_ingest(
        self, generated_runbook, evaluation, research
    ):
        """Generate mode should skip persistence when not requested."""
        mock_generator = MagicMock()
        mock_generator.generate_runbook = AsyncMock(
            return_value={
                "success": True,
                "runbook": generated_runbook,
                "evaluation": evaluation,
                "research": research,
                "iterations": 2,
            }
        )

        with (
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.RunbookGenerator",
                return_value=mock_generator,
            ),
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.ingest_sre_document_helper",
                new_callable=AsyncMock,
            ) as mock_ingest,
        ):
            result = await run_runbook_operation_helper(
                operation="generate",
                topic="Replication Lag",
                scenario_description="Replication delay during failover",
                auto_save=False,
                ingest=False,
            )

        assert result["saved_path"] is None
        mock_ingest.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_runbook_unsuccessful_result(self):
        """Generate mode should return a structured failure payload."""
        mock_generator = MagicMock()
        mock_generator.generate_runbook = AsyncMock(
            return_value={"success": False, "iterations": 0}
        )

        with patch(
            "redis_sre_agent.core.runbook_execution_helpers.RunbookGenerator",
            return_value=mock_generator,
        ):
            result = await run_runbook_operation_helper(
                operation="generate",
                topic="Replication Lag",
                scenario_description="Replication delay during failover",
            )

        assert result == {"operation": "generate", "success": False, "iterations": 0}

    @pytest.mark.asyncio
    async def test_evaluate_runbooks_success(self, tmp_path, evaluation):
        """Evaluate mode should score markdown files and optionally save JSON output."""
        input_dir = tmp_path / "runbooks"
        input_dir.mkdir()
        (input_dir / "one.md").write_text("# One\n\ncontent", encoding="utf-8")
        (input_dir / "two.md").write_text("# Two\n\ncontent", encoding="utf-8")

        mock_generator = MagicMock()
        mock_generator._evaluate_runbook = AsyncMock(side_effect=[evaluation, evaluation])

        output_file = tmp_path / "evaluation.json"
        with patch(
            "redis_sre_agent.core.runbook_execution_helpers.RunbookGenerator",
            return_value=mock_generator,
        ):
            result = await run_runbook_operation_helper(
                operation="evaluate",
                input_dir=str(input_dir),
                output_file=str(output_file),
            )

        assert result["operation"] == "evaluate"
        assert result["total_runbooks"] == 2
        assert result["average_score"] == 4.2
        assert result["excellent"] == 2
        assert result["output_file"] == str(output_file)
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_evaluate_runbooks_with_partial_failures(self, tmp_path, evaluation):
        """Evaluate mode should collect file-level failures and continue."""
        input_dir = tmp_path / "runbooks"
        input_dir.mkdir()
        (input_dir / "one.md").write_text("# One\n\ncontent", encoding="utf-8")
        (input_dir / "two.md").write_text("# Two\n\ncontent", encoding="utf-8")

        mock_generator = MagicMock()
        mock_generator._evaluate_runbook = AsyncMock(
            side_effect=[evaluation, Exception("evaluation failed")]
        )

        with patch(
            "redis_sre_agent.core.runbook_execution_helpers.RunbookGenerator",
            return_value=mock_generator,
        ):
            result = await run_runbook_operation_helper(
                operation="evaluate",
                input_dir=str(input_dir),
            )

        assert result["total_runbooks"] == 1
        assert result["errors"] == [{"filename": "two.md", "error": "evaluation failed"}]

    @pytest.mark.asyncio
    async def test_evaluate_runbooks_requires_markdown_files(self, tmp_path):
        """Evaluate mode should fail when no markdown files are available."""
        input_dir = tmp_path / "runbooks"
        input_dir.mkdir()

        with pytest.raises(ValueError, match="No markdown files found"):
            await run_runbook_operation_helper(operation="evaluate", input_dir=str(input_dir))

    @pytest.mark.asyncio
    async def test_runbook_unknown_operation(self):
        """Unknown operations should fail clearly."""
        with pytest.raises(ValueError, match="Unknown runbook operation"):
            await run_runbook_operation_helper(operation="unknown")

    @pytest.mark.asyncio
    async def test_generate_runbook_requires_arguments(self):
        """Generate mode should validate required inputs."""
        with pytest.raises(ValueError, match="topic and scenario_description are required"):
            await run_runbook_operation_helper(operation="generate", topic="Memory Pressure")

    @pytest.mark.asyncio
    async def test_generate_runbook_emits_progress(self, generated_runbook, evaluation, research):
        """Generate mode should emit start and completion progress updates."""
        mock_generator = MagicMock()
        mock_generator.generate_runbook = AsyncMock(
            return_value={
                "success": True,
                "runbook": generated_runbook,
                "evaluation": evaluation,
                "research": research,
                "iterations": 1,
            }
        )
        progress_emitter = AsyncMock()

        with patch(
            "redis_sre_agent.core.runbook_execution_helpers.RunbookGenerator",
            return_value=mock_generator,
        ):
            await run_runbook_operation_helper(
                operation="generate",
                topic="Memory Pressure",
                scenario_description="Redis memory saturation on primaries",
                auto_save=False,
                progress_emitter=progress_emitter,
            )

        assert progress_emitter.emit.await_count == 2


class TestQueueRunbookOperationTask:
    """Test runbook task queueing helper."""

    @pytest.mark.asyncio
    async def test_queue_runbook_operation_task(self):
        """Queue helper should create a task and submit the background job."""
        mock_client = AsyncMock()
        mock_status = MagicMock()
        mock_status.value = "queued"
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": mock_status,
        }

        with (
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.get_redis_client",
                return_value=mock_client,
            ),
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.create_task",
                new_callable=AsyncMock,
            ) as mock_create_task,
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.submit_background_task_call",
                new_callable=AsyncMock,
                return_value={"mode": "agent_task", "task_system": "sre", "result": None},
            ) as mock_submit,
        ):
            mock_create_task.return_value = mock_result

            result = await queue_runbook_operation_task(
                operation="generate",
                user_id="user-123",
                topic="Memory Pressure",
                scenario_description="Redis memory saturation on primaries",
            )

        assert result == {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
            "message": "Runbook generate task queued for processing",
            "operation": "generate",
        }
        mock_create_task.assert_awaited_once_with(
            message="Generate runbook for Memory Pressure",
            context={
                "task_type": "runbook",
                "runbook_operation": "generate",
                "user_id": "user-123",
            },
            redis_client=mock_client,
        )
        assert mock_submit.await_args.kwargs["processor_kwargs"] == {
            "operation": "generate",
            "task_id": "task-456",
            "thread_id": "thread-123",
            "topic": "Memory Pressure",
            "scenario_description": "Redis memory saturation on primaries",
        }

    @pytest.mark.asyncio
    async def test_queue_runbook_operation_task_preserves_falsy_kwargs(self):
        """Queue helper should keep explicit falsy values and only drop None."""
        mock_client = AsyncMock()
        mock_status = MagicMock()
        mock_status.value = "queued"
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": mock_status,
        }

        with (
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.get_redis_client",
                return_value=mock_client,
            ),
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.create_task",
                new_callable=AsyncMock,
            ) as mock_create_task,
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.submit_background_task_call",
                new_callable=AsyncMock,
                return_value={"mode": "agent_task", "task_system": "sre", "result": None},
            ) as mock_submit,
        ):
            mock_create_task.return_value = mock_result

            await queue_runbook_operation_task(
                operation="evaluate",
                ingest=False,
                max_iterations=0,
                output_file="",
                requirements=None,
            )

        assert mock_submit.await_args.kwargs["processor_kwargs"] == {
            "operation": "evaluate",
            "task_id": "task-456",
            "thread_id": "thread-123",
            "ingest": False,
            "max_iterations": 0,
            "output_file": "",
        }

    @pytest.mark.asyncio
    async def test_queue_runbook_operation_task_processes_inline_in_runtime(self):
        mock_client = AsyncMock()
        mock_status = MagicMock()
        mock_status.value = "queued"
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": mock_status,
        }
        mock_processor = AsyncMock(return_value={"success": True})

        with (
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.get_redis_client",
                return_value=mock_client,
            ),
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.create_task",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "redis_sre_agent.core.runbook_execution_helpers._get_runbook_task_callable",
                return_value=mock_processor,
            ),
        ):
            with runtime_task_execution_context({"outerTaskId": "runtime-task-1"}):
                result = await queue_runbook_operation_task(
                    operation="evaluate",
                    input_dir="/tmp/runbooks",
                )

        assert result == {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "done",
            "message": "Runbook evaluate processed inline during runtime execution",
            "operation": "evaluate",
            "result": {"success": True},
        }
        mock_processor.assert_awaited_once_with(
            operation="evaluate",
            task_id="task-456",
            thread_id="thread-123",
            input_dir="/tmp/runbooks",
        )


class TestRunbookExecutionHelperUtilities:
    """Test small helper utilities for full branch coverage."""

    def test_build_runbook_task_message_variants(self):
        """Task subjects should match the requested runbook operation."""
        assert _build_runbook_task_message("generate", {"topic": "Memory Pressure"}) == (
            "Generate runbook for Memory Pressure"
        )
        assert _build_runbook_task_message("generate", {}) == "Generate runbook"
        assert _build_runbook_task_message("evaluate", {}) == (
            "Evaluate runbooks in source_documents/runbooks"
        )
        assert (
            _build_runbook_task_message("evaluate", {"input_dir": "/tmp/runbooks"})
            == "Evaluate runbooks in /tmp/runbooks"
        )
        assert _build_runbook_task_message("other", {}) == "Runbook operation other"

    @pytest.mark.asyncio
    async def test_generate_runbook_auto_save_slugifies_topic(self, tmp_path, monkeypatch):
        """Auto-save mode should use the default runbook path."""
        generated_runbook = GeneratedRunbook(
            title="Redis Memory Pressure - Operational Runbook",
            content="# Redis Memory Pressure\n\nRunbook content",
            category="operational_runbook",
            severity="warning",
            sources=["source-1"],
            generation_timestamp="2026-03-25T12:00:00",
        )
        evaluation = RunbookEvaluation(
            overall_score=4.2,
            technical_accuracy=4,
            completeness=4,
            actionability=5,
            production_readiness=4,
            strengths=["Clear structure"],
            weaknesses=["Needs more examples"],
            recommendations=["Add another remediation option"],
            evaluation_summary="Production-ready with minor gaps.",
        )
        research = ResearchResult(
            tavily_findings=[{"title": "External source"}],
            knowledge_base_results=[{"title": "Internal source"}],
            research_summary="Research summary",
        )
        mock_generator = MagicMock()
        mock_generator.generate_runbook = AsyncMock(
            return_value={
                "success": True,
                "runbook": generated_runbook,
                "evaluation": evaluation,
                "research": research,
                "iterations": 1,
            }
        )

        monkeypatch.chdir(tmp_path)
        with patch(
            "redis_sre_agent.core.runbook_execution_helpers.RunbookGenerator",
            return_value=mock_generator,
        ):
            result = await run_runbook_operation_helper(
                operation="generate",
                topic="Memory / Pressure",
                scenario_description="Redis memory saturation on primaries",
            )

        assert result["saved_path"] == "source_documents/runbooks/memory-pressure.md"
        assert (tmp_path / "source_documents/runbooks/memory-pressure.md").read_text(
            encoding="utf-8"
        ) == generated_runbook.content

    @pytest.mark.asyncio
    async def test_generate_runbook_ingest_without_saved_path(self):
        """Ingest mode should fall back to a generated source when not saving."""
        generated_runbook = GeneratedRunbook(
            title="Redis Memory Pressure - Operational Runbook",
            content="# Redis Memory Pressure\n\nRunbook content",
            category="operational_runbook",
            severity="warning",
            sources=["source-1"],
            generation_timestamp="2026-03-25T12:00:00",
        )
        evaluation = RunbookEvaluation(
            overall_score=4.2,
            technical_accuracy=4,
            completeness=4,
            actionability=5,
            production_readiness=4,
            strengths=["Clear structure"],
            weaknesses=["Needs more examples"],
            recommendations=["Add another remediation option"],
            evaluation_summary="Production-ready with minor gaps.",
        )
        research = ResearchResult(
            tavily_findings=[{"title": "External source"}],
            knowledge_base_results=[{"title": "Internal source"}],
            research_summary="Research summary",
        )
        mock_generator = MagicMock()
        mock_generator.generate_runbook = AsyncMock(
            return_value={
                "success": True,
                "runbook": generated_runbook,
                "evaluation": evaluation,
                "research": research,
                "iterations": 1,
            }
        )

        with (
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.RunbookGenerator",
                return_value=mock_generator,
            ),
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.ingest_sre_document_helper",
                new_callable=AsyncMock,
            ) as mock_ingest,
        ):
            await run_runbook_operation_helper(
                operation="generate",
                topic="Memory Pressure",
                scenario_description="Redis memory saturation on primaries",
                auto_save=False,
                ingest=True,
            )

        assert mock_ingest.await_args.kwargs["source"] == "generated_runbook"

    @pytest.mark.asyncio
    async def test_evaluate_runbooks_uses_filename_when_heading_missing(self, tmp_path):
        """Evaluation should fall back to the filename when no Markdown heading exists."""
        input_dir = tmp_path / "runbooks"
        input_dir.mkdir()
        (input_dir / "plain-name.md").write_text("content only", encoding="utf-8")

        evaluation = RunbookEvaluation(
            overall_score=4.2,
            technical_accuracy=4,
            completeness=4,
            actionability=5,
            production_readiness=4,
            strengths=["Clear structure"],
            weaknesses=["Needs more examples"],
            recommendations=["Add another remediation option"],
            evaluation_summary="Production-ready with minor gaps.",
        )
        mock_generator = MagicMock()
        mock_generator._evaluate_runbook = AsyncMock(return_value=evaluation)

        with patch(
            "redis_sre_agent.core.runbook_execution_helpers.RunbookGenerator",
            return_value=mock_generator,
        ):
            result = await run_runbook_operation_helper(
                operation="evaluate",
                input_dir=str(input_dir),
            )

        assert result["results"][0]["title"] == "plain-name"

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

    @pytest.mark.asyncio
    async def test_generate_runbook_without_optional_objects(self):
        """Generate mode should preserve missing optional result objects."""
        generated_runbook = GeneratedRunbook(
            title="Redis Memory Pressure - Operational Runbook",
            content="# Redis Memory Pressure\n\nRunbook content",
            category="operational_runbook",
            severity="warning",
            sources=["source-1"],
            generation_timestamp="2026-03-25T12:00:00",
        )
        mock_generator = MagicMock()
        mock_generator.generate_runbook = AsyncMock(
            return_value={
                "success": True,
                "runbook": generated_runbook,
                "evaluation": None,
                "research": {"kind": "inline"},
                "iterations": 1,
            }
        )

        with patch(
            "redis_sre_agent.core.runbook_execution_helpers.RunbookGenerator",
            return_value=mock_generator,
        ):
            result = await run_runbook_operation_helper(
                operation="generate",
                topic="Memory Pressure",
                scenario_description="Redis memory saturation on primaries",
                auto_save=False,
            )

        assert result["evaluation"] is None
        assert result["research"] == {"kind": "inline"}

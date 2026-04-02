"""Shared helpers for task-backed pipeline execution workflows."""

from __future__ import annotations

import inspect
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from docket import Docket

from redis_sre_agent.core.helper_utils import emit_progress as _emit_progress
from redis_sre_agent.core.helper_utils import get_docket_redis_url as get_redis_url
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.tasks import create_task
from redis_sre_agent.pipelines.ingestion.processor import IngestionPipeline
from redis_sre_agent.pipelines.orchestrator import PipelineOrchestrator
from redis_sre_agent.pipelines.scraper.base import ArtifactStorage


def _build_scrape_config(*, latest_only: bool, docs_path: str) -> Dict[str, Dict[str, Any]]:
    """Build scraper configuration shared by scrape/full operations."""
    return {
        "redis_docs": {"latest_only": latest_only},
        "redis_docs_local": {"latest_only": latest_only, "docs_repo_path": docs_path},
    }


def _resolve_batch_date(storage: ArtifactStorage, batch_date: Optional[str]) -> str:
    """Validate and apply an optional batch-date override."""
    if not batch_date:
        return storage.current_date

    try:
        datetime.strptime(batch_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid batch date format: {batch_date}. Use YYYY-MM-DD") from exc

    storage.current_date = batch_date
    storage.current_batch_path = storage.base_path / batch_date
    storage._dirs_created = False
    return batch_date


def _list_source_markdown_files(source_path: Path) -> List[Path]:
    """Return source markdown files excluding README files."""
    markdown_files = [
        path for path in source_path.rglob("*.md") if path.name.lower() != "readme.md"
    ]
    return sorted(markdown_files)


def _build_pipeline_task_message(operation: str, kwargs: Dict[str, Any]) -> str:
    """Generate a concise subject line for a pipeline task."""
    if operation == "cleanup":
        return f"Cleanup pipeline batches older than {kwargs.get('keep_days', 30)} days"
    if operation == "ingest":
        batch_date = kwargs.get("batch_date")
        return (
            f"Run pipeline ingest for batch {batch_date}" if batch_date else "Run pipeline ingest"
        )
    if operation == "prepare_sources":
        return f"Prepare source documents from {kwargs.get('source_dir', 'source_documents')}"
    if operation == "runbooks":
        if kwargs.get("url"):
            return f"Generate pipeline runbooks for {kwargs['url']}"
        if kwargs.get("test_url"):
            return f"Test pipeline runbook extraction for {kwargs['test_url']}"
        if kwargs.get("list_urls"):
            return "List configured pipeline runbook URLs"
        return "Generate pipeline runbooks"
    return f"Run pipeline {operation}"


def _get_pipeline_task_callable() -> Any:
    """Resolve the Docket task callable without a module import cycle."""
    from redis_sre_agent.core.docket_tasks import process_pipeline_operation

    return process_pipeline_operation


async def run_pipeline_operation_helper(
    operation: str,
    *,
    batch_date: Optional[str] = None,
    artifacts_path: str = "./artifacts",
    scrapers: Optional[List[str]] = None,
    latest_only: bool = False,
    docs_path: str = "./redis-docs",
    source_dir: str = "source_documents",
    prepare_only: bool = False,
    keep_days: int = 30,
    url: Optional[str] = None,
    test_url: Optional[str] = None,
    list_urls: bool = False,
    progress_emitter: Any = None,
) -> Dict[str, Any]:
    """Execute a pipeline operation and return a structured result."""
    await _emit_progress(
        progress_emitter,
        f"Starting pipeline {operation}",
        "pipeline_start",
        {"operation": operation},
    )

    if operation == "scrape":
        orchestrator = PipelineOrchestrator(
            artifacts_path,
            _build_scrape_config(latest_only=latest_only, docs_path=docs_path),
            scrapers=scrapers,
        )
        result = await orchestrator.run_scraping_pipeline(scrapers)
        await _emit_progress(
            progress_emitter,
            f"Completed pipeline {operation}",
            "pipeline_complete",
            {"operation": operation},
        )
        return {"operation": operation, **result}

    if operation == "ingest":
        orchestrator = PipelineOrchestrator(
            artifacts_path,
            {"ingestion": {"latest_only": latest_only}},
        )
        result = await orchestrator.run_ingestion_pipeline(batch_date)
        await _emit_progress(
            progress_emitter,
            f"Completed pipeline {operation}",
            "pipeline_complete",
            {"operation": operation},
        )
        return {"operation": operation, **result}

    if operation == "full":
        config = _build_scrape_config(latest_only=latest_only, docs_path=docs_path)
        config["ingestion"] = {"latest_only": latest_only}
        orchestrator = PipelineOrchestrator(artifacts_path, config, scrapers=scrapers)
        result = await orchestrator.run_full_pipeline(scrapers)
        await _emit_progress(
            progress_emitter,
            f"Completed pipeline {operation}",
            "pipeline_complete",
            {"operation": operation},
        )
        return {"operation": operation, **result}

    if operation == "cleanup":
        orchestrator = PipelineOrchestrator(artifacts_path)
        result = await orchestrator.cleanup_old_batches(keep_days)
        await _emit_progress(
            progress_emitter,
            f"Completed pipeline {operation}",
            "pipeline_complete",
            {"operation": operation},
        )
        return {"operation": operation, **result}

    if operation == "runbooks":
        active_modes = sum(bool(value) for value in [url, test_url, list_urls])
        if active_modes > 1:
            raise ValueError("Only one of url, test_url, or list_urls may be provided")

        orchestrator = PipelineOrchestrator(artifacts_path, scrapers=["runbook_generator"])
        generator = orchestrator.scrapers["runbook_generator"]

        if list_urls:
            await _emit_progress(
                progress_emitter,
                f"Completed pipeline {operation}",
                "pipeline_complete",
                {"operation": operation},
            )
            return {
                "operation": operation,
                "mode": "list_urls",
                "configured_urls": generator.get_configured_urls(),
            }

        if test_url:
            await _emit_progress(
                progress_emitter,
                f"Completed pipeline {operation}",
                "pipeline_complete",
                {"operation": operation},
            )
            return {
                "operation": operation,
                "mode": "test_url",
                "url": test_url,
                "result": await generator.test_url_extraction(test_url),
            }

        if url:
            added = await generator.add_runbook_url(url)
            single_url_config = dict(generator.config)
            single_url_config["runbook_urls"] = [url]
            single_url_orchestrator = PipelineOrchestrator(
                artifacts_path,
                {"runbook_generator": single_url_config},
                scrapers=["runbook_generator"],
            )
            single_generator = single_url_orchestrator.scrapers["runbook_generator"]
            result = await single_generator.run_scraping_job()
            await _emit_progress(
                progress_emitter,
                f"Completed pipeline {operation}",
                "pipeline_complete",
                {"operation": operation},
            )
            return {
                "operation": operation,
                "mode": "single_url",
                "url": url,
                "url_added": added,
                **result,
            }

        result = await generator.run_scraping_job()
        await _emit_progress(
            progress_emitter,
            f"Completed pipeline {operation}",
            "pipeline_complete",
            {"operation": operation},
        )
        return {"operation": operation, "mode": "configured_urls", **result}

    if operation == "prepare_sources":
        source_path = Path(source_dir)
        if not source_path.exists():
            raise ValueError(f"Source directory does not exist: {source_path}")

        markdown_files = _list_source_markdown_files(source_path)
        if not markdown_files:
            raise ValueError(f"No markdown files found in {source_path}")

        storage = ArtifactStorage(artifacts_path)
        batch_date_to_use = _resolve_batch_date(storage, batch_date)
        pipeline = IngestionPipeline(storage)

        prepared_count = await pipeline.prepare_source_artifacts(source_path, batch_date_to_use)
        result: Dict[str, Any] = {
            "operation": operation,
            "batch_date": batch_date_to_use,
            "prepared_count": prepared_count,
            "prepare_only": prepare_only,
            "source_documents": [str(path.relative_to(source_path)) for path in markdown_files],
        }

        if prepare_only:
            result["ingestion"] = {"performed": False}
            await _emit_progress(
                progress_emitter,
                f"Completed pipeline {operation}",
                "pipeline_complete",
                {"operation": operation},
            )
            return result

        ingestion_results = await pipeline.ingest_prepared_batch(batch_date_to_use)
        successful = [item for item in ingestion_results if item.get("status") == "success"]
        failed = [item for item in ingestion_results if item.get("status") == "error"]
        result["ingestion"] = {
            "performed": True,
            "successful_documents": len(successful),
            "failed_documents": len(failed),
            "total_chunks_indexed": sum(item.get("chunks_indexed", 0) for item in successful),
            "results": ingestion_results,
        }
        await _emit_progress(
            progress_emitter,
            f"Completed pipeline {operation}",
            "pipeline_complete",
            {"operation": operation},
        )
        return result

    raise ValueError(f"Unknown pipeline operation: {operation}")


async def queue_pipeline_operation_task(
    operation: str,
    *,
    user_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Create and queue a task-backed pipeline operation."""
    redis_client = get_redis_client()
    context: Dict[str, Any] = {
        "task_type": "pipeline",
        "pipeline_operation": operation,
    }
    if user_id:
        context["user_id"] = user_id

    result = await create_task(
        message=_build_pipeline_task_message(operation, kwargs),
        context=context,
        redis_client=redis_client,
    )

    task_kwargs = {key: value for key, value in kwargs.items() if value is not None}
    async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
        task_func = docket.add(_get_pipeline_task_callable(), key=result["task_id"])
        if inspect.isawaitable(task_func):
            task_func = await task_func
        await task_func(
            operation=operation,
            task_id=result["task_id"],
            thread_id=result["thread_id"],
            **task_kwargs,
        )

    return {
        "thread_id": result["thread_id"],
        "task_id": result["task_id"],
        "status": result["status"].value
        if hasattr(result["status"], "value")
        else str(result["status"]),
        "message": f"Pipeline {operation} task queued for processing",
        "operation": operation,
    }

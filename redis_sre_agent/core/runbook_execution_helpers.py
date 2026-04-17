"""Shared helpers for task-backed runbook workflows."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from redis_sre_agent.agent.runbook_generator import GeneratedRunbook, RunbookGenerator
from redis_sre_agent.core.helper_utils import emit_progress as _emit_progress
from redis_sre_agent.core.helper_utils import get_docket_redis_url as get_redis_url
from redis_sre_agent.core.knowledge_helpers import ingest_sre_document_helper
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.tasks import create_task
from redis_sre_agent.mcp_server.task_contract import submit_background_task_call


def _slugify_topic(topic: str) -> str:
    """Create a filesystem-safe stem for generated runbooks."""
    normalized = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    return normalized or "generated-runbook"


def _resolve_runbook_output_path(
    topic: str, output_file: Optional[str], auto_save: bool
) -> Optional[Path]:
    """Determine where a generated runbook should be written, if anywhere."""
    if output_file:
        return Path(output_file)
    if auto_save:
        return Path("source_documents/runbooks") / f"{_slugify_topic(topic)}.md"
    return None


def _serialize_value(value: Any) -> Any:
    """Serialize dataclass values into plain dictionaries."""
    if value is None:
        return None
    if is_dataclass(value):
        return asdict(value)
    return value


def _extract_runbook_title(content: str, fallback_title: str) -> str:
    """Use the first Markdown heading as the title when available."""
    title_line = next((line for line in content.splitlines() if line.startswith("# ")), None)
    if title_line:
        return title_line[2:].strip()
    return fallback_title


def _build_runbook_task_message(operation: str, kwargs: Dict[str, Any]) -> str:
    """Generate a concise subject line for a runbook task."""
    if operation == "generate":
        topic = kwargs.get("topic")
        return f"Generate runbook for {topic}" if topic else "Generate runbook"
    if operation == "evaluate":
        return f"Evaluate runbooks in {kwargs.get('input_dir', 'source_documents/runbooks')}"
    return f"Runbook operation {operation}"


def _get_runbook_task_callable() -> Any:
    """Resolve the Docket task callable without a module import cycle."""
    from redis_sre_agent.core.docket_tasks import process_runbook_operation

    return process_runbook_operation


async def _generate_runbook(
    *,
    topic: str,
    scenario_description: str,
    severity: str,
    category: str,
    output_file: Optional[str],
    requirements: Optional[List[str]],
    max_iterations: int,
    auto_save: bool,
    ingest: bool,
) -> Dict[str, Any]:
    """Generate, optionally save, and optionally ingest a runbook."""
    generator = RunbookGenerator()
    result = await generator.generate_runbook(
        topic=topic,
        scenario_description=scenario_description,
        severity=severity,
        category=category,
        specific_requirements=requirements or None,
        max_iterations=max_iterations,
    )

    if not result.get("success"):
        return {"operation": "generate", **result}

    runbook = result["runbook"]
    saved_path = _resolve_runbook_output_path(topic, output_file, auto_save)
    if saved_path is not None:
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.write_text(runbook.content, encoding="utf-8")

    if ingest:
        await ingest_sre_document_helper(
            title=runbook.title,
            content=runbook.content,
            source=str(saved_path) if saved_path is not None else "generated_runbook",
            category=runbook.category,
            severity=runbook.severity,
            doc_type="runbook",
        )

    return {
        "operation": "generate",
        "success": True,
        "iterations": result.get("iterations", 0),
        "saved_path": str(saved_path) if saved_path is not None else None,
        "runbook": _serialize_value(runbook),
        "evaluation": _serialize_value(result.get("evaluation")),
        "research": _serialize_value(result.get("research")),
    }


async def _evaluate_runbooks(*, input_dir: str, output_file: Optional[str]) -> Dict[str, Any]:
    """Evaluate runbook markdown files in a directory."""
    input_path = Path(input_dir)
    markdown_files = sorted(input_path.glob("*.md"))
    if not markdown_files:
        raise ValueError(f"No markdown files found in {input_path}")

    generator = RunbookGenerator()
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for markdown_file in markdown_files:
        content = markdown_file.read_text(encoding="utf-8")
        title = _extract_runbook_title(content, markdown_file.stem)
        runbook = GeneratedRunbook(
            title=title,
            content=content,
            category="existing_runbook",
            severity="unknown",
            sources=["existing_file"],
            generation_timestamp="",
        )

        try:
            evaluation = await generator._evaluate_runbook(runbook)
            results.append(
                {
                    "filename": markdown_file.name,
                    "title": title,
                    **asdict(evaluation),
                }
            )
        except Exception as exc:
            errors.append({"filename": markdown_file.name, "error": str(exc)})

    total_runbooks = len(results)
    average_score = (
        sum(item["overall_score"] for item in results) / total_runbooks if total_runbooks else 0.0
    )
    payload: Dict[str, Any] = {
        "operation": "evaluate",
        "input_dir": str(input_path),
        "total_files": len(markdown_files),
        "total_runbooks": total_runbooks,
        "average_score": average_score,
        "excellent": sum(1 for item in results if item["overall_score"] >= 4.0),
        "good": sum(1 for item in results if 3.0 <= item["overall_score"] < 4.0),
        "needs_improvement": sum(1 for item in results if item["overall_score"] < 3.0),
        "results": results,
        "errors": errors,
        "output_file": output_file,
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return payload


async def run_runbook_operation_helper(
    operation: str,
    *,
    topic: Optional[str] = None,
    scenario_description: Optional[str] = None,
    severity: str = "warning",
    category: str = "operational_runbook",
    output_file: Optional[str] = None,
    requirements: Optional[List[str]] = None,
    max_iterations: int = 2,
    auto_save: bool = True,
    ingest: bool = False,
    input_dir: str = "source_documents/runbooks",
    progress_emitter: Any = None,
) -> Dict[str, Any]:
    """Execute a runbook operation and return a structured result."""
    await _emit_progress(
        progress_emitter,
        f"Starting runbook {operation}",
        "runbook_start",
        {"operation": operation},
    )

    if operation == "generate":
        if topic is None or scenario_description is None:
            raise ValueError("topic and scenario_description are required for generate")
        result = await _generate_runbook(
            topic=topic,
            scenario_description=scenario_description,
            severity=severity,
            category=category,
            output_file=output_file,
            requirements=requirements,
            max_iterations=max_iterations,
            auto_save=auto_save,
            ingest=ingest,
        )
    elif operation == "evaluate":
        result = await _evaluate_runbooks(input_dir=input_dir, output_file=output_file)
    else:
        raise ValueError(f"Unknown runbook operation: {operation}")

    await _emit_progress(
        progress_emitter,
        f"Completed runbook {operation}",
        "runbook_complete",
        {"operation": operation},
    )
    return result


async def queue_runbook_operation_task(
    operation: str,
    *,
    user_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Create and queue a task-backed runbook operation."""
    redis_client = get_redis_client()
    context: Dict[str, Any] = {
        "task_type": "runbook",
        "runbook_operation": operation,
    }
    if user_id:
        context["user_id"] = user_id

    result = await create_task(
        message=_build_runbook_task_message(operation, kwargs),
        context=context,
        redis_client=redis_client,
    )

    task_kwargs = {key: value for key, value in kwargs.items() if value is not None}
    execution = await submit_background_task_call(
        processor=_get_runbook_task_callable(),
        key=str(result["task_id"]),
        processor_kwargs={
            "operation": operation,
            "task_id": result["task_id"],
            "thread_id": result["thread_id"],
            **task_kwargs,
        },
    )

    response = {
        "thread_id": result["thread_id"],
        "task_id": result["task_id"],
        "operation": operation,
    }
    if execution["mode"] == "inline":
        response.update(
            {
                "status": "done",
                "message": f"Runbook {operation} processed inline during runtime execution",
                "result": execution["result"],
            }
        )
        return response

    response.update(
        {
            "status": result["status"].value
            if hasattr(result["status"], "value")
            else str(result["status"]),
            "message": f"Runbook {operation} task queued for processing",
        }
    )
    return response

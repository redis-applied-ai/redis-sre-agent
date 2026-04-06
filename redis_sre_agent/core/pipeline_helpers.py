"""Shared helpers for pipeline inspection workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from redis_sre_agent.pipelines.orchestrator import PipelineOrchestrator
from redis_sre_agent.pipelines.scraper.base import ArtifactStorage


async def get_pipeline_status_helper(artifacts_path: str = "./artifacts") -> Dict[str, Any]:
    """Return pipeline status in a machine-friendly shape."""
    orchestrator = PipelineOrchestrator(artifacts_path)
    return await orchestrator.get_pipeline_status()


async def get_pipeline_batch_helper(
    batch_date: str, artifacts_path: str = "./artifacts"
) -> Dict[str, Any]:
    """Return detailed information for a specific batch."""
    storage = ArtifactStorage(artifacts_path)
    manifest = storage.get_batch_manifest(batch_date)
    if not manifest:
        return {
            "batch_date": batch_date,
            "artifacts_path": str(storage.base_path),
            "error": f"No manifest found for batch {batch_date}",
        }

    batch_path = Path(artifacts_path) / batch_date
    ingestion_manifest = batch_path / "ingestion_manifest.json"

    ingestion: Dict[str, Any] = {
        "available": False,
        "status": "not_ingested",
    }
    if ingestion_manifest.exists():
        with ingestion_manifest.open(encoding="utf-8") as f:
            ingestion_data = json.load(f)
        ingestion = {
            "available": True,
            "status": "success" if ingestion_data.get("success") else "failed",
            "documents_processed": ingestion_data.get("documents_processed", 0),
            "chunks_created": ingestion_data.get("chunks_created", 0),
            "chunks_indexed": ingestion_data.get("chunks_indexed", 0),
            "categories_processed": ingestion_data.get("categories_processed", {}),
        }

    return {
        "batch_date": batch_date,
        "artifacts_path": str(storage.base_path),
        "created_at": manifest.get("created_at"),
        "total_documents": manifest.get("total_documents", 0),
        "categories": manifest.get("categories", {}),
        "document_types": manifest.get("document_types", {}),
        "sources": manifest.get("sources", []),
        "ingestion": ingestion,
    }

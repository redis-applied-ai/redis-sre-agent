"""Tests for pipeline helper functions."""

from __future__ import annotations

import json

import pytest

from redis_sre_agent.core.pipeline_helpers import (
    get_pipeline_batch_helper,
    get_pipeline_status_helper,
)


@pytest.mark.asyncio
async def test_get_pipeline_status_helper_delegates_to_orchestrator():
    """Status helper returns orchestrator payload."""
    from unittest.mock import AsyncMock, patch

    mock_orchestrator = AsyncMock()
    mock_orchestrator.get_pipeline_status.return_value = {"available_batches": ["2026-03-25"]}

    with patch(
        "redis_sre_agent.core.pipeline_helpers.PipelineOrchestrator",
        return_value=mock_orchestrator,
    ) as mock_cls:
        result = await get_pipeline_status_helper("/tmp/artifacts")

        assert result == {"available_batches": ["2026-03-25"]}
        mock_cls.assert_called_once_with("/tmp/artifacts")
        mock_orchestrator.get_pipeline_status.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_get_pipeline_batch_helper_missing_manifest(tmp_path):
    """Batch helper returns error payload when manifest is absent."""
    result = await get_pipeline_batch_helper("2026-03-25", artifacts_path=str(tmp_path))

    assert result["batch_date"] == "2026-03-25"
    assert "error" in result


@pytest.mark.asyncio
async def test_get_pipeline_batch_helper_without_ingestion_manifest(tmp_path):
    """Batch helper reports not_ingested when only batch manifest exists."""
    batch_dir = tmp_path / "2026-03-25"
    batch_dir.mkdir(parents=True)
    (batch_dir / "batch_manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-03-25T00:00:00+00:00",
                "total_documents": 3,
                "categories": {"oss": 2},
                "document_types": {"documentation": 3},
                "sources": ["https://redis.io"],
            }
        ),
        encoding="utf-8",
    )

    result = await get_pipeline_batch_helper("2026-03-25", artifacts_path=str(tmp_path))

    assert result["total_documents"] == 3
    assert result["ingestion"]["available"] is False
    assert result["ingestion"]["status"] == "not_ingested"


@pytest.mark.asyncio
async def test_get_pipeline_batch_helper_with_ingestion_manifest(tmp_path):
    """Batch helper includes ingestion details when manifest exists."""
    batch_dir = tmp_path / "2026-03-25"
    batch_dir.mkdir(parents=True)
    (batch_dir / "batch_manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-03-25T00:00:00+00:00",
                "total_documents": 5,
                "categories": {"oss": 4},
                "document_types": {"documentation": 5},
                "sources": ["https://redis.io"],
            }
        ),
        encoding="utf-8",
    )
    (batch_dir / "ingestion_manifest.json").write_text(
        json.dumps(
            {
                "success": True,
                "documents_processed": 5,
                "chunks_created": 12,
                "chunks_indexed": 10,
                "categories_processed": {"oss": {"documents_processed": 5}},
            }
        ),
        encoding="utf-8",
    )

    result = await get_pipeline_batch_helper("2026-03-25", artifacts_path=str(tmp_path))

    assert result["ingestion"]["available"] is True
    assert result["ingestion"]["status"] == "success"
    assert result["ingestion"]["chunks_created"] == 12

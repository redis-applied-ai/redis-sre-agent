import json
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.knowledge_pack import knowledge_pack
from redis_sre_agent.knowledge_pack.models import KnowledgePackInspection


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_build_help_shows_profile_and_json(cli_runner):
    result = cli_runner.invoke(knowledge_pack, ["build", "--help"])

    assert result.exit_code == 0
    assert "--profile" in result.output
    assert "--json" in result.output


def test_build_command_outputs_json(cli_runner):
    payload = {
        "pack_id": "pack-123",
        "output_path": "/tmp/pack.zip",
        "batch_date": "2026-05-12",
        "pack_profile": "runtime",
        "record_counts": {
            "artifact_documents": 1,
            "chunk_records": 1,
            "document_meta_records": 1,
            "source_meta_records": 1,
        },
    }

    with patch(
        "redis_sre_agent.cli.knowledge_pack.build_knowledge_pack",
        new=AsyncMock(return_value=payload),
    ) as build_mock:
        result = cli_runner.invoke(
            knowledge_pack,
            ["build", "--batch-date", "2026-05-12", "--output", "/tmp/pack.zip", "--json"],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == payload
    assert build_mock.await_count == 1


def test_inspect_command_renders_table(cli_runner):
    inspection = KnowledgePackInspection.model_validate(
        {
            "manifest": {
                "pack_id": "pack-123",
                "created_at": "2026-05-12T00:00:00+00:00",
                "batch_date": "2026-05-12",
                "schema_hash": "schema",
                "embedding_provider": "openai",
                "embedding_model": "text-embedding-3-small",
                "vector_dim": 1536,
                "embedding_fingerprint": "fingerprint",
                "record_counts": {
                    "artifact_documents": 1,
                    "chunk_records": 1,
                    "document_meta_records": 1,
                    "source_meta_records": 1,
                },
            },
            "checksums_verified": True,
            "restore_compatible": True,
            "compatibility_reason": "compatible",
        }
    )

    with patch(
        "redis_sre_agent.cli.knowledge_pack.inspect_knowledge_pack", return_value=inspection
    ):
        result = cli_runner.invoke(knowledge_pack, ["inspect", "--pack", "/tmp/pack.zip"])

    assert result.exit_code == 0, result.output
    assert "Knowledge Pack" in result.output
    assert "pack-123" in result.output
    assert "verified" in result.output


def test_load_command_reports_restore_counts(cli_runner):
    payload = {
        "pack_id": "pack-123",
        "pack_profile": "runtime",
        "mode": "restore",
        "batch_date": "2026-05-12",
        "chunk_records_loaded": 4,
        "document_meta_records_loaded": 2,
        "source_meta_records_loaded": 1,
    }

    with patch(
        "redis_sre_agent.cli.knowledge_pack.load_knowledge_pack",
        new=AsyncMock(return_value=payload),
    ):
        result = cli_runner.invoke(knowledge_pack, ["load", "--pack", "/tmp/pack.zip"])

    assert result.exit_code == 0, result.output
    assert "Knowledge pack loaded" in result.output
    assert "chunks=4" in result.output

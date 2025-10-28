"""Integration tests for CLI knowledge commands using Testcontainers (Docker Compose).

These tests do not mock Redis. They ingest minimal fragments directly into the
knowledge index and exercise the CLI commands:
- `redis-sre-agent knowledge fragments <DOCUMENT_HASH>`
- `redis-sre-agent knowledge related <DOCUMENT_HASH> --chunk-index N`
"""

import asyncio
import json
from typing import Dict, List

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.main import main as cli_main
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_knowledge_index


@pytest.mark.integration
def test_knowledge_fragments_cli_lists_all_chunks(redis_container):
    """Verify `knowledge fragments` lists all fragments for a document (JSON mode)."""

    runner = CliRunner()

    # Prepare sample fragments directly in the knowledge index (no OpenAI calls)
    async def _prepare() -> Dict[str, str]:
        index = await get_knowledge_index()

        doc_hash = "dochash-abc123"
        chunks: List[Dict] = [
            {
                "id": "frag-1",
                "title": "Sample Doc",
                "content": "First chunk content.",
                "source": "tests",
                "category": "testing",
                "severity": "info",
                "document_hash": doc_hash,
                "chunk_index": 0,
                "total_chunks": 2,
                # flat/cosine/float32 of configured dimension
                "vector": [0.0] * settings.vector_dim,
            },
            {
                "id": "frag-2",
                "title": "Sample Doc",
                "content": "Second chunk content.",
                "source": "tests",
                "category": "testing",
                "severity": "info",
                "document_hash": doc_hash,
                "chunk_index": 1,
                "total_chunks": 2,
                "vector": [0.0] * settings.vector_dim,
            },
        ]

        keys = [RedisKeys.knowledge_document(c["id"]) for c in chunks]
        await index.load(id_field="id", keys=keys, data=chunks)
        return {"document_hash": doc_hash}

    prep = asyncio.run(_prepare())

    # Invoke CLI in JSON mode for stable assertions
    result = runner.invoke(
        cli_main,
        ["knowledge", "fragments", prep["document_hash"], "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["document_hash"] == prep["document_hash"]
    assert payload.get("fragments_count") == 2

    frags = payload.get("fragments") or []
    assert len(frags) == 2
    # Ensure both chunk indexes are present and ordered
    assert [f.get("chunk_index") for f in frags] == [0, 1]


@pytest.mark.integration
def test_knowledge_related_cli_returns_context_window(redis_container):
    """Verify `knowledge related` returns a window around the target chunk."""

    runner = CliRunner()

    async def _prepare() -> Dict[str, str]:
        index = await get_knowledge_index()
        doc_hash = "dochash-xyz789"
        chunks: List[Dict] = [
            {
                "id": "rfrag-0",
                "title": "Rel Doc",
                "content": "Ctx 0",
                "source": "tests",
                "category": "testing",
                "severity": "info",
                "document_hash": doc_hash,
                "chunk_index": 0,
                "total_chunks": 3,
                "vector": [0.0] * settings.vector_dim,
            },
            {
                "id": "rfrag-1",
                "title": "Rel Doc",
                "content": "Ctx 1 (target)",
                "source": "tests",
                "category": "testing",
                "severity": "info",
                "document_hash": doc_hash,
                "chunk_index": 1,
                "total_chunks": 3,
                "vector": [0.0] * settings.vector_dim,
            },
            {
                "id": "rfrag-2",
                "title": "Rel Doc",
                "content": "Ctx 2",
                "source": "tests",
                "category": "testing",
                "severity": "info",
                "document_hash": doc_hash,
                "chunk_index": 2,
                "total_chunks": 3,
                "vector": [0.0] * settings.vector_dim,
            },
        ]
        keys = [RedisKeys.knowledge_document(c["id"]) for c in chunks]
        await index.load(id_field="id", keys=keys, data=chunks)
        return {"document_hash": doc_hash}

    prep = asyncio.run(_prepare())

    # Ask for a window=1 around chunk 1
    result = runner.invoke(
        cli_main,
        [
            "knowledge",
            "related",
            prep["document_hash"],
            "--chunk-index",
            "1",
            "--window",
            "1",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["document_hash"] == prep["document_hash"]
    assert payload.get("target_chunk_index") == 1
    assert payload.get("context_window") == 1

    rel = payload.get("related_fragments") or []
    # Should include chunks 0,1,2 with 1 marked as target
    assert [f.get("chunk_index") for f in rel] == [0, 1, 2]
    assert any(f.get("is_target_chunk") and f.get("chunk_index") == 1 for f in rel)

import json
from array import array
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from redis_sre_agent.core.config import Settings
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import create_indices, get_knowledge_index
from redis_sre_agent.knowledge_pack.builder import (
    build_knowledge_pack,
    compute_embedding_fingerprint,
    compute_schema_hash,
)
from redis_sre_agent.knowledge_pack.checksums import (
    build_checksums_for_directory,
    write_checksums_file,
)
from redis_sre_agent.knowledge_pack.loader import load_knowledge_pack
from redis_sre_agent.knowledge_pack.models import KnowledgePackManifest, RecordCounts


def _write_artifact_batch(root: Path, batch_date: str) -> None:
    batch_root = root / batch_date
    shared_dir = batch_root / "shared"
    shared_dir.mkdir(parents=True)
    (batch_root / "batch_manifest.json").write_text(
        json.dumps({"batch_date": batch_date, "total_documents": 1}) + "\n",
        encoding="utf-8",
    )
    (shared_dir / "doc.json").write_text(
        json.dumps(
            {
                "title": "Release Doc",
                "content": "Built from a pack",
                "source_url": "source_documents/shared/release-doc.md",
                "source": "source_documents/shared/release-doc.md",
                "category": "shared",
                "doc_type": "knowledge",
                "severity": "medium",
                "content_hash": "content-hash-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_build_and_restore_knowledge_pack_round_trip(
    async_redis_client, test_settings, tmp_path
):
    await create_indices(config=test_settings)
    index = await get_knowledge_index(config=test_settings)
    vector = array("f", [0.0] * test_settings.vector_dim).tobytes()
    document_hash = "dochash-roundtrip"
    chunk_key = RedisKeys.knowledge_chunk(document_hash, 0)

    await index.load(
        data=[
            {
                "id": "chunk-1",
                "title": "Release Doc",
                "content": "Built from a pack",
                "source": "source_documents/shared/release-doc.md",
                "category": "shared",
                "severity": "medium",
                "document_hash": document_hash,
                "chunk_index": 0,
                "total_chunks": 1,
                "vector": vector,
            }
        ],
        id_field="id",
        keys=[chunk_key],
    )
    await async_redis_client.hset(
        RedisKeys.knowledge_document_meta(document_hash),
        mapping={"document_hash": document_hash, "content_hash": "content-hash-1"},
    )
    await async_redis_client.hset(
        RedisKeys.knowledge_source_meta("sourcehash-1"),
        mapping={
            "source_document_path": "shared/release-doc.md",
            "document_hash": document_hash,
        },
    )

    artifacts_path = tmp_path / "artifacts"
    batch_date = "2026-05-12"
    _write_artifact_batch(artifacts_path, batch_date)

    pack_path = tmp_path / "dist" / "knowledge-pack.zip"
    build_result = await build_knowledge_pack(
        batch_date=batch_date,
        output_path=pack_path,
        artifacts_path=artifacts_path,
        release_tag="v9.9.9",
        repo_sha="deadbeef",
        scrapers_run=["source_documents", "redis_docs_local", "redis_kb", "redis_cloud_api"],
        config=test_settings,
    )

    assert pack_path.exists()
    assert build_result["record_counts"]["chunk_records"] == 1

    await async_redis_client.flushdb()
    await create_indices(config=test_settings)

    result = await load_knowledge_pack(
        pack_path=pack_path,
        mode="restore",
        artifacts_path=tmp_path / "restored-artifacts",
        config=test_settings,
    )

    assert result["mode"] == "restore"
    assert result["chunk_records_loaded"] == 1
    assert await async_redis_client.exists(chunk_key) == 1
    assert await async_redis_client.exists(RedisKeys.knowledge_pack_active()) == 1


def _write_incompatible_pack(tmp_path: Path) -> Path:
    manifest = KnowledgePackManifest(
        pack_id="airgap-pack",
        release_tag="v9.9.9",
        created_at="2026-05-12T00:00:00+00:00",
        batch_date="2026-05-12",
        schema_hash=compute_schema_hash(1536),
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        vector_dim=1536,
        embedding_fingerprint=compute_embedding_fingerprint(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            vector_dim=1536,
            schema_hash=compute_schema_hash(1536),
        ),
        record_counts=RecordCounts(
            artifact_documents=1,
            chunk_records=0,
            document_meta_records=0,
            source_meta_records=0,
        ),
    )
    root = tmp_path / "pack"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    restore_dir = root / "restore"
    restore_dir.mkdir()
    for name in (
        "knowledge_chunks.ndjson",
        "knowledge_document_meta.ndjson",
        "knowledge_source_meta.ndjson",
    ):
        (restore_dir / name).write_text("", encoding="utf-8")
    (restore_dir / "active_pack_registry.json").write_text("{}", encoding="utf-8")

    _write_artifact_batch(root / "artifacts", manifest.batch_date)
    checksums = build_checksums_for_directory(root, exclude={"checksums.txt"})
    write_checksums_file(root / "checksums.txt", checksums)

    zip_path = tmp_path / "airgap-pack.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            archive.write(path, path.relative_to(root).as_posix())
    return zip_path


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auto_mode_falls_back_to_reingest(
    async_redis_client, test_settings, tmp_path, monkeypatch
):
    pack_path = _write_incompatible_pack(tmp_path)
    airgap_settings = Settings(
        redis_url=test_settings.redis_url,
        embedding_provider="local",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        vector_dim=384,
    )

    class FakeOrchestrator:
        def __init__(
            self, artifacts_path: str, config=None, knowledge_settings=None, scrapers=None
        ):
            self.artifacts_path = artifacts_path
            self.knowledge_settings = knowledge_settings

        async def run_ingestion_pipeline(self, batch_date: str):
            assert self.knowledge_settings == airgap_settings
            index = await get_knowledge_index(config=airgap_settings)
            vector = array("f", [0.0] * airgap_settings.vector_dim).tobytes()
            chunk_key = RedisKeys.knowledge_chunk("dochash-fallback", 0)
            await index.load(
                data=[
                    {
                        "id": "chunk-fallback",
                        "title": "Fallback Doc",
                        "content": "Loaded via reingest fallback",
                        "source": "source_documents/shared/release-doc.md",
                        "category": "shared",
                        "severity": "medium",
                        "document_hash": "dochash-fallback",
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "vector": vector,
                    }
                ],
                id_field="id",
                keys=[chunk_key],
            )
            await async_redis_client.hset(
                RedisKeys.knowledge_document_meta("dochash-fallback"),
                mapping={"document_hash": "dochash-fallback"},
            )
            await async_redis_client.hset(
                RedisKeys.knowledge_source_meta("sourcehash-fallback"),
                mapping={"source_document_path": "shared/release-doc.md"},
            )
            return {"success": True, "documents_processed": 1, "chunks_indexed": 1}

    monkeypatch.setattr(
        "redis_sre_agent.knowledge_pack.loader.PipelineOrchestrator", FakeOrchestrator
    )

    result = await load_knowledge_pack(
        pack_path=pack_path,
        mode="auto",
        artifacts_path=tmp_path / "unpacked-artifacts",
        config=airgap_settings,
    )

    assert result["mode"] == "reingest"
    assert result["ingestion"]["chunks_indexed"] == 1
    assert await async_redis_client.exists(RedisKeys.knowledge_pack_active()) == 1

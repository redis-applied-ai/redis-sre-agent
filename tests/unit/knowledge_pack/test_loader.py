import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from redis_sre_agent.core.config import Settings
from redis_sre_agent.knowledge_pack.builder import (
    compute_embedding_fingerprint,
    compute_schema_hash,
)
from redis_sre_agent.knowledge_pack.checksums import (
    build_checksums_for_directory,
    write_checksums_file,
)
from redis_sre_agent.knowledge_pack.loader import (
    _extract_artifacts_from_pack,
    auto_load_configured_knowledge_pack,
    get_restore_compatibility,
    inspect_knowledge_pack,
    load_knowledge_pack,
)
from redis_sre_agent.knowledge_pack.models import (
    KnowledgePackInspection,
    KnowledgePackManifest,
    RecordCounts,
)


def _make_manifest(*, provider: str, model: str, vector_dim: int) -> KnowledgePackManifest:
    schema_hash = compute_schema_hash(vector_dim)
    return KnowledgePackManifest(
        pack_id="pack-123",
        created_at="2026-05-12T00:00:00+00:00",
        batch_date="2026-05-12",
        schema_hash=schema_hash,
        embedding_provider=provider,
        embedding_model=model,
        vector_dim=vector_dim,
        embedding_fingerprint=compute_embedding_fingerprint(
            embedding_provider=provider,
            embedding_model=model,
            vector_dim=vector_dim,
            schema_hash=schema_hash,
        ),
        record_counts=RecordCounts(
            artifact_documents=1,
            chunk_records=1,
            document_meta_records=1,
            source_meta_records=1,
        ),
    )


def _write_pack_zip(tmp_path: Path, manifest: KnowledgePackManifest) -> Path:
    root = tmp_path / "pack"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifacts_dir = root / "artifacts" / manifest.batch_date / "shared"
    artifacts_dir.mkdir(parents=True)
    (root / "artifacts" / manifest.batch_date / "batch_manifest.json").write_text(
        json.dumps({"batch_date": manifest.batch_date, "total_documents": 1}) + "\n",
        encoding="utf-8",
    )
    (artifacts_dir / "doc.json").write_text(
        json.dumps(
            {
                "title": "Doc",
                "content": "Body",
                "source_url": "https://example.invalid/doc",
                "source": "source_documents/shared/doc.md",
                "category": "shared",
                "doc_type": "knowledge",
                "severity": "medium",
                "content_hash": "hash-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    restore_dir = root / "restore"
    restore_dir.mkdir()
    for name, payload in {
        "knowledge_chunks.ndjson": "{}\n",
        "knowledge_document_meta.ndjson": "{}\n",
        "knowledge_source_meta.ndjson": "{}\n",
        "active_pack_registry.json": "{}\n",
    }.items():
        (restore_dir / name).write_text(payload, encoding="utf-8")

    checksums = build_checksums_for_directory(root, exclude={"checksums.txt"})
    write_checksums_file(root / "checksums.txt", checksums)

    zip_path = tmp_path / "pack.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            archive.write(path, path.relative_to(root).as_posix())
    return zip_path


def test_get_restore_compatibility_matches_current_runtime():
    config = Settings(
        redis_url="redis://localhost:6379/0",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        vector_dim=1536,
    )
    manifest = _make_manifest(
        provider="openai",
        model="text-embedding-3-small",
        vector_dim=1536,
    )

    compatible, reason = get_restore_compatibility(manifest, config=config)

    assert compatible is True
    assert "match the pack fingerprint" in reason


def test_inspect_knowledge_pack_reports_incompatible_runtime(tmp_path: Path):
    config = Settings(
        redis_url="redis://localhost:6379/0",
        embedding_provider="local",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        vector_dim=384,
    )
    manifest = _make_manifest(
        provider="openai",
        model="text-embedding-3-small",
        vector_dim=1536,
    )
    zip_path = _write_pack_zip(tmp_path, manifest)

    inspection = inspect_knowledge_pack(zip_path, config=config)

    assert inspection.checksums_verified is True
    assert inspection.restore_compatible is False
    assert "do not match the pack fingerprint" in inspection.compatibility_reason


@pytest.mark.asyncio
async def test_load_knowledge_pack_auto_prefers_restore_when_compatible(
    tmp_path: Path, monkeypatch
):
    manifest = _make_manifest(
        provider="openai",
        model="text-embedding-3-small",
        vector_dim=1536,
    )
    inspection = KnowledgePackInspection(
        manifest=manifest,
        checksums_verified=True,
        restore_compatible=True,
        compatibility_reason="compatible",
    )
    restore_calls: list[dict] = []

    async def fake_restore(**kwargs):
        restore_calls.append(kwargs)
        return {"mode": "restore", "chunk_records_loaded": 1}

    async def fail_reingest(**kwargs):
        raise AssertionError("reingest should not run")

    monkeypatch.setattr(
        "redis_sre_agent.knowledge_pack.loader.inspect_knowledge_pack",
        lambda *args, **kwargs: inspection,
    )
    monkeypatch.setattr("redis_sre_agent.knowledge_pack.loader._restore_from_pack", fake_restore)
    monkeypatch.setattr("redis_sre_agent.knowledge_pack.loader._reingest_from_pack", fail_reingest)

    result = await load_knowledge_pack(
        pack_path=tmp_path / "pack.zip",
        mode="auto",
        artifacts_path=tmp_path / "artifacts",
        config=Settings(redis_url="redis://localhost:6379/0"),
    )

    assert result["mode"] == "restore"
    assert restore_calls


@pytest.mark.asyncio
async def test_auto_load_configured_knowledge_pack_skips_nonempty_index(
    tmp_path: Path, monkeypatch
):
    pack_path = tmp_path / "pack.zip"
    pack_path.write_text("placeholder", encoding="utf-8")
    config = Settings(
        redis_url="redis://localhost:6379/0",
        knowledge_pack_auto_load=True,
        knowledge_pack_path=pack_path,
    )

    async def fake_index_stats(cfg):
        return {"exists": True, "num_docs": 3}

    monkeypatch.setattr(
        "redis_sre_agent.knowledge_pack.loader._knowledge_index_stats", fake_index_stats
    )

    result = await auto_load_configured_knowledge_pack(config)

    assert result == {
        "status": "skipped",
        "reason": "knowledge_index_not_empty",
        "num_docs": 3,
    }


@pytest.mark.asyncio
async def test_auto_load_configured_knowledge_pack_uses_configured_artifacts_path(
    tmp_path: Path, monkeypatch
):
    pack_path = tmp_path / "pack.zip"
    pack_path.write_text("placeholder", encoding="utf-8")
    config = Settings(
        redis_url="redis://localhost:6379/0",
        knowledge_pack_auto_load=True,
        knowledge_pack_path=pack_path,
        knowledge_pack_load_mode="auto",
        knowledge_pack_artifacts_path=tmp_path / "knowledge-pack-artifacts",
    )

    async def fake_index_stats(cfg):
        return {"exists": False, "num_docs": 0}

    load_calls: list[dict[str, object]] = []

    async def fake_load(**kwargs):
        load_calls.append(kwargs)
        return {"mode": "reingest", "pack_id": "pack-123"}

    monkeypatch.setattr(
        "redis_sre_agent.knowledge_pack.loader._knowledge_index_stats", fake_index_stats
    )
    monkeypatch.setattr("redis_sre_agent.knowledge_pack.loader.load_knowledge_pack", fake_load)

    result = await auto_load_configured_knowledge_pack(config)

    assert result["status"] == "loaded"
    assert len(load_calls) == 1
    assert load_calls[0]["artifacts_path"] == config.knowledge_pack_artifacts_path


@pytest.mark.asyncio
async def test_extract_artifacts_from_pack_rejects_path_traversal(tmp_path: Path):
    manifest = _make_manifest(
        provider="openai",
        model="text-embedding-3-small",
        vector_dim=1536,
    )
    root = tmp_path / "pack"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    restore_dir = root / "restore"
    restore_dir.mkdir()
    for name, payload in {
        "knowledge_chunks.ndjson": "{}\n",
        "knowledge_document_meta.ndjson": "{}\n",
        "knowledge_source_meta.ndjson": "{}\n",
        "active_pack_registry.json": "{}\n",
    }.items():
        (restore_dir / name).write_text(payload, encoding="utf-8")
    checksums = build_checksums_for_directory(root, exclude={"checksums.txt"})
    write_checksums_file(root / "checksums.txt", checksums)

    zip_path = tmp_path / "malicious-pack.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            archive.write(path, path.relative_to(root).as_posix())
        archive.writestr("artifacts/../../escape.txt", "nope")

    with pytest.raises(ValueError, match="escapes destination root"):
        await _extract_artifacts_from_pack(zip_path, tmp_path / "artifacts")

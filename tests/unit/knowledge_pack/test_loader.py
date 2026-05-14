import hashlib
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
    _materialize_registry_from_runtime_batch,
    _reingest_from_pack,
    auto_load_configured_knowledge_pack,
    get_restore_compatibility,
    inspect_knowledge_pack,
    load_knowledge_pack,
)
from redis_sre_agent.knowledge_pack.models import (
    ActiveKnowledgePackRegistry,
    KnowledgePackInspection,
    KnowledgePackManifest,
    RecordCounts,
)
from redis_sre_agent.pipelines.scraper.base import ScrapedDocument


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


def test_materialize_registry_from_runtime_batch_uses_runtime_keys(tmp_path: Path):
    manifest = _make_manifest(
        provider="openai",
        model="text-embedding-3-small",
        vector_dim=1536,
    )
    batch_root = tmp_path / manifest.batch_date / "shared"
    batch_root.mkdir(parents=True)
    (tmp_path / manifest.batch_date / "batch_manifest.json").write_text(
        json.dumps({"batch_date": manifest.batch_date, "total_documents": 2}) + "\n",
        encoding="utf-8",
    )
    (batch_root / "knowledge.json").write_text(
        json.dumps(
            {
                "title": "Runtime Doc",
                "content": "Body from artifacts",
                "source_url": "source_documents/shared/runtime-doc.md",
                "category": "shared",
                "doc_type": "knowledge",
                "severity": "medium",
                "content_hash": "stale-pack-hash",
                "metadata": {
                    "source_document_path": "source_documents/shared/runtime-doc.md",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (batch_root / "skill.json").write_text(
        json.dumps(
            {
                "title": "Skill Doc",
                "content": "Ignored by knowledge-pack registry",
                "source_url": "source_documents/shared/skill.md",
                "category": "shared",
                "doc_type": "skill",
                "severity": "medium",
                "metadata": {
                    "source_document_path": "source_documents/shared/skill.md",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    config = Settings(redis_url="redis://localhost:6379/0")
    source_document_path = "source_documents/shared/runtime-doc.md"
    runtime_document_hash = ScrapedDocument.from_dict(
        {
            "title": "Runtime Doc",
            "content": "Body from artifacts",
            "source_url": source_document_path,
            "category": "shared",
            "doc_type": "knowledge",
            "severity": "medium",
            "metadata": {
                "source_document_path": source_document_path,
            },
        }
    ).content_hash
    source_path_hash = hashlib.sha256(source_document_path.encode("utf-8")).hexdigest()[:16]
    registry = _materialize_registry_from_runtime_batch(
        artifacts_path=tmp_path,
        manifest=manifest,
        config=config,
    )

    assert registry.pack_id == manifest.pack_id
    assert registry.release_tag == manifest.release_tag
    assert registry.pack_profile == manifest.pack_profile
    assert registry.batch_date == manifest.batch_date
    assert registry.chunk_keys == [f"sre_knowledge:{runtime_document_hash}:chunk:0"]
    assert registry.document_meta_keys == [f"sre_knowledge_meta:{runtime_document_hash}"]
    assert registry.source_meta_keys == [f"sre_knowledge_meta:source:{source_path_hash}"]


@pytest.mark.asyncio
async def test_reingest_keeps_active_pack_keys_when_ingestion_fails(tmp_path: Path, monkeypatch):
    manifest = _make_manifest(
        provider="openai",
        model="text-embedding-3-small",
        vector_dim=1536,
    )
    active_registry = ActiveKnowledgePackRegistry(
        pack_id="old-pack",
        loaded_at="2026-05-12T00:00:00+00:00",
        batch_date="2026-05-12",
        schema_hash=manifest.schema_hash,
        embedding_fingerprint=manifest.embedding_fingerprint,
        chunk_keys=["old-chunk"],
        document_meta_keys=["old-meta"],
        source_meta_keys=[],
    )
    replacement_registry = ActiveKnowledgePackRegistry(
        pack_id=manifest.pack_id,
        loaded_at="2026-05-13T00:00:00+00:00",
        batch_date=manifest.batch_date,
        schema_hash=manifest.schema_hash,
        embedding_fingerprint=manifest.embedding_fingerprint,
        chunk_keys=["new-chunk"],
        document_meta_keys=["new-meta"],
        source_meta_keys=[],
    )
    deleted_keys: list[str] = []
    stored_registries: list[str] = []

    class FakeRedis:
        async def delete(self, *keys):
            deleted_keys.extend(keys)
            return len(keys)

        async def set(self, key, value):
            stored_registries.append(f"{key}:{value}")

    class FakeIndex:
        client = FakeRedis()

    class FailingOrchestrator:
        def __init__(self, artifacts_path: str, knowledge_settings):
            self.artifacts_path = artifacts_path
            self.knowledge_settings = knowledge_settings

        async def run_ingestion_pipeline(self, batch_date: str):
            raise RuntimeError("ingestion failed")

    async def noop_create_indices(**kwargs):
        return None

    async def fake_get_index(**kwargs):
        return FakeIndex()

    async def fake_index_stats(config):
        return {"exists": True, "num_docs": 2}

    async def fake_load_registry(redis_client):
        return active_registry

    async def fake_extract_artifacts(pack_path: Path, artifacts_path: Path):
        return manifest.batch_date

    monkeypatch.setattr("redis_sre_agent.knowledge_pack.loader.create_indices", noop_create_indices)
    monkeypatch.setattr("redis_sre_agent.knowledge_pack.loader.get_knowledge_index", fake_get_index)
    monkeypatch.setattr(
        "redis_sre_agent.knowledge_pack.loader._knowledge_index_stats", fake_index_stats
    )
    monkeypatch.setattr("redis_sre_agent.knowledge_pack.loader._load_registry", fake_load_registry)
    monkeypatch.setattr(
        "redis_sre_agent.knowledge_pack.loader._extract_artifacts_from_pack",
        fake_extract_artifacts,
    )
    monkeypatch.setattr(
        "redis_sre_agent.knowledge_pack.loader._materialize_registry_from_runtime_batch",
        lambda **kwargs: replacement_registry,
    )
    monkeypatch.setattr(
        "redis_sre_agent.knowledge_pack.loader.PipelineOrchestrator",
        FailingOrchestrator,
    )

    with pytest.raises(RuntimeError, match="ingestion failed"):
        await _reingest_from_pack(
            pack_path=tmp_path / "pack.zip",
            manifest=manifest,
            artifacts_path=tmp_path / "artifacts",
            replace_existing=False,
            config=Settings(redis_url="redis://localhost:6379/0"),
        )

    assert deleted_keys == ["new-chunk", "new-meta"]
    assert "old-chunk" not in deleted_keys
    assert "old-meta" not in deleted_keys
    assert stored_registries == []

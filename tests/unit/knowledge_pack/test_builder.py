import json
from pathlib import Path
from unittest.mock import Mock

from redis_sre_agent.knowledge_pack.builder import (
    _copy_batch_artifacts,
    compute_embedding_fingerprint,
    compute_schema_hash,
    resolve_pack_embedding_profile,
)
from redis_sre_agent.knowledge_pack.models import (
    AIRGAP_EMBEDDING_MODEL,
    AIRGAP_EMBEDDING_PROVIDER,
    AIRGAP_PACK_PROFILE,
    AIRGAP_VECTOR_DIM,
    STANDARD_PACK_PROFILE,
)


def test_compute_schema_hash_changes_with_vector_dim():
    small = compute_schema_hash(384)
    large = compute_schema_hash(1536)

    assert small
    assert large
    assert small != large


def test_compute_embedding_fingerprint_changes_with_embedding_settings():
    schema_hash = compute_schema_hash(1536)
    baseline = compute_embedding_fingerprint(
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        vector_dim=1536,
        schema_hash=schema_hash,
    )
    changed_model = compute_embedding_fingerprint(
        embedding_provider="openai",
        embedding_model="text-embedding-3-large",
        vector_dim=1536,
        schema_hash=schema_hash,
    )

    assert baseline != changed_model


def test_resolve_pack_embedding_profile_uses_runtime_settings_by_default():
    config = Mock(
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        vector_dim=1536,
    )

    profile = resolve_pack_embedding_profile(config=config)

    assert profile == {
        "pack_profile": STANDARD_PACK_PROFILE,
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "vector_dim": 1536,
    }


def test_resolve_pack_embedding_profile_uses_airgap_defaults():
    profile = resolve_pack_embedding_profile(profile_name=AIRGAP_PACK_PROFILE)

    assert profile == {
        "pack_profile": AIRGAP_PACK_PROFILE,
        "embedding_provider": AIRGAP_EMBEDDING_PROVIDER,
        "embedding_model": AIRGAP_EMBEDDING_MODEL,
        "vector_dim": AIRGAP_VECTOR_DIM,
    }


def test_copy_batch_artifacts_uses_batch_manifest_document_count(tmp_path: Path):
    source_batch_path = tmp_path / "2026-05-12"
    shared_dir = source_batch_path / "shared"
    shared_dir.mkdir(parents=True)
    (source_batch_path / "batch_manifest.json").write_text(
        json.dumps({"batch_date": "2026-05-12", "total_documents": 7}) + "\n",
        encoding="utf-8",
    )
    (shared_dir / "doc.json").write_text(
        json.dumps({"title": "Doc", "content": "Body"}) + "\n",
        encoding="utf-8",
    )

    copied_count = _copy_batch_artifacts(source_batch_path, tmp_path / "pack-root")

    assert copied_count == 7


def test_copy_batch_artifacts_excludes_batch_manifest_from_fallback_count(tmp_path: Path):
    source_batch_path = tmp_path / "2026-05-12"
    shared_dir = source_batch_path / "shared"
    shared_dir.mkdir(parents=True)
    (source_batch_path / "batch_manifest.json").write_text("{invalid-json", encoding="utf-8")
    (shared_dir / "doc-1.json").write_text("{}", encoding="utf-8")
    (shared_dir / "doc-2.json").write_text("{}", encoding="utf-8")

    copied_count = _copy_batch_artifacts(source_batch_path, tmp_path / "pack-root")

    assert copied_count == 2

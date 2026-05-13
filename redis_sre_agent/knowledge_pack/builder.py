"""Build release knowledge-pack zip artifacts from live Redis knowledge data."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zipfile import ZIP_DEFLATED, ZipFile

from redis_sre_agent.core.config import Settings, settings
from redis_sre_agent.core.redis import SRE_KNOWLEDGE_SCHEMA, get_knowledge_index

from .checksums import build_checksums_for_directory, write_checksums_file
from .models import (
    AIRGAP_EMBEDDING_MODEL,
    AIRGAP_EMBEDDING_PROVIDER,
    AIRGAP_PACK_PROFILE,
    AIRGAP_VECTOR_DIM,
    KNOWLEDGE_PACK_ACTIVE_REGISTRY_FILE,
    KNOWLEDGE_PACK_CHUNK_RECORDS_FILE,
    KNOWLEDGE_PACK_DOCUMENT_META_FILE,
    KNOWLEDGE_PACK_SOURCE_META_FILE,
    STANDARD_PACK_PROFILE,
    ActiveKnowledgePackRegistry,
    KnowledgePackManifest,
    RecordCounts,
)

_MANIFEST_FILE = "manifest.json"
_CHECKSUMS_FILE = "checksums.txt"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_rev_parse(target: str, cwd: Path) -> str | None:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", target], cwd=cwd, text=True).strip()
            or None
        )
    except Exception:
        return None


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def build_knowledge_schema(vector_dim: int) -> dict[str, Any]:
    """Return the knowledge schema with an explicit vector dimension."""
    schema = json.loads(json.dumps(SRE_KNOWLEDGE_SCHEMA))
    for field in schema.get("fields", []):
        if field.get("name") == "vector":
            field.setdefault("attrs", {})["dims"] = vector_dim
    return schema


def compute_schema_hash(vector_dim: int) -> str:
    """Return a stable schema hash for one vector dimension."""
    import hashlib

    return hashlib.sha256(
        _json_dumps(build_knowledge_schema(vector_dim)).encode("utf-8")
    ).hexdigest()


def compute_embedding_fingerprint(
    *,
    embedding_provider: str,
    embedding_model: str,
    vector_dim: int,
    schema_hash: str,
) -> str:
    """Return a stable fingerprint describing restore compatibility."""
    import hashlib

    payload = _json_dumps(
        {
            "embedding_provider": embedding_provider,
            "embedding_model": embedding_model,
            "vector_dim": vector_dim,
            "schema_hash": schema_hash,
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_pack_embedding_profile(
    *,
    config: Optional[Settings] = None,
    profile_name: str = STANDARD_PACK_PROFILE,
) -> dict[str, Any]:
    """Return the embedding settings recorded in the pack manifest."""
    cfg = config or settings
    normalized_profile = profile_name.strip().lower()
    if normalized_profile == AIRGAP_PACK_PROFILE:
        return {
            "pack_profile": AIRGAP_PACK_PROFILE,
            "embedding_provider": AIRGAP_EMBEDDING_PROVIDER,
            "embedding_model": AIRGAP_EMBEDDING_MODEL,
            "vector_dim": AIRGAP_VECTOR_DIM,
        }
    return {
        "pack_profile": STANDARD_PACK_PROFILE,
        "embedding_provider": cfg.embedding_provider,
        "embedding_model": cfg.embedding_model,
        "vector_dim": cfg.vector_dim,
    }


def _normalize_hash_mapping(raw_mapping: dict[Any, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw_mapping.items():
        normalized_key = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        normalized[normalized_key] = value
    return normalized


def _normalize_chunk_payload(raw_mapping: dict[Any, Any]) -> tuple[dict[str, Any], str]:
    mapping = _normalize_hash_mapping(raw_mapping)
    vector = mapping.pop("vector", b"")
    if isinstance(vector, str):
        vector_bytes = vector.encode("utf-8")
    else:
        vector_bytes = bytes(vector)

    payload: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, bytes):
            payload[key] = value.decode("utf-8")
        else:
            payload[key] = value
    return payload, base64.b64encode(vector_bytes).decode("ascii")


def _normalize_meta_mapping(raw_mapping: dict[Any, Any]) -> dict[str, str]:
    mapping = _normalize_hash_mapping(raw_mapping)
    normalized: dict[str, str] = {}
    for key, value in mapping.items():
        if isinstance(value, bytes):
            normalized[key] = value.decode("utf-8")
        else:
            normalized[key] = str(value)
    return normalized


async def _scan_chunk_records(redis_client: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    async for key in redis_client.scan_iter(match="sre_knowledge:*:chunk:*"):
        normalized_key = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        raw_mapping = await redis_client.hgetall(key)
        payload, vector_b64 = _normalize_chunk_payload(raw_mapping)
        records.append({"key": normalized_key, "payload": payload, "vector_b64": vector_b64})
    return sorted(records, key=lambda item: item["key"])


async def _scan_meta_records(redis_client: Any, pattern: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    async for key in redis_client.scan_iter(match=pattern):
        normalized_key = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        raw_mapping = await redis_client.hgetall(key)
        records.append({"key": normalized_key, "mapping": _normalize_meta_mapping(raw_mapping)})
    return sorted(records, key=lambda item: item["key"])


def _write_ndjson(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _copy_batch_artifacts(source_batch_path: Path, destination_root: Path) -> int:
    target_batch_path = destination_root / "artifacts" / source_batch_path.name
    shutil.copytree(source_batch_path, target_batch_path)
    manifest_path = target_batch_path / "batch_manifest.json"
    if manifest_path.exists():
        try:
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            total_documents = manifest_payload.get("total_documents")
            if isinstance(total_documents, int) and total_documents >= 0:
                return total_documents
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    return sum(
        1
        for path in target_batch_path.rglob("*.json")
        if path.is_file() and path.name != "batch_manifest.json"
    )


def _build_source_revisions(repo_root: Path, repo_sha: str | None) -> dict[str, Any]:
    source_revisions: dict[str, Any] = {}
    if repo_sha:
        source_revisions["repo_sha"] = repo_sha
        source_revisions["source_documents_git_sha"] = repo_sha

    redis_docs_root = repo_root / "redis-docs"
    if redis_docs_root.exists():
        redis_docs_sha = _git_rev_parse("HEAD", redis_docs_root)
        if redis_docs_sha:
            source_revisions["redis_docs_commit"] = redis_docs_sha

    redis_cloud_api_spec = repo_root / "source_documents" / "cloud" / "redis-cloud-api-spec.json"
    if redis_cloud_api_spec.exists():
        source_revisions["redis_cloud_api_source"] = str(
            redis_cloud_api_spec.relative_to(repo_root)
        )

    return source_revisions


def _zip_directory(source_root: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(
            candidate for candidate in source_root.rglob("*") if candidate.is_file()
        ):
            archive.write(path, path.relative_to(source_root).as_posix())


async def build_knowledge_pack(
    *,
    batch_date: str,
    output_path: Path,
    artifacts_path: Path,
    release_tag: str | None = None,
    repo_sha: str | None = None,
    scrapers_run: list[str] | None = None,
    profile_name: str = STANDARD_PACK_PROFILE,
    config: Optional[Settings] = None,
) -> dict[str, Any]:
    """Build a knowledge-pack zip from live knowledge-index state and raw artifacts."""
    cfg = config or settings
    repo_root = Path.cwd()
    source_batch_path = artifacts_path / batch_date
    if not source_batch_path.exists():
        raise ValueError(f"Artifact batch not found: {source_batch_path}")
    if not (source_batch_path / "batch_manifest.json").exists():
        raise ValueError(
            f"Artifact batch manifest not found: {source_batch_path / 'batch_manifest.json'}"
        )

    manifest_profile = resolve_pack_embedding_profile(config=cfg, profile_name=profile_name)
    schema_hash = compute_schema_hash(manifest_profile["vector_dim"])
    embedding_fingerprint = compute_embedding_fingerprint(
        embedding_provider=manifest_profile["embedding_provider"],
        embedding_model=manifest_profile["embedding_model"],
        vector_dim=manifest_profile["vector_dim"],
        schema_hash=schema_hash,
    )

    effective_repo_sha = repo_sha or _git_rev_parse("HEAD", repo_root)
    source_revisions = _build_source_revisions(repo_root, effective_repo_sha)

    index = await get_knowledge_index(config=cfg)
    redis_client = index.client
    chunk_records = await _scan_chunk_records(redis_client)
    document_meta_records = await _scan_meta_records(redis_client, pattern="sre_knowledge_meta:*")
    source_meta_records = [
        record
        for record in document_meta_records
        if record["key"].startswith("sre_knowledge_meta:source:")
    ]
    document_meta_records = [
        record
        for record in document_meta_records
        if not record["key"].startswith("sre_knowledge_meta:source:")
    ]

    if not chunk_records:
        raise ValueError(
            "Knowledge index is empty; ingest the target batch before building a pack."
        )

    pack_id = uuid.uuid4().hex
    active_registry = ActiveKnowledgePackRegistry(
        pack_id=pack_id,
        release_tag=release_tag,
        pack_profile=manifest_profile["pack_profile"],
        loaded_at=_utcnow(),
        batch_date=batch_date,
        schema_hash=schema_hash,
        embedding_fingerprint=embedding_fingerprint,
        chunk_keys=[record["key"] for record in chunk_records],
        document_meta_keys=[record["key"] for record in document_meta_records],
        source_meta_keys=[record["key"] for record in source_meta_records],
    )

    with tempfile.TemporaryDirectory(prefix="knowledge-pack-build-") as tmpdir:
        root = Path(tmpdir)
        artifact_documents = _copy_batch_artifacts(source_batch_path, root)
        _write_ndjson(root / KNOWLEDGE_PACK_CHUNK_RECORDS_FILE, chunk_records)
        _write_ndjson(root / KNOWLEDGE_PACK_DOCUMENT_META_FILE, document_meta_records)
        _write_ndjson(root / KNOWLEDGE_PACK_SOURCE_META_FILE, source_meta_records)
        _write_json(root / KNOWLEDGE_PACK_ACTIVE_REGISTRY_FILE, active_registry.model_dump())

        manifest = KnowledgePackManifest(
            pack_id=pack_id,
            pack_profile=manifest_profile["pack_profile"],
            release_tag=release_tag,
            repo_sha=effective_repo_sha,
            created_at=_utcnow(),
            batch_date=batch_date,
            schema_hash=schema_hash,
            embedding_provider=manifest_profile["embedding_provider"],
            embedding_model=manifest_profile["embedding_model"],
            vector_dim=manifest_profile["vector_dim"],
            embedding_fingerprint=embedding_fingerprint,
            scrapers_run=scrapers_run or [],
            source_documents_git_sha=effective_repo_sha,
            source_revisions=source_revisions,
            record_counts=RecordCounts(
                artifact_documents=artifact_documents,
                chunk_records=len(chunk_records),
                document_meta_records=len(document_meta_records),
                source_meta_records=len(source_meta_records),
            ),
        )
        _write_json(root / _MANIFEST_FILE, manifest.model_dump())

        checksums = build_checksums_for_directory(root, exclude={_CHECKSUMS_FILE})
        write_checksums_file(root / _CHECKSUMS_FILE, checksums)
        _zip_directory(root, output_path)

    return {
        "pack_id": pack_id,
        "output_path": str(output_path),
        "batch_date": batch_date,
        "pack_profile": manifest_profile["pack_profile"],
        "record_counts": manifest.record_counts.model_dump(),
        "embedding_fingerprint": embedding_fingerprint,
    }

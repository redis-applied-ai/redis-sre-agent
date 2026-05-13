"""Inspect and load knowledge-pack zip assets."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from zipfile import ZipFile

from redis_sre_agent.core.config import Settings, settings
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import create_indices, get_knowledge_index
from redis_sre_agent.pipelines.orchestrator import PipelineOrchestrator

from .builder import compute_embedding_fingerprint, compute_schema_hash
from .checksums import verify_zip_checksums
from .models import (
    KNOWLEDGE_PACK_ACTIVE_REGISTRY_FILE,
    KNOWLEDGE_PACK_CHUNK_RECORDS_FILE,
    KNOWLEDGE_PACK_DOCUMENT_META_FILE,
    KNOWLEDGE_PACK_SOURCE_META_FILE,
    ActiveKnowledgePackRegistry,
    KnowledgePackInspection,
    KnowledgePackManifest,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iter_ndjson_lines(raw_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _current_embedding_fingerprint(cfg: Settings) -> str:
    schema_hash = compute_schema_hash(cfg.vector_dim)
    return compute_embedding_fingerprint(
        embedding_provider=cfg.embedding_provider,
        embedding_model=cfg.embedding_model,
        vector_dim=cfg.vector_dim,
        schema_hash=schema_hash,
    )


def get_restore_compatibility(
    manifest: KnowledgePackManifest,
    *,
    config: Optional[Settings] = None,
) -> tuple[bool, str]:
    """Return whether a pack is restore-compatible with the current runtime."""
    cfg = config or settings
    current_fingerprint = _current_embedding_fingerprint(cfg)
    if current_fingerprint == manifest.embedding_fingerprint:
        return True, "current embedding settings match the pack fingerprint"

    reason = (
        "current runtime embedding settings do not match the pack fingerprint "
        f"(runtime={cfg.embedding_provider}/{cfg.embedding_model}/{cfg.vector_dim}, "
        f"pack={manifest.embedding_provider}/{manifest.embedding_model}/{manifest.vector_dim})"
    )
    return False, reason


def inspect_knowledge_pack(
    pack_path: Path,
    *,
    verify_checksums: bool = True,
    config: Optional[Settings] = None,
) -> KnowledgePackInspection:
    """Read and optionally verify a knowledge-pack zip."""
    if verify_checksums:
        verify_zip_checksums(pack_path)

    with ZipFile(pack_path) as archive:
        manifest = KnowledgePackManifest.model_validate_json(archive.read("manifest.json"))

    compatible, reason = get_restore_compatibility(manifest, config=config)
    return KnowledgePackInspection(
        manifest=manifest,
        checksums_verified=verify_checksums,
        restore_compatible=compatible,
        compatibility_reason=reason,
    )


async def _knowledge_index_stats(cfg: Settings) -> dict[str, Any]:
    index = await get_knowledge_index(config=cfg)
    exists = await index.exists()
    if not exists:
        return {"exists": False, "num_docs": 0}

    raw_info = await index._redis_client.execute_command("FT.INFO", index.schema.index.name)
    info: dict[str, Any] = {}
    for idx in range(0, len(raw_info), 2):
        key = raw_info[idx]
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        info[str(key)] = raw_info[idx + 1]
    num_docs = info.get("num_docs", 0)
    if isinstance(num_docs, bytes):
        num_docs = num_docs.decode("utf-8")
    return {"exists": True, "num_docs": int(num_docs)}


async def _load_registry(redis_client: Any) -> ActiveKnowledgePackRegistry | None:
    payload = await redis_client.get(RedisKeys.knowledge_pack_active())
    if not payload:
        return None
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    return ActiveKnowledgePackRegistry.model_validate_json(payload)


async def _store_registry(redis_client: Any, registry: ActiveKnowledgePackRegistry) -> None:
    await redis_client.set(RedisKeys.knowledge_pack_active(), registry.model_dump_json())


async def _delete_keys(redis_client: Any, keys: Iterable[str]) -> int:
    normalized = [key for key in keys if key]
    if not normalized:
        return 0
    deleted = 0
    batch_size = 500
    for idx in range(0, len(normalized), batch_size):
        deleted += int(await redis_client.delete(*normalized[idx : idx + batch_size]))
    return deleted


async def _materialize_registry_from_live_index(
    *,
    manifest: KnowledgePackManifest,
    config: Settings,
) -> ActiveKnowledgePackRegistry:
    index = await get_knowledge_index(config=config)
    redis_client = index.client

    chunk_keys: list[str] = []
    async for key in redis_client.scan_iter(match="sre_knowledge:*:chunk:*"):
        chunk_keys.append(key.decode("utf-8") if isinstance(key, bytes) else str(key))

    document_meta_keys: list[str] = []
    source_meta_keys: list[str] = []
    async for key in redis_client.scan_iter(match="sre_knowledge_meta:*"):
        normalized_key = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        if normalized_key.startswith("sre_knowledge_meta:source:"):
            source_meta_keys.append(normalized_key)
        else:
            document_meta_keys.append(normalized_key)

    runtime_schema_hash = compute_schema_hash(config.vector_dim)
    runtime_embedding_fingerprint = compute_embedding_fingerprint(
        embedding_provider=config.embedding_provider,
        embedding_model=config.embedding_model,
        vector_dim=config.vector_dim,
        schema_hash=runtime_schema_hash,
    )

    return ActiveKnowledgePackRegistry(
        pack_id=manifest.pack_id,
        release_tag=manifest.release_tag,
        pack_profile=manifest.pack_profile,
        loaded_at=_utcnow(),
        batch_date=manifest.batch_date,
        schema_hash=runtime_schema_hash,
        embedding_fingerprint=runtime_embedding_fingerprint,
        chunk_keys=sorted(chunk_keys),
        document_meta_keys=sorted(document_meta_keys),
        source_meta_keys=sorted(source_meta_keys),
    )


async def _restore_from_pack(
    *,
    pack_path: Path,
    manifest: KnowledgePackManifest,
    replace_existing: bool,
    config: Settings,
) -> dict[str, Any]:
    compatible, reason = get_restore_compatibility(manifest, config=config)
    if not compatible:
        raise ValueError(f"Restore mode is not compatible: {reason}")

    await create_indices(config=config)
    index = await get_knowledge_index(config=config)
    redis_client = index.client

    current_index_stats = await _knowledge_index_stats(config)
    active_registry = await _load_registry(redis_client)
    deleted = {"chunk_keys": 0, "document_meta_keys": 0, "source_meta_keys": 0}

    if active_registry is not None:
        deleted["chunk_keys"] = await _delete_keys(redis_client, active_registry.chunk_keys)
        deleted["document_meta_keys"] = await _delete_keys(
            redis_client, active_registry.document_meta_keys
        )
        deleted["source_meta_keys"] = await _delete_keys(
            redis_client, active_registry.source_meta_keys
        )
    elif current_index_stats["num_docs"] > 0 and not replace_existing:
        raise ValueError(
            "Knowledge index already contains documents with no active knowledge-pack registry. "
            "Pass --replace-existing to proceed without deleting unknown keys."
        )

    with ZipFile(pack_path) as archive:
        chunk_records = _iter_ndjson_lines(
            archive.read(KNOWLEDGE_PACK_CHUNK_RECORDS_FILE).decode("utf-8")
        )
        document_meta_records = _iter_ndjson_lines(
            archive.read(KNOWLEDGE_PACK_DOCUMENT_META_FILE).decode("utf-8")
        )
        source_meta_records = _iter_ndjson_lines(
            archive.read(KNOWLEDGE_PACK_SOURCE_META_FILE).decode("utf-8")
        )
        registry_payload = ActiveKnowledgePackRegistry.model_validate_json(
            archive.read(KNOWLEDGE_PACK_ACTIVE_REGISTRY_FILE)
        )

    batch_size = 200
    for idx in range(0, len(chunk_records), batch_size):
        records_batch = chunk_records[idx : idx + batch_size]
        keys = [record["key"] for record in records_batch]
        payloads = []
        for record in records_batch:
            payload = dict(record["payload"])
            payload["vector"] = base64.b64decode(record["vector_b64"])
            payloads.append(payload)
        await index.load(data=payloads, id_field="id", keys=keys)

    async def _restore_meta_records(records: list[dict[str, Any]]) -> None:
        if not records:
            return
        for idx in range(0, len(records), batch_size):
            batch = records[idx : idx + batch_size]
            async with redis_client.pipeline(transaction=False) as pipe:
                for record in batch:
                    await pipe.hset(record["key"], mapping=record["mapping"])
                await pipe.execute()

    await _restore_meta_records(document_meta_records)
    await _restore_meta_records(source_meta_records)

    registry = ActiveKnowledgePackRegistry(
        **registry_payload.model_dump(exclude={"loaded_at"}),
        loaded_at=_utcnow(),
    )
    await _store_registry(redis_client, registry)

    return {
        "mode": "restore",
        "deleted": deleted,
        "chunk_records_loaded": len(chunk_records),
        "document_meta_records_loaded": len(document_meta_records),
        "source_meta_records_loaded": len(source_meta_records),
    }


async def _extract_artifacts_from_pack(pack_path: Path, artifacts_path: Path) -> str:
    artifacts_path.mkdir(parents=True, exist_ok=True)
    batch_date = ""
    artifacts_root = artifacts_path.resolve()
    with ZipFile(pack_path) as archive:
        for member in archive.infolist():
            if not member.filename.startswith("artifacts/") or member.is_dir():
                continue
            relative_path = Path(member.filename).relative_to("artifacts")
            if not batch_date and relative_path.parts:
                batch_date = relative_path.parts[0]
            target_path = (artifacts_root / relative_path).resolve()
            if artifacts_root not in target_path.parents and target_path != artifacts_root:
                raise ValueError(
                    f"Knowledge pack artifact path escapes destination root: {member.filename}"
                )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(archive.read(member.filename))
    if not batch_date:
        raise ValueError("Knowledge pack does not contain bundled artifacts required for reingest.")
    return batch_date


async def _reingest_from_pack(
    *,
    pack_path: Path,
    manifest: KnowledgePackManifest,
    artifacts_path: Path,
    config: Settings,
) -> dict[str, Any]:
    batch_date = await _extract_artifacts_from_pack(pack_path, artifacts_path)
    await create_indices(config=config)
    orchestrator = PipelineOrchestrator(str(artifacts_path), knowledge_settings=config)
    ingestion_result = await orchestrator.run_ingestion_pipeline(batch_date)
    index = await get_knowledge_index(config=config)
    registry = await _materialize_registry_from_live_index(manifest=manifest, config=config)
    await _store_registry(index.client, registry)
    return {
        "mode": "reingest",
        "batch_date": batch_date,
        "ingestion": ingestion_result,
    }


async def load_knowledge_pack(
    *,
    pack_path: Path,
    mode: str,
    artifacts_path: Path,
    replace_existing: bool = False,
    skip_checksums: bool = False,
    config: Optional[Settings] = None,
) -> dict[str, Any]:
    """Load a knowledge pack using restore, reingest, or auto mode."""
    cfg = config or settings
    inspection = inspect_knowledge_pack(pack_path, verify_checksums=not skip_checksums, config=cfg)
    manifest = inspection.manifest

    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"auto", "restore", "reingest"}:
        raise ValueError(f"Unsupported load mode: {mode}")

    if normalized_mode == "auto":
        normalized_mode = "restore" if inspection.restore_compatible else "reingest"

    if normalized_mode == "restore":
        result = await _restore_from_pack(
            pack_path=pack_path,
            manifest=manifest,
            replace_existing=replace_existing,
            config=cfg,
        )
    else:
        result = await _reingest_from_pack(
            pack_path=pack_path,
            manifest=manifest,
            artifacts_path=artifacts_path,
            config=cfg,
        )

    return {
        "pack_id": manifest.pack_id,
        "pack_profile": manifest.pack_profile,
        "release_tag": manifest.release_tag,
        "batch_date": manifest.batch_date,
        "checksums_verified": inspection.checksums_verified,
        "restore_compatible": inspection.restore_compatible,
        "compatibility_reason": inspection.compatibility_reason,
        **result,
    }


async def auto_load_configured_knowledge_pack(
    config: Optional[Settings] = None,
) -> dict[str, Any]:
    """Load the configured knowledge pack when auto-load is enabled and the index is empty."""
    cfg = config or settings
    if not cfg.knowledge_pack_auto_load:
        return {"status": "skipped", "reason": "knowledge_pack_auto_load_disabled"}
    if cfg.knowledge_pack_path is None:
        return {"status": "skipped", "reason": "knowledge_pack_path_not_configured"}

    pack_path = Path(cfg.knowledge_pack_path).expanduser()
    if not pack_path.exists():
        return {
            "status": "skipped",
            "reason": "knowledge_pack_path_missing",
            "path": str(pack_path),
        }

    index_stats = await _knowledge_index_stats(cfg)
    if index_stats["num_docs"] > 0:
        return {
            "status": "skipped",
            "reason": "knowledge_index_not_empty",
            "num_docs": index_stats["num_docs"],
        }

    result = await load_knowledge_pack(
        pack_path=pack_path,
        mode=cfg.knowledge_pack_load_mode,
        artifacts_path=cfg.knowledge_pack_artifacts_path,
        replace_existing=False,
        skip_checksums=False,
        config=cfg,
    )
    return {"status": "loaded", **result}

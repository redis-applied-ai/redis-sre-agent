"""Typed models for knowledge-pack manifests and registry payloads."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

PACK_FORMAT_VERSION = 1
KNOWLEDGE_PACK_KIND = "knowledge_pack"
STANDARD_PACK_PROFILE = "runtime"
AIRGAP_PACK_PROFILE = "airgap"
AIRGAP_EMBEDDING_PROVIDER = "local"
AIRGAP_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
AIRGAP_VECTOR_DIM = 384


class RecordCounts(BaseModel):
    """Counts of exported records included in a knowledge pack."""

    artifact_documents: int = 0
    chunk_records: int = 0
    document_meta_records: int = 0
    source_meta_records: int = 0


class KnowledgePackManifest(BaseModel):
    """Top-level manifest stored in every knowledge pack."""

    pack_format_version: int = PACK_FORMAT_VERSION
    pack_kind: str = KNOWLEDGE_PACK_KIND
    pack_id: str
    pack_profile: Literal["runtime", "airgap"] = STANDARD_PACK_PROFILE
    release_tag: Optional[str] = None
    repo_sha: Optional[str] = None
    created_at: str
    batch_date: str
    included_corpora: list[str] = Field(default_factory=lambda: ["knowledge"])
    includes_artifacts: bool = True
    includes_restore_records: bool = True
    schema_hash: str
    embedding_provider: str
    embedding_model: str
    vector_dim: int
    embedding_fingerprint: str
    scrapers_run: list[str] = Field(default_factory=list)
    source_documents_git_sha: Optional[str] = None
    source_revisions: dict[str, Any] = Field(default_factory=dict)
    record_counts: RecordCounts


class ActiveKnowledgePackRegistry(BaseModel):
    """Redis-stored registry describing the currently active knowledge pack."""

    pack_id: str
    release_tag: Optional[str] = None
    pack_profile: Literal["runtime", "airgap"] = STANDARD_PACK_PROFILE
    loaded_at: str
    batch_date: str
    schema_hash: str
    embedding_fingerprint: str
    chunk_keys: list[str] = Field(default_factory=list)
    document_meta_keys: list[str] = Field(default_factory=list)
    source_meta_keys: list[str] = Field(default_factory=list)


class KnowledgePackInspection(BaseModel):
    """Inspection result returned by the inspect command and loader."""

    manifest: KnowledgePackManifest
    checksums_verified: bool = False
    restore_compatible: bool = False
    compatibility_reason: str = ""

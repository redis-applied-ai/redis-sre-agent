from unittest.mock import Mock

from redis_sre_agent.knowledge_pack.builder import (
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

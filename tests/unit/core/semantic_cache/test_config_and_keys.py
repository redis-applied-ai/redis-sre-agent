"""US-002: config settings + Redis key builders for the semantic cache."""

from redis_sre_agent.core.config import Settings
from redis_sre_agent.core.keys import RedisKeys


def test_semantic_cache_defaults_disabled(monkeypatch):
    # Clear ambient env (config.py load_dotenv() may have injected a local .env
    # that enables the cache for the docker stack) so this tests field defaults.
    for var in ("SEMANTIC_CACHE_ENABLED", "LANGCACHE_CACHE_ID", "LANGCACHE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    cfg = Settings(_env_file=None)
    assert cfg.semantic_cache_enabled is False
    assert cfg.semantic_cache_similarity_threshold == 0.9
    assert cfg.semantic_cache_ttl_latest_ms == 60 * 60 * 1000
    assert cfg.semantic_cache_ttl_pinned_ms == 24 * 60 * 60 * 1000
    # Credentials default to absent so from_settings refuses to build.
    assert cfg.langcache_cache_id is None
    assert cfg.langcache_api_key is None
    assert cfg.langcache_server_url.startswith("https://")


def test_langcache_secrets_are_secretstr():
    cfg = Settings(langcache_cache_id="cache-123", langcache_api_key="key-abc")
    # Secrets must not leak via repr/str.
    assert "key-abc" not in repr(cfg.langcache_api_key)
    assert cfg.langcache_api_key.get_secret_value() == "key-abc"
    assert cfg.langcache_cache_id.get_secret_value() == "cache-123"


def test_provenance_key_builders():
    assert RedisKeys.semantic_cache_provenance("abc123") == "cache_prov:abc123"
    assert RedisKeys.semantic_cache_meta("entry1") == "cache_meta:entry1"
    assert RedisKeys.semantic_cache_invalidation("abc123") == "cache_inval:abc123"

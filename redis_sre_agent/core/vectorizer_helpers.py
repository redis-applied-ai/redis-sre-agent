"""Helper functions for creating vectorizers with consistent configuration."""

import importlib
import logging
from typing import Any, Optional, Protocol

from redisvl.extensions.cache.embeddings.embeddings import EmbeddingsCache
from redisvl.utils.vectorize import HFTextVectorizer, OpenAITextVectorizer

from redis_sre_agent.core.config import Settings, settings

logger = logging.getLogger(__name__)


class VectorizerFactory(Protocol):
    """Protocol for custom vectorizer factory functions."""

    def __call__(
        self,
        *,
        provider: str,
        model: Optional[str] = None,
        config: Settings,
        cache: EmbeddingsCache,
        **kwargs,
    ) -> Any: ...


class Vectorizer(Protocol):
    """Minimal runtime contract for vectorizers used by this repo."""

    async def aembed(self, *args, **kwargs) -> Any: ...

    async def aembed_many(self, *args, **kwargs) -> Any: ...


_vectorizer_factory: Optional[VectorizerFactory] = None
_settings_vectorizer_factory: Optional[VectorizerFactory] = None
_factory_initialized: bool = False


def _resolve_factory_from_path(factory_path: str) -> VectorizerFactory:
    """Resolve a vectorizer factory from a dot-path import string."""
    module_path, _, func_name = factory_path.rpartition(".")
    if not module_path:
        raise ValueError(
            f"Invalid VECTORIZER_FACTORY path '{factory_path}': "
            "must be a dot-path like 'mypackage.module.factory_func'"
        )

    module = importlib.import_module(module_path)
    factory = getattr(module, func_name)
    if not callable(factory):
        raise ValueError(f"VECTORIZER_FACTORY '{factory_path}' is not callable")
    return factory


def _load_factory_from_config() -> Optional[VectorizerFactory]:
    """Load the vectorizer factory from global settings if specified."""
    global _settings_vectorizer_factory, _factory_initialized

    if _factory_initialized:
        return _settings_vectorizer_factory

    _factory_initialized = True
    factory_path = getattr(settings, "vectorizer_factory", None)
    if not factory_path or not isinstance(factory_path, str):
        return None

    try:
        _settings_vectorizer_factory = _resolve_factory_from_path(factory_path)
        logger.info("Loaded custom vectorizer factory from %s", factory_path)
    except Exception:
        logger.exception("Failed to load vectorizer factory from '%s'", factory_path)
        raise
    return _settings_vectorizer_factory


def set_vectorizer_factory(factory: Optional[VectorizerFactory]) -> None:
    """Register a custom vectorizer factory function."""
    global _vectorizer_factory
    _vectorizer_factory = factory


def get_vectorizer_factory() -> Optional[VectorizerFactory]:
    """Get the currently registered global vectorizer factory, if any."""
    if _vectorizer_factory is not None:
        return _vectorizer_factory
    return _settings_vectorizer_factory


def _build_embeddings_cache(config: Settings) -> EmbeddingsCache:
    """Build the shared Redis-backed embeddings cache for a vectorizer instance."""
    return EmbeddingsCache(
        name="sre_embeddings_cache",
        redis_url=config.redis_url.get_secret_value(),
        ttl=config.embeddings_cache_ttl,
    )


def _default_vectorizer_factory(
    *,
    provider: str,
    model: Optional[str] = None,
    config: Settings,
    cache: EmbeddingsCache,
    **kwargs,
) -> Any:
    """Default vectorizer factory using RedisVL's built-in vectorizers."""
    resolved_provider = provider.lower()
    resolved_model = model or config.embedding_model

    if resolved_provider == "local":
        logger.info("Using local HuggingFace vectorizer with model: %s", resolved_model)
        return HFTextVectorizer(
            model=resolved_model,
            cache=cache,
            **kwargs,
        )

    if resolved_provider == "openai":
        logger.debug(
            "Vectorizer created with embeddings cache (ttl=%ss)",
            config.embeddings_cache_ttl,
        )
        return OpenAITextVectorizer(
            model=resolved_model,
            cache=cache,
            api_config={
                "api_key": config.openai_api_key,
                **({"base_url": config.openai_base_url} if config.openai_base_url else {}),
            },
            **kwargs,
        )

    raise ValueError(
        f"Unknown embedding_provider: '{resolved_provider}'. Supported values: 'openai', 'local'"
    )


def _resolve_factory(config: Settings, *, explicit_config: bool) -> Optional[VectorizerFactory]:
    """Resolve the active factory, respecting explicit per-call config overrides."""
    if explicit_config:
        factory_path = getattr(config, "vectorizer_factory", None)
        if factory_path and isinstance(factory_path, str):
            return _resolve_factory_from_path(factory_path)
        if _vectorizer_factory is not None:
            return _vectorizer_factory
        return None

    if _vectorizer_factory is not None:
        return _vectorizer_factory

    return _load_factory_from_config()


def _validate_vectorizer_instance(vectorizer: Any) -> Vectorizer:
    """Validate that the returned object supports the async API used at runtime."""
    missing_methods = [
        method_name
        for method_name in ("aembed", "aembed_many")
        if not hasattr(vectorizer, method_name)
    ]
    if missing_methods:
        missing = ", ".join(missing_methods)
        raise TypeError(
            "Vectorizer factory must return an object that implements "
            f"the runtime async methods: {missing}"
        )
    return vectorizer


def create_vectorizer(
    config: Optional[Settings] = None,
    model: Optional[str] = None,
    **kwargs,
) -> Vectorizer:
    """Create a vectorizer using the registered factory or the default implementation."""
    cfg = config or settings
    factory = _resolve_factory(cfg, explicit_config=config is not None)
    cache = _build_embeddings_cache(cfg)
    active_factory = factory if factory is not None else _default_vectorizer_factory
    vectorizer = active_factory(
        provider=cfg.embedding_provider,
        model=model or cfg.embedding_model,
        config=cfg,
        cache=cache,
        **kwargs,
    )
    return _validate_vectorizer_instance(vectorizer)

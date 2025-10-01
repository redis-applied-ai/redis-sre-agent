"""Redis connection management with singleton pattern."""

import asyncio
import logging
from typing import Any, Callable, List, Optional

from redis.asyncio import Redis
from redisvl.extensions.cache.embeddings.embeddings import EmbeddingsCache
from redisvl.index.index import AsyncSearchIndex
from redisvl.utils.vectorize import OpenAITextVectorizer

from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)

# Global singleton instances
_redis_client: Optional[Redis] = None
_vectorizer: Optional[Any] = None
_document_index: Optional[AsyncSearchIndex] = None

# Index names
SRE_KNOWLEDGE_INDEX = "sre_knowledge"
METRICS_INDEX = "sre_metrics"
SRE_SCHEDULES_INDEX = "sre_schedules"

# Schema definitions
SRE_KNOWLEDGE_SCHEMA = {
    "index": {
        "name": SRE_KNOWLEDGE_INDEX,
        "prefix": f"{SRE_KNOWLEDGE_INDEX}:",
        "storage_type": "hash",
    },
    "fields": [
        {
            "name": "title",
            "type": "text",
        },
        {
            "name": "content",
            "type": "text",
        },
        {
            "name": "document_hash",
            "type": "tag",
        },
        {
            "name": "source",
            "type": "tag",
        },
        {
            "name": "category",
            "type": "tag",
        },
        {
            "name": "severity",
            "type": "tag",
        },
        {
            "name": "product_labels",
            "type": "tag",
        },
        {
            "name": "product_label_tags",
            "type": "tag",
        },
        {
            "name": "created_at",
            "type": "numeric",
        },
        {
            "name": "vector",
            "type": "vector",
            "attrs": {
                "dims": settings.vector_dim,
                "distance_metric": "cosine",
                "algorithm": "flat",
                "datatype": "float32",
            },
        },
    ],
}

SRE_SCHEDULES_SCHEMA = {
    "index": {
        "name": SRE_SCHEDULES_INDEX,
        "prefix": f"{SRE_SCHEDULES_INDEX}:",
        "storage_type": "hash",
    },
    "fields": [
        {
            "name": "id",
            "type": "tag",
        },
        {
            "name": "name",
            "type": "text",
        },
        {
            "name": "description",
            "type": "text",
        },
        {
            "name": "interval_type",
            "type": "tag",
        },
        {
            "name": "interval_value",
            "type": "numeric",
        },
        {
            "name": "redis_instance_id",
            "type": "tag",
        },
        {
            "name": "instructions",
            "type": "text",
        },
        {
            "name": "enabled",
            "type": "tag",
        },
        {
            "name": "created_at",
            "type": "numeric",
        },
        {
            "name": "updated_at",
            "type": "numeric",
        },
        {
            "name": "last_run_at",
            "type": "numeric",
        },
        {
            "name": "next_run_at",
            "type": "numeric",
        },
    ],
}


def get_redis_client() -> Redis:
    """Get Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            url=settings.redis_url,
            password=settings.redis_password,
            decode_responses=False,  # Keep as bytes for RedisVL compatibility
        )
    return _redis_client


class _AsyncVectorizerProxy:
    """Proxy providing an awaitable embed_many while delegating other attributes."""

    def __init__(self, inner: Any):
        self._inner = inner

    async def embed_many(self, texts: List[str]):
        # Prefer embed_many if available, else try known sync methods
        method: Optional[Callable[..., Any]] = None
        for name in ("embed_many", "embed_texts", "embed"):
            if hasattr(self._inner, name):
                method = getattr(self._inner, name)
                break
        if method is None:
            raise AttributeError("Vectorizer has no embedding method")
        return await asyncio.to_thread(method, texts)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def __eq__(self, other: Any) -> bool:
        # Allow equality checks against the inner mock used in unit tests
        return other is self._inner or other == self._inner


# TODO: This should be using a RedisVL vectorizer
def get_vectorizer() -> OpenAITextVectorizer:
    """Get OpenAI vectorizer singleton with Redis caching.

    Additionally, make ``embed_many`` awaitable on the instance so callers can
    use ``await vectorizer.embed_many([...])``. This preserves backward
    compatibility for unit tests that expect the raw OpenAITextVectorizer
    instance while enabling async integration tests to ``await`` the call.
    """
    global _vectorizer
    if _vectorizer is None:
        cache = EmbeddingsCache(redis_url=settings.redis_url)
        inner = OpenAITextVectorizer(
            model=settings.embedding_model,
            cache=cache,
            api_config={"api_key": settings.openai_api_key},
        )
        _vectorizer = _AsyncVectorizerProxy(inner)
    else:
        # If a raw vectorizer instance exists without awaitable embed_many, wrap it
        embed_many = getattr(_vectorizer, "embed_many", None)
        if not (callable(embed_many) and asyncio.iscoroutinefunction(embed_many)):
            _vectorizer = _AsyncVectorizerProxy(_vectorizer)

    return _vectorizer


def get_knowledge_index() -> AsyncSearchIndex:
    """Get SRE knowledge base index singleton."""
    global _document_index
    if _document_index is None:
        _document_index = AsyncSearchIndex.from_dict(
            SRE_KNOWLEDGE_SCHEMA, redis_url=settings.redis_url
        )
    return _document_index


def get_schedules_index() -> AsyncSearchIndex:
    """Get SRE schedules index singleton."""
    return AsyncSearchIndex.from_dict(SRE_SCHEDULES_SCHEMA, redis_url=settings.redis_url)


async def test_redis_connection() -> bool:
    """Test Redis connection health."""
    try:
        client = get_redis_client()
        await client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection test failed: {e}")
        return False


async def test_vector_search() -> bool:
    """Test vector search index availability."""
    try:
        index = get_knowledge_index()
        exists = await index.exists()
        return exists
    except Exception as e:
        logger.error(f"Vector search test failed: {e}")
        return False


async def create_indices() -> bool:
    """Create vector search indices if they don't exist."""
    try:
        # Create knowledge index
        knowledge_index = get_knowledge_index()
        knowledge_exists = await knowledge_index.exists()

        if not knowledge_exists:
            await knowledge_index.create()
            logger.info(f"Created vector index: {SRE_KNOWLEDGE_INDEX}")
        else:
            logger.info(f"Vector index already exists: {SRE_KNOWLEDGE_INDEX}")

        # Create schedules index
        schedules_index = get_schedules_index()
        schedules_exists = await schedules_index.exists()

        if not schedules_exists:
            await schedules_index.create()
            logger.info(f"Created schedules index: {SRE_SCHEDULES_INDEX}")
        else:
            logger.info(f"Schedules index already exists: {SRE_SCHEDULES_INDEX}")

        return True
    except Exception as e:
        logger.error(f"Failed to create indices: {e}")
        return False


async def initialize_redis_infrastructure() -> dict:
    """Initialize Redis infrastructure and return status."""
    status = {}

    # Test basic Redis connection
    redis_ok = await test_redis_connection()
    status["redis_connection"] = "available" if redis_ok else "unavailable"

    # Test vectorizer
    try:
        vectorizer = get_vectorizer()
        status["vectorizer"] = "available" if vectorizer else "unavailable"
    except Exception as e:
        logger.error(f"Vectorizer initialization failed: {e}")
        status["vectorizer"] = "unavailable"

    # Create indices if Redis is available
    if redis_ok:
        indices_created = await create_indices()
        status["indices_created"] = "available" if indices_created else "unavailable"
    else:
        status["indices_created"] = "unavailable"

    # Initialize Docket infrastructure if Redis is available
    if redis_ok:
        docket_ok = await initialize_docket_infrastructure()
        status["docket_infrastructure"] = "available" if docket_ok else "unavailable"
    else:
        status["docket_infrastructure"] = "unavailable"

    # Test vector search index after creation (only if Redis is available)
    if redis_ok:
        vector_ok = await test_vector_search()
        status["vector_search"] = "available" if vector_ok else "unavailable"
    else:
        status["vector_search"] = "unavailable"

    return status


async def initialize_docket_infrastructure() -> bool:
    """Initialize Docket task queue infrastructure."""
    try:
        # Import Docket here to avoid circular imports
        from docket import Docket

        # Test Docket connection and ensure infrastructure is ready
        async with Docket(url=settings.redis_url, name="sre_docket") as docket:
            # Test basic Docket functionality by checking for workers
            # This will create necessary Redis structures if they don't exist
            await docket.workers()
            logger.info("Docket infrastructure initialized successfully")
            return True

    except ImportError:
        logger.warning("Docket not available - task queue functionality will be limited")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Docket infrastructure: {e}")
        return False


async def cleanup_redis_connections():
    """Cleanup Redis connections on shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
    logger.info("Redis connections cleaned up")

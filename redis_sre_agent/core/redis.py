"""Redis connection management with singleton pattern."""

import logging
from typing import Optional

from redis.asyncio import Redis
from redisvl.extensions.cache.embeddings.embeddings import EmbeddingsCache
from redisvl.index.index import AsyncSearchIndex
from redisvl.utils.vectorize import OpenAITextVectorizer

from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)

# Global singleton instances
_redis_client: Optional[Redis] = None
_vectorizer: Optional[OpenAITextVectorizer] = None
_document_index: Optional[AsyncSearchIndex] = None

# Index names
SRE_KNOWLEDGE_INDEX = "sre_knowledge"
METRICS_INDEX = "sre_metrics"

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


def get_vectorizer() -> OpenAITextVectorizer:
    """Get OpenAI vectorizer singleton with Redis caching."""
    global _vectorizer
    if _vectorizer is None:
        cache = EmbeddingsCache(redis_url=settings.redis_url)
        _vectorizer = OpenAITextVectorizer(
            model=settings.embedding_model,
            cache=cache,
            api_config={"api_key": settings.openai_api_key},
        )
    return _vectorizer


def get_knowledge_index() -> AsyncSearchIndex:
    """Get SRE knowledge base index singleton."""
    global _document_index
    if _document_index is None:
        _document_index = AsyncSearchIndex.from_dict(
            SRE_KNOWLEDGE_SCHEMA, redis_url=settings.redis_url
        )
    return _document_index


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
        index = get_knowledge_index()
        exists = await index.exists()

        if not exists:
            await index.create()
            logger.info(f"Created vector index: {SRE_KNOWLEDGE_INDEX}")
        else:
            logger.info(f"Vector index already exists: {SRE_KNOWLEDGE_INDEX}")

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

    # Test vector search index after creation
    vector_ok = await test_vector_search()
    status["vector_search"] = "available" if vector_ok else "unavailable"

    return status


async def cleanup_redis_connections():
    """Cleanup Redis connections on shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
    logger.info("Redis connections cleaned up")

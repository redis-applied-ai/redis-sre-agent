"""Redis connection management - no caching to avoid event loop issues."""

import logging
from typing import Optional

from redis.asyncio import Redis
from redisvl.extensions.cache.embeddings.embeddings import EmbeddingsCache
from redisvl.index.index import AsyncSearchIndex
from redisvl.utils.vectorize import OpenAITextVectorizer

from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)

# Index names
SRE_KNOWLEDGE_INDEX = "sre_knowledge"
METRICS_INDEX = "sre_metrics"
SRE_SCHEDULES_INDEX = "sre_schedules"

# Threads index
SRE_THREADS_INDEX = "sre_threads"
# Tasks index
SRE_TASKS_INDEX = "sre_tasks"

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
            "name": "content_hash",
            "type": "tag",
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

SRE_THREADS_SCHEMA = {
    "index": {
        "name": SRE_THREADS_INDEX,
        "prefix": f"{SRE_THREADS_INDEX}:",
        "storage_type": "hash",
    },
    "fields": [
        {"name": "subject", "type": "text"},
        {"name": "user_id", "type": "tag"},
        {"name": "instance_id", "type": "tag"},
        {"name": "priority", "type": "numeric"},
        {"name": "created_at", "type": "numeric"},
        {"name": "updated_at", "type": "numeric"},
    ],
}

SRE_TASKS_SCHEMA = {
    "index": {
        "name": SRE_TASKS_INDEX,
        "prefix": f"{SRE_TASKS_INDEX}:",
        "storage_type": "hash",
    },
    "fields": [
        {"name": "status", "type": "tag"},
        {"name": "subject", "type": "text"},
        {"name": "user_id", "type": "tag"},
        {"name": "thread_id", "type": "tag"},
        {"name": "created_at", "type": "numeric"},
        {"name": "updated_at", "type": "numeric"},
    ],
}


def get_redis_client(url: Optional[str] = None) -> Redis:
    """Get Redis client (creates fresh client to avoid event loop issues)."""
    redis_url = url or settings.redis_url.get_secret_value()
    redis_password = settings.redis_password.get_secret_value() if settings.redis_password else None
    return Redis.from_url(
        url=redis_url,
        password=redis_password,
        decode_responses=False,  # Keep as bytes for RedisVL compatibility
    )


def get_vectorizer() -> OpenAITextVectorizer:
    """Get OpenAI vectorizer with Redis-backed embeddings cache.

    Returns the native vectorizer; callers should use aembed/aembed_many.
    """
    # Build Redis URL with password if needed (ensure cache can auth)
    redis_url = settings.redis_url.get_secret_value()
    redis_password = settings.redis_password.get_secret_value() if settings.redis_password else None
    if redis_password and "@" not in redis_url:
        redis_url = redis_url.replace("redis://", f"redis://:{redis_password}@")

    # Name the cache to keep a stable key namespace
    cache = EmbeddingsCache(name="sre_embeddings_cache", redis_url=redis_url)

    return OpenAITextVectorizer(
        model=settings.embedding_model,
        cache=cache,
        api_config={"api_key": settings.openai_api_key},
    )


async def get_knowledge_index() -> AsyncSearchIndex:
    """Get SRE knowledge base index (creates fresh to avoid event loop issues)."""
    from redisvl.schema import IndexSchema

    # Build Redis URL with password if needed
    redis_url = settings.redis_url.get_secret_value()
    redis_password = settings.redis_password.get_secret_value() if settings.redis_password else None
    if redis_password and "@" not in redis_url:
        # Insert password into URL: redis://localhost -> redis://:password@localhost
        redis_url = redis_url.replace("redis://", f"redis://:{redis_password}@")

    # Create Redis client once and pass to index
    redis_client = Redis.from_url(redis_url, decode_responses=False)

    # Convert schema dict to IndexSchema object
    schema = IndexSchema.from_dict(SRE_KNOWLEDGE_SCHEMA)

    # Create index with the shared client
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)

    return index


async def get_tasks_index() -> AsyncSearchIndex:
    """Get SRE tasks index (async)."""
    from redisvl.schema import IndexSchema

    redis_url = settings.redis_url.get_secret_value()
    redis_password = settings.redis_password.get_secret_value() if settings.redis_password else None
    if redis_password and "@" not in redis_url:
        redis_url = redis_url.replace("redis://", f"redis://:{redis_password}@")

    redis_client = Redis.from_url(redis_url, decode_responses=False)
    schema = IndexSchema.from_dict(SRE_TASKS_SCHEMA)
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)
    return index


async def get_threads_index() -> AsyncSearchIndex:
    """Get SRE threads/tasks index (async)."""
    from redisvl.schema import IndexSchema

    # Build Redis URL with password if needed
    redis_url = settings.redis_url.get_secret_value()
    redis_password = settings.redis_password.get_secret_value() if settings.redis_password else None
    if redis_password and "@" not in redis_url:
        redis_url = redis_url.replace("redis://", f"redis://:{redis_password}@")

    redis_client = Redis.from_url(redis_url, decode_responses=False)
    schema = IndexSchema.from_dict(SRE_THREADS_SCHEMA)
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)
    return index


async def get_schedules_index() -> AsyncSearchIndex:
    """Get SRE schedules index singleton."""
    from redisvl.schema import IndexSchema

    # Build Redis URL with password if needed
    redis_url = settings.redis_url.get_secret_value()
    redis_password = settings.redis_password.get_secret_value() if settings.redis_password else None
    if redis_password and "@" not in redis_url:
        # Insert password into URL: redis://localhost -> redis://:password@localhost
        redis_url = redis_url.replace("redis://", f"redis://:{redis_password}@")

    # Create Redis client once and pass to index
    redis_client = Redis.from_url(redis_url, decode_responses=False)

    # Convert schema dict to IndexSchema object
    schema = IndexSchema.from_dict(SRE_SCHEDULES_SCHEMA)

    # Create index with the shared client
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)

    return index


async def test_redis_connection(url: Optional[str] = None) -> bool:
    """Test Redis connection health.

    Args:
        url: Optional Redis URL to test. If not provided, uses default from settings.

    Returns:
        True if connection successful, False otherwise.
    """
    try:
        client = get_redis_client(url=url)
        await client.ping()
        await client.aclose()
        return True
    except Exception as e:
        logger.error(f"Redis connection test failed: {e}")
        return False


async def test_vector_search() -> bool:
    """Test vector search index availability."""
    try:
        index = await get_knowledge_index()
        exists = await index.exists()
        return exists
    except Exception as e:
        logger.error(f"Vector search test failed: {e}")
        return False


async def create_indices() -> bool:
    """Create vector search indices if they don't exist."""
    try:
        # Create knowledge index
        knowledge_index = await get_knowledge_index()
        knowledge_exists = await knowledge_index.exists()

        if not knowledge_exists:
            await knowledge_index.create()
            logger.info(f"Created vector index: {SRE_KNOWLEDGE_INDEX}")
        else:
            logger.info(f"Vector index already exists: {SRE_KNOWLEDGE_INDEX}")

        # Create schedules index
        schedules_index = await get_schedules_index()
        schedules_exists = await schedules_index.exists()

        if not schedules_exists:
            await schedules_index.create()
            logger.info(f"Created schedules index: {SRE_SCHEDULES_INDEX}")
        else:
            logger.info(f"Schedules index already exists: {SRE_SCHEDULES_INDEX}")

        # Create threads index
        threads_index = await get_threads_index()
        threads_exists = await threads_index.exists()
        if not threads_exists:
            await threads_index.create()
            logger.info(f"Created threads index: {SRE_THREADS_INDEX}")
        else:
            logger.info(f"Threads index already exists: {SRE_THREADS_INDEX}")

        # Create tasks index
        tasks_index = await get_tasks_index()
        tasks_exists = await tasks_index.exists()
        if not tasks_exists:
            await tasks_index.create()
            logger.info(f"Created tasks index: {SRE_TASKS_INDEX}")
        else:
            logger.info(f"Tasks index already exists: {SRE_TASKS_INDEX}")

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
        async with Docket(url=settings.redis_url.get_secret_value(), name="sre_docket") as docket:
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
    """Cleanup Redis connections on shutdown (no-op since we removed caching)."""
    # No cleanup needed since we don't cache connections anymore
    logger.info("Redis connections cleanup called (no-op)")

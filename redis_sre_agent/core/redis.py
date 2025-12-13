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
# Instances index
SRE_INSTANCES_INDEX = "sre_instances"


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
            "name": "version",
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
        {"name": "tags", "type": "tag"},
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

SRE_INSTANCES_SCHEMA = {
    "index": {
        "name": SRE_INSTANCES_INDEX,
        "prefix": f"{SRE_INSTANCES_INDEX}:",
        "storage_type": "hash",
    },
    "fields": [
        {"name": "name", "type": "text"},
        {"name": "environment", "type": "tag"},
        {"name": "usage", "type": "tag"},
        {"name": "instance_type", "type": "tag"},
        {"name": "user_id", "type": "tag"},
        {"name": "status", "type": "tag"},
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

    The embeddings cache uses a stable key namespace ("sre_embeddings_cache")
    so that embeddings are shared across vectorizer instances. Cache keys
    include the model name, so different models won't conflict.

    TTL is configurable via settings.embeddings_cache_ttl (default: 7 days).
    """
    # Build Redis URL with password if needed (ensure cache can auth)
    redis_url = settings.redis_url.get_secret_value()
    redis_password = settings.redis_password.get_secret_value() if settings.redis_password else None
    if redis_password and "@" not in redis_url:
        redis_url = redis_url.replace("redis://", f"redis://:{redis_password}@")

    # Name the cache to keep a stable key namespace
    # TTL prevents stale embeddings if model changes
    cache = EmbeddingsCache(
        name="sre_embeddings_cache",
        redis_url=redis_url,
        ttl=settings.embeddings_cache_ttl,
    )
    logger.debug(f"Vectorizer created with embeddings cache (ttl={settings.embeddings_cache_ttl}s)")

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


async def get_instances_index() -> AsyncSearchIndex:
    """Get SRE instances index (async)."""
    from redisvl.schema import IndexSchema

    # Build Redis URL with password if needed
    redis_url = settings.redis_url.get_secret_value()
    redis_password = settings.redis_password.get_secret_value() if settings.redis_password else None
    if redis_password and "@" not in redis_url:
        redis_url = redis_url.replace("redis://", f"redis://:{redis_password}@")

    redis_client = Redis.from_url(redis_url, decode_responses=False)
    schema = IndexSchema.from_dict(SRE_INSTANCES_SCHEMA)
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
            logger.debug(f"Created vector index: {SRE_KNOWLEDGE_INDEX}")
        else:
            logger.debug(f"Vector index already exists: {SRE_KNOWLEDGE_INDEX}")

        # Create schedules index
        schedules_index = await get_schedules_index()
        schedules_exists = await schedules_index.exists()

        if not schedules_exists:
            await schedules_index.create()
            logger.debug(f"Created schedules index: {SRE_SCHEDULES_INDEX}")
        else:
            logger.debug(f"Schedules index already exists: {SRE_SCHEDULES_INDEX}")

        # Create threads index
        threads_index = await get_threads_index()
        threads_exists = await threads_index.exists()
        if not threads_exists:
            await threads_index.create()
            logger.debug(f"Created threads index: {SRE_THREADS_INDEX}")
        else:
            logger.debug(f"Threads index already exists: {SRE_THREADS_INDEX}")

        # Create tasks index
        tasks_index = await get_tasks_index()
        tasks_exists = await tasks_index.exists()
        if not tasks_exists:
            await tasks_index.create()
            logger.debug(f"Created tasks index: {SRE_TASKS_INDEX}")
        else:
            logger.debug(f"Tasks index already exists: {SRE_TASKS_INDEX}")

        # Create instances index
        instances_index = await get_instances_index()
        instances_exists = await instances_index.exists()
        if not instances_exists:
            await instances_index.create()
            logger.debug(f"Created instances index: {SRE_INSTANCES_INDEX}")
        else:
            logger.debug(f"Instances index already exists: {SRE_INSTANCES_INDEX}")

        return True
    except Exception as e:
        logger.error(f"Failed to create indices: {e}")
        return False


async def recreate_indices(index_name: str | None = None) -> dict:
    """Drop and recreate RediSearch indices.

    This is useful when the schema has changed (e.g., new fields added).

    Args:
        index_name: Specific index to recreate ('knowledge', 'schedules', 'threads',
                   'tasks', 'instances'), or None to recreate all.

    Returns:
        Dictionary with success status and details for each index.
    """
    result = {"success": True, "indices": {}}

    index_configs = [
        ("knowledge", SRE_KNOWLEDGE_INDEX, get_knowledge_index),
        ("schedules", SRE_SCHEDULES_INDEX, get_schedules_index),
        ("threads", SRE_THREADS_INDEX, get_threads_index),
        ("tasks", SRE_TASKS_INDEX, get_tasks_index),
        ("instances", SRE_INSTANCES_INDEX, get_instances_index),
    ]

    for name, idx_name, get_fn in index_configs:
        # Skip if a specific index was requested and this isn't it
        if index_name and name != index_name:
            continue

        try:
            idx = await get_fn()

            # Drop index if it exists
            if await idx.exists():
                try:
                    # Use FT.DROPINDEX to drop without deleting documents
                    await idx._redis_client.execute_command("FT.DROPINDEX", idx_name)
                    logger.info(f"Dropped index: {idx_name}")
                except Exception as drop_err:
                    logger.warning(f"Could not drop index {idx_name}: {drop_err}")

            # Recreate with current schema
            await idx.create()
            logger.info(f"Created index: {idx_name}")
            result["indices"][name] = "recreated"

        except Exception as e:
            logger.error(f"Failed to recreate index {name}: {e}")
            result["indices"][name] = f"error: {e}"
            result["success"] = False

    return result


async def initialize_redis() -> dict:
    """Initialize Redis infrastructure and return status."""
    status = {}

    # Test basic Redis connection
    redis_ok = await test_redis_connection()
    status["redis_connection"] = "available" if redis_ok else "unavailable"

    # Test vectorizer (skip when no OpenAI key configured)
    try:
        if not settings.openai_api_key:
            status["vectorizer"] = "skipped"
        else:
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
        docket_ok = await initialize_docket()
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


async def initialize_docket() -> bool:
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
        logger.error(f"Failed to initialize: {e}")
        return False

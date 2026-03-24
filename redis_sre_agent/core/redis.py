"""Redis connection management - no caching to avoid event loop issues."""

import logging
from typing import Any, Optional, Union

from redis.asyncio import Redis
from redisvl.extensions.cache.embeddings.embeddings import EmbeddingsCache
from redisvl.index.index import AsyncSearchIndex
from redisvl.utils.vectorize import HFTextVectorizer, OpenAITextVectorizer

from redis_sre_agent.core.config import Settings, settings

# Type alias for vectorizers
Vectorizer = Union[OpenAITextVectorizer, HFTextVectorizer]

logger = logging.getLogger(__name__)

# Index names
SRE_KNOWLEDGE_INDEX = "sre_knowledge"
SRE_SKILLS_INDEX = "sre_skills"
SRE_SUPPORT_TICKETS_INDEX = "sre_support_tickets"
METRICS_INDEX = "sre_metrics"
SRE_SCHEDULES_INDEX = "sre_schedules"

# Threads index
SRE_THREADS_INDEX = "sre_threads"
# Tasks index
SRE_TASKS_INDEX = "sre_tasks"
# Instances index
SRE_INSTANCES_INDEX = "sre_instances"
# Clusters index
SRE_CLUSTERS_INDEX = "sre_clusters"
# Q&A index
SRE_QA_INDEX = "sre_qa"


def _build_document_schema(index_name: str, include_pinned: bool) -> dict:
    """Build a search schema for chunked source documents."""
    fields = [
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
            "name": "doc_type",
            "type": "tag",
        },
        {
            "name": "name",
            "type": "tag",
        },
        {
            "name": "summary",
            "type": "text",
        },
        {
            "name": "priority",
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
            "name": "chunk_index",
            "type": "numeric",
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
    ]
    if include_pinned:
        pinned_field = {"name": "pinned", "type": "tag"}
        chunk_index_position = next(
            (
                idx
                for idx, field in enumerate(fields)
                if isinstance(field, dict) and field.get("name") == "chunk_index"
            ),
            len(fields),
        )
        fields.insert(chunk_index_position, pinned_field)
    return {
        "index": {
            "name": index_name,
            "prefix": f"{index_name}:",
            "storage_type": "hash",
        },
        "fields": fields,
    }


# Schema definitions
SRE_KNOWLEDGE_SCHEMA = _build_document_schema(SRE_KNOWLEDGE_INDEX, include_pinned=True)
SRE_SKILLS_SCHEMA = _build_document_schema(SRE_SKILLS_INDEX, include_pinned=True)
SRE_SUPPORT_TICKETS_SCHEMA = _build_document_schema(
    SRE_SUPPORT_TICKETS_INDEX,
    include_pinned=True,
)

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
        {"name": "name", "type": "tag"},
        {"name": "environment", "type": "tag"},
        {"name": "usage", "type": "tag"},
        {"name": "instance_type", "type": "tag"},
        {"name": "cluster_id", "type": "tag"},
        {"name": "user_id", "type": "tag"},
        {"name": "status", "type": "tag"},
        {"name": "created_at", "type": "numeric"},
        {"name": "updated_at", "type": "numeric"},
    ],
}

SRE_CLUSTERS_SCHEMA = {
    "index": {
        "name": SRE_CLUSTERS_INDEX,
        "prefix": f"{SRE_CLUSTERS_INDEX}:",
        "storage_type": "hash",
    },
    "fields": [
        {"name": "name", "type": "tag"},
        {"name": "environment", "type": "tag"},
        {"name": "cluster_type", "type": "tag"},
        {"name": "user_id", "type": "tag"},
        {"name": "status", "type": "tag"},
        {"name": "created_at", "type": "numeric"},
        {"name": "updated_at", "type": "numeric"},
    ],
}

SRE_QA_SCHEMA = {
    "index": {
        "name": SRE_QA_INDEX,
        "prefix": f"{SRE_QA_INDEX}:",
        "storage_type": "hash",
    },
    "fields": [
        {"name": "question", "type": "text"},
        {"name": "answer", "type": "text"},
        {"name": "user_id", "type": "tag"},
        {"name": "thread_id", "type": "tag"},
        {"name": "task_id", "type": "tag"},
        {"name": "created_at", "type": "numeric"},
        {"name": "updated_at", "type": "numeric"},
        {
            "name": "question_vector",
            "type": "vector",
            "attrs": {
                "dims": settings.vector_dim,
                "distance_metric": "cosine",
                "algorithm": "flat",
                "datatype": "float32",
            },
        },
        {
            "name": "answer_vector",
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


def _decode_redis_value(value: Any) -> Any:
    """Decode Redis byte payloads into plain Python values."""
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, list):
        return [_decode_redis_value(item) for item in value]
    return value


def _pairs_to_dict(values: list[Any]) -> dict[str, Any]:
    """Convert Redis alternating key/value arrays into dictionaries."""
    result: dict[str, Any] = {}
    normalized = _decode_redis_value(values)
    for i in range(0, len(normalized) - 1, 2):
        key = str(normalized[i])
        result[key] = normalized[i + 1]
    return result


def _expected_field_definitions(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build comparable field metadata from a schema dict."""
    definitions: dict[str, dict[str, Any]] = {}
    for field in schema.get("fields", []):
        if not isinstance(field, dict):
            continue
        name = str(field.get("name", "")).strip()
        if not name:
            continue
        field_type = str(field.get("type", "")).strip().upper()
        definition: dict[str, Any] = {"type": field_type}
        if field_type == "VECTOR":
            attrs = field.get("attrs") or {}
            definition["attrs"] = {
                "algorithm": str(attrs.get("algorithm", "")).strip().upper(),
                "data_type": str(attrs.get("datatype", "")).strip().upper(),
                "dim": attrs.get("dims"),
                "distance_metric": str(attrs.get("distance_metric", "")).strip().upper(),
            }
        definitions[name] = definition
    return definitions


def _actual_field_definitions(raw_info: list[Any]) -> dict[str, dict[str, Any]]:
    """Extract comparable field metadata from FT.INFO output."""
    decoded = _decode_redis_value(raw_info)
    info = _pairs_to_dict(decoded)
    attributes = info.get("attributes") or []
    definitions: dict[str, dict[str, Any]] = {}

    for attribute in attributes:
        attr_dict = _pairs_to_dict(attribute)
        name = str(attr_dict.get("attribute") or attr_dict.get("identifier") or "").strip()
        if not name:
            continue
        field_type = str(attr_dict.get("type", "")).strip().upper()
        definition: dict[str, Any] = {"type": field_type}
        if field_type == "VECTOR":
            definition["attrs"] = {
                "algorithm": str(attr_dict.get("algorithm", "")).strip().upper(),
                "data_type": str(attr_dict.get("data_type", "")).strip().upper(),
                "dim": attr_dict.get("dim"),
                "distance_metric": str(attr_dict.get("distance_metric", "")).strip().upper(),
            }
        definitions[name] = definition

    return definitions


def _compare_index_schema(
    expected_fields: dict[str, dict[str, Any]],
    actual_fields: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Summarize schema drift between the expected and actual index definitions."""
    expected_names = set(expected_fields)
    actual_names = set(actual_fields)

    missing_fields = sorted(expected_names - actual_names)
    unexpected_fields = sorted(actual_names - expected_names)
    mismatched_fields: dict[str, dict[str, Any]] = {}

    for field_name in sorted(expected_names & actual_names):
        expected = expected_fields[field_name]
        actual = actual_fields[field_name]
        if expected != actual:
            mismatched_fields[field_name] = {"expected": expected, "actual": actual}

    in_sync = not missing_fields and not unexpected_fields and not mismatched_fields
    return {
        "in_sync": in_sync,
        "missing_fields": missing_fields,
        "unexpected_fields": unexpected_fields,
        "mismatched_fields": mismatched_fields,
    }


def get_redis_client(
    url: Optional[str] = None,
    config: Optional[Settings] = None,
) -> Redis:
    """Get Redis client (creates fresh client to avoid event loop issues).

    Args:
        url: Optional Redis URL. If provided, takes precedence over config.
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        Async Redis client instance.
    """
    cfg = config or settings
    redis_url = url or cfg.redis_url.get_secret_value()
    return Redis.from_url(
        url=redis_url,
        decode_responses=False,  # Keep as bytes for RedisVL compatibility
    )


def get_vectorizer(config: Optional[Settings] = None) -> Vectorizer:
    """Get vectorizer with Redis-backed embeddings cache.

    Returns either an OpenAI or HuggingFace vectorizer based on settings.embedding_provider.
    Callers should use aembed/aembed_many for async operations.

    Args:
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Providers:
        - 'openai': Uses OpenAI API (requires OPENAI_API_KEY and network access)
        - 'local': Uses HuggingFace sentence-transformers (no API needed, air-gap compatible)

    The embeddings cache uses a stable key namespace ("sre_embeddings_cache")
    so that embeddings are shared across vectorizer instances. Cache keys
    include the model name, so different models won't conflict.

    TTL is configurable via settings.embeddings_cache_ttl (default: 7 days).
    """
    cfg = config or settings
    redis_url = cfg.redis_url.get_secret_value()

    # Name the cache to keep a stable key namespace
    # TTL prevents stale embeddings if model changes
    cache = EmbeddingsCache(
        name="sre_embeddings_cache",
        redis_url=redis_url,
        ttl=cfg.embeddings_cache_ttl,
    )

    provider = cfg.embedding_provider.lower()

    if provider == "local":
        # Use HuggingFace sentence-transformers (air-gap compatible)
        logger.info(f"Using local HuggingFace vectorizer with model: {cfg.embedding_model}")
        return HFTextVectorizer(
            model=cfg.embedding_model,
            cache=cache,
        )
    elif provider == "openai":
        # Use OpenAI API (default)
        logger.debug(f"Vectorizer created with embeddings cache (ttl={cfg.embeddings_cache_ttl}s)")
        return OpenAITextVectorizer(
            model=cfg.embedding_model,
            cache=cache,
            api_config={
                "api_key": cfg.openai_api_key,
                **({"base_url": cfg.openai_base_url} if cfg.openai_base_url else {}),
            },
        )
    else:
        raise ValueError(
            f"Unknown embedding_provider: '{provider}'. Supported values: 'openai', 'local'"
        )


async def get_knowledge_index(config: Optional[Settings] = None) -> AsyncSearchIndex:
    """Get SRE knowledge base index (creates fresh to avoid event loop issues).

    Args:
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        AsyncSearchIndex for the knowledge base.
    """
    from redisvl.schema import IndexSchema

    cfg = config or settings
    redis_url = cfg.redis_url.get_secret_value()

    # Create Redis client once and pass to index
    redis_client = Redis.from_url(redis_url, decode_responses=False)

    # Convert schema dict to IndexSchema object
    schema = IndexSchema.from_dict(SRE_KNOWLEDGE_SCHEMA)

    # Create index with the shared client
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)

    return index


async def get_skills_index(config: Optional[Settings] = None) -> AsyncSearchIndex:
    """Get SRE skills index (creates fresh to avoid event loop issues)."""
    from redisvl.schema import IndexSchema

    cfg = config or settings
    redis_url = cfg.redis_url.get_secret_value()
    redis_client = Redis.from_url(redis_url, decode_responses=False)
    schema = IndexSchema.from_dict(SRE_SKILLS_SCHEMA)
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)
    return index


async def get_support_tickets_index(config: Optional[Settings] = None) -> AsyncSearchIndex:
    """Get SRE support tickets index (creates fresh to avoid event loop issues)."""
    from redisvl.schema import IndexSchema

    cfg = config or settings
    redis_url = cfg.redis_url.get_secret_value()
    redis_client = Redis.from_url(redis_url, decode_responses=False)
    schema = IndexSchema.from_dict(SRE_SUPPORT_TICKETS_SCHEMA)
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)
    return index


async def get_tasks_index(config: Optional[Settings] = None) -> AsyncSearchIndex:
    """Get SRE tasks index (async).

    Args:
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        AsyncSearchIndex for tasks.
    """
    from redisvl.schema import IndexSchema

    cfg = config or settings
    redis_url = cfg.redis_url.get_secret_value()

    redis_client = Redis.from_url(redis_url, decode_responses=False)
    schema = IndexSchema.from_dict(SRE_TASKS_SCHEMA)
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)
    return index


async def get_instances_index(config: Optional[Settings] = None) -> AsyncSearchIndex:
    """Get SRE instances index (async).

    Args:
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        AsyncSearchIndex for instances.
    """
    from redisvl.schema import IndexSchema

    cfg = config or settings
    redis_url = cfg.redis_url.get_secret_value()

    redis_client = Redis.from_url(redis_url, decode_responses=False)
    schema = IndexSchema.from_dict(SRE_INSTANCES_SCHEMA)
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)
    return index


async def get_clusters_index(config: Optional[Settings] = None) -> AsyncSearchIndex:
    """Get SRE clusters index (async).

    Args:
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        AsyncSearchIndex for clusters.
    """
    from redisvl.schema import IndexSchema

    cfg = config or settings
    redis_url = cfg.redis_url.get_secret_value()

    redis_client = Redis.from_url(redis_url, decode_responses=False)
    schema = IndexSchema.from_dict(SRE_CLUSTERS_SCHEMA)
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)
    return index


async def get_threads_index(config: Optional[Settings] = None) -> AsyncSearchIndex:
    """Get SRE threads/tasks index (async).

    Args:
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        AsyncSearchIndex for threads.
    """
    from redisvl.schema import IndexSchema

    cfg = config or settings
    redis_url = cfg.redis_url.get_secret_value()

    redis_client = Redis.from_url(redis_url, decode_responses=False)
    schema = IndexSchema.from_dict(SRE_THREADS_SCHEMA)
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)
    return index


async def get_qa_index() -> AsyncSearchIndex:
    """Get Q&A index for vector search on questions and answers."""
    from redisvl.schema import IndexSchema

    # Build Redis URL with password if needed
    redis_url = settings.redis_url.get_secret_value()
    redis_password = settings.redis_password.get_secret_value() if settings.redis_password else None
    if redis_password and "@" not in redis_url:
        redis_url = redis_url.replace("redis://", f"redis://:{redis_password}@")

    redis_client = Redis.from_url(redis_url, decode_responses=False)
    schema = IndexSchema.from_dict(SRE_QA_SCHEMA)
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)
    return index


async def get_schedules_index(config: Optional[Settings] = None) -> AsyncSearchIndex:
    """Get SRE schedules index.

    Args:
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        AsyncSearchIndex for schedules.
    """
    from redisvl.schema import IndexSchema

    cfg = config or settings
    redis_url = cfg.redis_url.get_secret_value()

    # Create Redis client once and pass to index
    redis_client = Redis.from_url(redis_url, decode_responses=False)

    # Convert schema dict to IndexSchema object
    schema = IndexSchema.from_dict(SRE_SCHEDULES_SCHEMA)

    # Create index with the shared client
    index = AsyncSearchIndex(schema=schema, redis_client=redis_client)

    return index


async def test_redis_connection(
    url: Optional[str] = None,
    config: Optional[Settings] = None,
) -> bool:
    """Test Redis connection health.

    Args:
        url: Optional Redis URL to test. If provided, takes precedence over config.
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        True if connection successful, False otherwise.
    """
    try:
        client = get_redis_client(url=url, config=config)
        await client.ping()
        await client.aclose()
        return True
    except Exception as e:
        logger.error(f"Redis connection test failed: {e}")
        return False


async def test_vector_search(config: Optional[Settings] = None) -> bool:
    """Test vector search index availability.

    Args:
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        True if vector search index exists, False otherwise.
    """
    try:
        index = await get_knowledge_index(config=config)
        exists = await index.exists()
        return exists
    except Exception as e:
        logger.error(f"Vector search test failed: {e}")
        return False


def _iter_index_configs():
    """Yield canonical index metadata for management commands."""
    yield ("knowledge", SRE_KNOWLEDGE_INDEX, get_knowledge_index, SRE_KNOWLEDGE_SCHEMA)
    yield ("skills", SRE_SKILLS_INDEX, get_skills_index, SRE_SKILLS_SCHEMA)
    yield (
        "support_tickets",
        SRE_SUPPORT_TICKETS_INDEX,
        get_support_tickets_index,
        SRE_SUPPORT_TICKETS_SCHEMA,
    )
    yield ("schedules", SRE_SCHEDULES_INDEX, get_schedules_index, SRE_SCHEDULES_SCHEMA)
    yield ("threads", SRE_THREADS_INDEX, get_threads_index, SRE_THREADS_SCHEMA)
    yield ("tasks", SRE_TASKS_INDEX, get_tasks_index, SRE_TASKS_SCHEMA)
    yield ("instances", SRE_INSTANCES_INDEX, get_instances_index, SRE_INSTANCES_SCHEMA)
    yield ("clusters", SRE_CLUSTERS_INDEX, get_clusters_index, SRE_CLUSTERS_SCHEMA)


async def get_index_schema_status(
    index_name: str | None = None,
    config: Optional[Settings] = None,
) -> dict[str, Any]:
    """Inspect index schemas and report whether they match current definitions."""
    result: dict[str, Any] = {"success": True, "indices": {}}

    for name, idx_name, get_fn, schema in _iter_index_configs():
        if index_name and name != index_name:
            continue

        entry: dict[str, Any] = {
            "index_name": idx_name,
            "expected_fields": sorted(_expected_field_definitions(schema)),
        }

        try:
            idx = await get_fn(config=config)
            exists = await idx.exists()
            entry["exists"] = exists

            if not exists:
                entry["status"] = "missing"
                result["indices"][name] = entry
                continue

            raw_info = await idx._redis_client.execute_command("FT.INFO", idx_name)
            actual_fields = _actual_field_definitions(raw_info)
            comparison = _compare_index_schema(
                _expected_field_definitions(schema),
                actual_fields,
            )
            entry.update(comparison)
            entry["actual_fields"] = sorted(actual_fields)
            entry["status"] = "in_sync" if comparison["in_sync"] else "drifted"
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = str(exc)
            result["success"] = False

        result["indices"][name] = entry

    return result


async def sync_index_schemas(
    index_name: str | None = None,
    config: Optional[Settings] = None,
) -> dict[str, Any]:
    """Create or recreate only indices whose schema has drifted."""
    status_result = await get_index_schema_status(index_name=index_name, config=config)
    result: dict[str, Any] = {"success": status_result["success"], "indices": {}}

    for name, idx_name, get_fn, _schema in _iter_index_configs():
        if index_name and name != index_name:
            continue

        status = status_result["indices"].get(name, {})
        current_status = status.get("status")
        entry: dict[str, Any] = {
            "index_name": idx_name,
            "previous_status": current_status,
        }

        if current_status == "in_sync":
            entry["action"] = "unchanged"
            result["indices"][name] = entry
            continue

        if current_status == "error":
            entry["action"] = "error"
            entry["error"] = status.get("error")
            result["indices"][name] = entry
            result["success"] = False
            continue

        try:
            idx = await get_fn(config=config)
            if status.get("exists"):
                await idx._redis_client.execute_command("FT.DROPINDEX", idx_name)
                await idx.create()
                entry["action"] = "recreated"
            else:
                await idx.create()
                entry["action"] = "created"
        except Exception as exc:
            entry["action"] = "error"
            entry["error"] = str(exc)
            result["success"] = False

        result["indices"][name] = entry

    return result


async def create_indices(config: Optional[Settings] = None) -> bool:
    """Create vector search indices if they don't exist.

    Args:
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        True if all indices were created successfully, False otherwise.
    """
    try:
        for _name, idx_name, get_fn, _schema in _iter_index_configs():
            idx = await get_fn(config=config)
            exists = await idx.exists()
            if not exists:
                await idx.create()
                logger.debug("Created index: %s", idx_name)
            else:
                logger.debug("Index already exists: %s", idx_name)
        return True
    except Exception as e:
        logger.error(f"Failed to create indices: {e}")
        return False


async def recreate_indices(
    index_name: str | None = None,
    config: Optional[Settings] = None,
) -> dict:
    """Drop and recreate RediSearch indices.

    This is useful when the schema has changed (e.g., new fields added).

    Args:
        index_name: Specific index to recreate ('knowledge', 'skills',
                   'support_tickets', 'schedules', 'threads', 'tasks',
                   'instances', 'clusters'), or None to recreate all.
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        Dictionary with success status and details for each index.
    """
    result = {"success": True, "indices": {}}

    for name, idx_name, get_fn, _schema in _iter_index_configs():
        # Skip if a specific index was requested and this isn't it
        if index_name and name != index_name:
            continue

        try:
            idx = await get_fn(config=config)

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


async def initialize_redis(config: Optional[Settings] = None) -> dict:
    """Initialize Redis infrastructure and return status.

    Args:
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        Dictionary with status of each infrastructure component.
    """
    cfg = config or settings
    status = {}

    # Test basic Redis connection
    redis_ok = await test_redis_connection(config=cfg)
    status["redis_connection"] = "available" if redis_ok else "unavailable"

    # Test vectorizer (skip when no OpenAI key configured)
    try:
        if not cfg.openai_api_key:
            status["vectorizer"] = "skipped"
        else:
            vectorizer = get_vectorizer(config=cfg)
            status["vectorizer"] = "available" if vectorizer else "unavailable"
    except Exception as e:
        logger.error(f"Vectorizer initialization failed: {e}")
        status["vectorizer"] = "unavailable"

    # Create indices if Redis is available
    if redis_ok:
        indices_created = await create_indices(config=cfg)
        status["indices_created"] = "available" if indices_created else "unavailable"
    else:
        status["indices_created"] = "unavailable"

    # Initialize Docket infrastructure if Redis is available
    if redis_ok:
        docket_ok = await initialize_docket(config=cfg)
        status["docket_infrastructure"] = "available" if docket_ok else "unavailable"
    else:
        status["docket_infrastructure"] = "unavailable"

    # Test vector search index after creation (only if Redis is available)
    if redis_ok:
        vector_ok = await test_vector_search(config=cfg)
        status["vector_search"] = "available" if vector_ok else "unavailable"
    else:
        status["vector_search"] = "unavailable"

    return status


async def initialize_docket(config: Optional[Settings] = None) -> bool:
    """Initialize Docket task queue infrastructure.

    Args:
        config: Optional Settings object. If not provided, uses global settings.
            This enables dependency injection for testing without modifying
            environment variables.

    Returns:
        True if Docket infrastructure initialized successfully, False otherwise.
    """
    cfg = config or settings
    try:
        # Import Docket here to avoid circular imports
        from docket import Docket

        # Test Docket connection and ensure infrastructure is ready
        async with Docket(url=cfg.redis_url.get_secret_value(), name="sre_docket") as docket:
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

"""Health check endpoints for the Redis SRE Agent API."""

import json
import logging
from datetime import datetime, timezone

from docket.docket import Docket
from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.redis import initialize_redis_infrastructure
from redis_sre_agent.core.tasks import test_task_system

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_class=PlainTextResponse)
@router.head("/")
async def root_health_check():
    """Simple, fast health check for load balancer - no external dependencies."""
    return f"{settings.app_name} is running! 🚀"


@router.get("/health", response_model=None)
@router.head("/health")
async def detailed_health_check():
    """Comprehensive health check testing all system components."""

    # Test Redis infrastructure
    redis_status = await initialize_redis_infrastructure()

    # Test Docket task system
    task_system_ok = await test_task_system()

    # Test worker availability (non-blocking)
    try:
        async with Docket(url=settings.redis_url, name="sre_docket") as docket:
            workers = await docket.workers()
            workers_available = len(workers) > 0
    except Exception as e:
        logger.warning(f"Worker status check failed: {e}")
        workers_available = False

    # Compile component status
    components = {
        "redis_connection": redis_status.get("redis_connection", "unavailable"),
        "vectorizer": redis_status.get("vectorizer", "unavailable"),
        "indices_created": redis_status.get("indices_created", "unavailable"),
        "vector_search": redis_status.get("vector_search", "unavailable"),
        "task_system": "available" if task_system_ok else "unavailable",
        "workers": "available" if workers_available else "unavailable",
    }

    # Determine overall status
    all_healthy = all(status == "available" for status in components.values())
    status = "healthy" if all_healthy else "unhealthy"
    status_code = 200 if all_healthy else 503

    response_data = {
        "status": status,
        "components": components,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
        "settings": {
            "redis_url": (
                settings.redis_url.replace(settings.redis_password or "", "***")
                if settings.redis_password
                else settings.redis_url
            ),
            "embedding_model": settings.embedding_model,
            "task_queue": settings.task_queue_name,
        },
    }

    return Response(
        content=json.dumps(response_data, indent=2),
        status_code=status_code,
        media_type="application/json",
    )

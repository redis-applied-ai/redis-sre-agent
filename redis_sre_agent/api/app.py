"""Main FastAPI application for Redis SRE Agent."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from redis_sre_agent.api.health import router as health_router
from redis_sre_agent.api.instances import router as instances_router
from redis_sre_agent.api.knowledge import router as knowledge_router
from redis_sre_agent.api.metrics import router as metrics_router
from redis_sre_agent.api.middleware import setup_middleware
from redis_sre_agent.api.schedules import router as schedules_router
from redis_sre_agent.api.tasks import router as tasks_api_router
from redis_sre_agent.api.threads import router as threads_router
from redis_sre_agent.api.websockets import router as websockets_router
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.redis import initialize_redis
from redis_sre_agent.observability.tracing import setup_tracing as setup_base_tracing

# Configure logging with consistent format
# Note: When running via uvicorn with --log-config, this is overridden by logging_config.yaml
LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
)

logger = logging.getLogger(__name__)

# Global startup state for agent status checks


def setup_tracing(app: FastAPI) -> None:
    """Initialize OpenTelemetry tracing if an OTLP endpoint is configured.

    Uses the centralized tracing module for consistent span attributes
    and Redis filtering hooks.
    """
    # Setup base tracing (Redis with hooks, HTTP clients, OpenAI)
    if not setup_base_tracing(settings.app_name, "0.1.0"):
        return  # Tracing not enabled

    # Instrument FastAPI (exclude common health/docs paths)
    excluded = ",".join(
        [
            r"^/$",
            r"^/api/v1/$",
            r"^/api/v1/health$",
            r"^/api/v1/metrics$",
            r"^/api/v1/metrics/health$",
            r"^/metrics$",
            r"^/docs$",
            r"^/openapi\.json$",
        ]
    )
    FastAPIInstrumentor.instrument_app(app, excluded_urls=excluded)
    logger.info("OpenTelemetry tracing initialized (FastAPI + libs instrumented)")


_app_startup_state = {}


def get_app_startup_state():
    """Get the current startup state for the application."""
    return _app_startup_state.copy()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    logger.info(f"Starting up {settings.app_name}...")

    global _app_startup_state

    try:
        # Initialize Redis infrastructure
        redis_status = await initialize_redis()
        logger.info(f"Redis infrastructure status: {redis_status}")

        # Register SRE tasks with Docket
        # Note: The scheduler task is started by the worker, not the API

        try:
            from redis_sre_agent.core.docket_tasks import register_sre_tasks

            await register_sre_tasks()
            logger.info("✅ SRE tasks registered with Docket")
        except Exception as e:
            logger.warning(f"Failed to register SRE tasks: {e}")

        # Store startup state for agent status checks
        _app_startup_state = redis_status

        # Log configuration (mask Redis URL credentials)
        from redis_sre_agent.core.instances import mask_redis_url

        logger.info(f"Redis URL: {mask_redis_url(settings.redis_url.get_secret_value())}")
        logger.info(f"Embedding model: {settings.embedding_model}")
        logger.info(f"Debug mode: {settings.debug}")

        logger.info("✅ Startup completed successfully")

    except Exception as e:
        logger.error(f"⚠️ Startup had issues but continuing: {e}")
        # Don't fail completely - let the app start for health checks
        _app_startup_state = {"error": str(e)}

    yield

    # Shutdown
    logger.info("Shutting down FastAPI application...")
    # No Redis cleanup required; clients are not cached.


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="An AI-powered SRE agent for Redis infrastructure management and troubleshooting",
    version="0.1.0",
    lifespan=lifespan,
    debug=settings.debug,
)

# Setup middleware
# Setup tracing (no-op if not configured)
setup_tracing(app)

setup_middleware(app)


# Add root endpoint for simple health checks (load balancers, etc.)
@app.get("/", response_class=PlainTextResponse)
@app.head("/")
async def root_health_check():
    """Simple, fast health check for load balancer - no external dependencies."""
    return f"{settings.app_name} is running! 🚀"


# Include routers
app.include_router(health_router, prefix="/api/v1", tags=["Health"])
app.include_router(metrics_router, prefix="/api/v1", tags=["Metrics"])
app.include_router(instances_router, prefix="/api/v1", tags=["Instances"])
app.include_router(knowledge_router, tags=["Knowledge"])
# Mount the Threads/Tasks APIs under /api/v1
app.include_router(threads_router, prefix="/api/v1", tags=["Threads"])
app.include_router(tasks_api_router, prefix="/api/v1", tags=["Tasks"])

app.include_router(schedules_router, tags=["Schedules"])
app.include_router(websockets_router, prefix="/api/v1", tags=["WebSockets"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "redis_sre_agent.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        log_config="logging_config.yaml",
    )

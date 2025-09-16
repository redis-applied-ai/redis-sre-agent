"""Main FastAPI application for Redis SRE Agent."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from redis_sre_agent.api.agent import router as agent_router
from redis_sre_agent.api.health import router as health_router
from redis_sre_agent.api.middleware import setup_middleware
from redis_sre_agent.api.tasks import router as tasks_router
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.redis import cleanup_redis_connections, initialize_redis_infrastructure

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global startup state for agent status checks
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
        redis_status = await initialize_redis_infrastructure()
        logger.info(f"Redis infrastructure status: {redis_status}")

        # Register SRE tasks with Docket
        try:
            from redis_sre_agent.core.tasks import register_sre_tasks
            await register_sre_tasks()
            logger.info("✅ SRE tasks registered with Docket")
        except Exception as e:
            logger.warning(f"Failed to register SRE tasks: {e}")

        # Store startup state for agent status checks
        _app_startup_state = redis_status

        # Log configuration
        logger.info(f"Redis URL: {settings.redis_url}")
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

    try:
        await cleanup_redis_connections()
        logger.info("✅ Shutdown completed successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="An AI-powered SRE agent for Redis infrastructure management and troubleshooting",
    version="0.1.0",
    lifespan=lifespan,
    debug=settings.debug,
)

# Setup middleware
setup_middleware(app)

# Include routers
app.include_router(health_router, tags=["Health"])
app.include_router(agent_router, prefix="/api/v1", tags=["Agent"])
app.include_router(tasks_router, prefix="/api/v1", tags=["Tasks"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "redis_sre_agent.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )

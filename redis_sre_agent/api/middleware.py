"""FastAPI middleware for CORS, error handling, and logging.

NOTE: We use pure ASGI middleware instead of BaseHTTPMiddleware to avoid
issues with WebSocket connections. BaseHTTPMiddleware doesn't properly handle
WebSocket protocol upgrades and can cause "WebSocket closed before established"
errors. See: https://starlette.dev/middleware/#pure-asgi-middleware
"""

import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)


class LoggingMiddleware:
    """Pure ASGI middleware for logging HTTP requests and responses with timing.

    This middleware skips WebSocket connections (scope["type"] == "websocket")
    to avoid interfering with WebSocket handshakes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Skip non-HTTP connections (WebSocket, lifespan events)
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        request = Request(scope)

        # Log request
        logger.info(f"Request: {request.method} {request.url}")

        # Track response status code
        status_code: int = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                # Add timing header
                process_time = time.time() - start_time
                headers = list(message.get("headers", []))
                headers.append((b"x-process-time", str(process_time).encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
            process_time = time.time() - start_time
            logger.info(
                f"Response: {status_code} | Time: {process_time:.4f}s | Path: {request.url.path}"
            )
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"Request failed: {request.method} {request.url} | "
                f"Time: {process_time:.4f}s | "
                f"Error: {str(e)}"
            )
            raise


class ErrorHandlerMiddleware:
    """Pure ASGI middleware for global error handling.

    This middleware skips WebSocket connections (scope["type"] == "websocket")
    to avoid interfering with WebSocket handshakes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Skip non-HTTP connections (WebSocket, lifespan events)
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except Exception as e:
            request = Request(scope)
            # Log unexpected errors
            logger.exception(f"Unhandled error in {request.method} {request.url}: {e}")

            # Return generic error response
            response = JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "message": "An unexpected error occurred",
                    "path": str(request.url.path),
                    "method": request.method,
                },
            )
            await response(scope, receive, send)


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the FastAPI application."""

    # CORS middleware - allow frontend development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_hosts,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Custom middleware (order matters - first added is outermost)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(LoggingMiddleware)

    logger.info("Middleware setup completed")

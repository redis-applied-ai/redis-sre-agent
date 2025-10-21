"""Core tasks API for Redis SRE Agent.

This module provides a stable import surface for task-related utilities and
registration hooks. Tests may patch functions in this module to avoid side
effects during collection.
"""

from __future__ import annotations

import logging

# Re-export validate_url so call sites and tests can import from core.tasks
try:  # pragma: no cover - thin import shim
    from .docket_tasks import validate_url  # type: ignore
except Exception:  # pragma: no cover
    # In minimal environments docket_tasks may be unavailable; provide a stub
    async def validate_url(url: str, timeout: float = 5.0) -> dict:
        return {"url": url, "valid": False, "error": "validate_url unavailable"}


logger = logging.getLogger(__name__)


async def register_sre_tasks() -> None:
    """Register SRE background tasks.

    In runtime environments, this would register scheduled jobs or Docket tasks.
    The test suite patches this function to avoid side effects during import.
    """
    logger.debug("register_sre_tasks() called (no-op default implementation)")
    # Intentionally a no-op; real registration happens in production wiring.
    return None

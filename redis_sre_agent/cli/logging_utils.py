"""Shared CLI logging helpers."""

from __future__ import annotations

import logging
import os
from typing import Optional

_LOGGING_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _requested_log_level() -> Optional[int]:
    raw = (os.getenv("LOG_LEVEL") or "").strip()
    if not raw:
        return None
    return getattr(logging, raw.upper(), logging.INFO)


def configure_cli_logging() -> Optional[int]:
    """Configure CLI logging when LOG_LEVEL is explicitly set."""
    level = _requested_log_level()
    if level is None:
        return None

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=level, format=_LOGGING_FORMAT)
    root_logger.setLevel(level)
    for handler in root_logger.handlers:
        handler.setLevel(level)
    return level


def log_cli_exception(logger_name: str, message: str, exc: BaseException) -> None:
    """Emit CLI exception details when LOG_LEVEL requests logging."""
    level = configure_cli_logging()
    if level is None:
        return

    logger = logging.getLogger(logger_name)
    if logger.isEnabledFor(logging.DEBUG):
        logger.exception(message)
    else:
        logger.error("%s: %s", message, exc)

"""Shared helpers for administrative and task-oriented modules."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional


async def emit_progress(
    progress_emitter: Any,
    message: str,
    update_type: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a task update when a progress emitter is available."""
    if progress_emitter is not None:
        await progress_emitter.emit(message, update_type, metadata or {})


def decode_text(value: Any) -> str:
    """Decode Redis byte values into strings."""
    if isinstance(value, bytes):
        return value.decode()
    return str(value or "")


def parse_duration(value: str) -> timedelta:
    """Parse a duration like 7d, 24h, 15m, or 30s."""
    normalized = (value or "").strip().lower()
    try:
        if normalized.endswith("d"):
            return timedelta(days=float(normalized[:-1]))
        if normalized.endswith("h"):
            return timedelta(hours=float(normalized[:-1]))
        if normalized.endswith("m"):
            return timedelta(minutes=float(normalized[:-1]))
        if normalized.endswith("s"):
            return timedelta(seconds=float(normalized[:-1]))
        return timedelta(seconds=float(normalized))
    except Exception as exc:
        raise ValueError(f"Invalid duration '{value}': {exc}") from exc

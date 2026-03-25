"""Shared helpers for MCP index tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from redis_sre_agent.core.redis import (
    _iter_index_configs,
    get_index_schema_status,
    recreate_indices,
    sync_index_schemas,
)

VALID_INDEX_NAMES = {
    "knowledge",
    "skills",
    "support_tickets",
    "schedules",
    "threads",
    "tasks",
    "instances",
    "clusters",
}


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value or "")


def _normalize_index_name(index_name: Optional[str]) -> Optional[str]:
    normalized = (index_name or "").strip().lower()
    if not normalized or normalized == "all":
        return None
    if normalized not in VALID_INDEX_NAMES:
        valid = ", ".join(sorted(VALID_INDEX_NAMES | {"all"}))
        raise ValueError(f"Invalid index_name '{index_name}'. Valid values: {valid}")
    return normalized


async def list_indices_helper(
    *,
    index_name: Optional[str] = None,
    config=None,
) -> Dict[str, Any]:
    """List known index status and document counts."""
    normalized_index_name = _normalize_index_name(index_name)
    result: Dict[str, Any] = {
        "success": True,
        "requested_index": normalized_index_name or "all",
        "indices": [],
    }

    for name, idx_name, get_fn, _schema in _iter_index_configs():
        if normalized_index_name and name != normalized_index_name:
            continue

        try:
            idx = await get_fn(config=config)
            exists = await idx.exists()
            entry: Dict[str, Any] = {
                "name": name,
                "index_name": idx_name,
                "exists": exists,
            }
            if not exists:
                entry["num_docs"] = 0
                result["indices"].append(entry)
                continue

            try:
                raw_info = await idx._redis_client.execute_command("FT.INFO", idx_name)
                info = {
                    _decode(raw_info[i]): raw_info[i + 1]
                    for i in range(0, len(raw_info), 2)
                }
                entry["num_docs"] = int(_decode(info.get("num_docs", 0)))
            except Exception:
                entry["num_docs"] = "?"

            result["indices"].append(entry)
        except Exception as exc:
            result["success"] = False
            result["indices"].append(
                {
                    "name": name,
                    "index_name": idx_name,
                    "exists": False,
                    "error": str(exc),
                }
            )

    return result


async def get_index_schema_status_helper(
    *,
    index_name: Optional[str] = None,
    config=None,
) -> Dict[str, Any]:
    """Return schema drift status for one or all indices."""
    normalized_index_name = _normalize_index_name(index_name)
    return await get_index_schema_status(index_name=normalized_index_name, config=config)


async def recreate_indices_helper(
    *,
    index_name: Optional[str] = None,
    confirm: bool = False,
    config=None,
) -> Dict[str, Any]:
    """Recreate one or all indices after confirmation."""
    normalized_index_name = _normalize_index_name(index_name)
    if not confirm:
        return {
            "success": False,
            "status": "cancelled",
            "error": "Confirmation required",
            "index_name": normalized_index_name or "all",
        }
    return await recreate_indices(index_name=normalized_index_name, config=config)


async def sync_index_schemas_helper(
    *,
    index_name: Optional[str] = None,
    confirm: bool = False,
    config=None,
) -> Dict[str, Any]:
    """Create or recreate drifted indices after confirmation."""
    normalized_index_name = _normalize_index_name(index_name)
    if not confirm:
        return {
            "success": False,
            "status": "cancelled",
            "error": "Confirmation required",
            "index_name": normalized_index_name or "all",
        }
    return await sync_index_schemas(index_name=normalized_index_name, config=config)

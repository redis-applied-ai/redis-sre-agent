"""Shared heuristics for cluster-scoped diagnostic query detection."""

from __future__ import annotations

from typing import Final

_CLUSTER_DB_DIAGNOSTIC_SIGNAL_TERMS: Final[tuple[str, ...]] = (
    "memory",
    "slowlog",
    "latency",
    "throughput",
    "connections",
    "connected clients",
    "client list",
    "config",
    "keyspace",
    "keys",
    "replication",
    "failover",
    "performance",
    "hot key",
    "health check",
    "diagnostic",
    "triage",
    "database",
    "db",
)


def cluster_query_requests_db_diagnostics(query: str, conversation_context: str = "") -> bool:
    """Detect whether cluster-scoped query text implies DB/instance diagnostics."""
    text = f"{query or ''} {conversation_context or ''}".lower()
    if not text.strip():
        return False
    return any(term in text for term in _CLUSTER_DB_DIAGNOSTIC_SIGNAL_TERMS)

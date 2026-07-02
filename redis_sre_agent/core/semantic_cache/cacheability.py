"""Cacheability gate for the semantic answer cache write path.

Only successful **grounded** answers are stored. An *ungrounded* answer — one
produced with no knowledge-base search results — is the only hard write
exclusion (there is no authz/PII model, so nothing else gates storage). See
``docs/design/semantic-cache-knowledge-agent.md`` §H/§I.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CacheDecision:
    """Outcome of the cacheability gate."""

    cacheable: bool
    reason: str


def decide_cacheability(
    knowledge_search_results: Optional[List[Dict[str, Any]]],
    *,
    response: Optional[str] = None,
) -> CacheDecision:
    """Decide whether a freshly generated answer may be stored.

    Args:
        knowledge_search_results: The accumulated ``knowledge_search_results``
            from the agent run. Empty/None means the answer is *ungrounded*.
        response: The generated answer text; an empty answer is never stored.

    Returns:
        A :class:`CacheDecision`. ``cacheable`` is True only for a non-empty
        answer backed by at least one knowledge-search result.
    """
    if response is not None and not str(response).strip():
        return CacheDecision(False, "empty_response")
    if not knowledge_search_results:
        return CacheDecision(False, "ungrounded")
    return CacheDecision(True, "grounded")

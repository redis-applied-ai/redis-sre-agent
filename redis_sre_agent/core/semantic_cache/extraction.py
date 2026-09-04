"""Entity-ID and query-version extraction for the semantic cache.

Identifier queries need an *exact* identifier match (``RET-4421`` != ``RET-4422``)
but *paraphrase* reuse for the same ID. We scope those by an ``entity_id``
attribute. Versions are a *separate axis* (the ``version`` lookup filter), so a
token must never be classified as both.

This is net-new work: the existing ``_looks_like_support_ticket_identifier`` is
shape-only and classifies ``7.8`` as an identifier, and the existing
``_SOURCE_VERSION_RE`` only reads versions from doc *source paths*, not query
text. See ``docs/design/semantic-cache-knowledge-agent.md`` §I.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Default version axis value when the query pins no version.
DEFAULT_VERSION = "latest"

# Query-text version detector (NEW — there is no query-text version detector in
# the codebase today). Matches: "7.8", "v7.8", "version 7.2", "in 7.4". The
# optional "v"/"version" prefix is consumed before the digits so that the
# anchoring word boundary sits before the (optional) prefix, not between "v" and
# the digit (where there is none in "v7.8").
_QUERY_VERSION_RE = re.compile(
    r"\bv?(?:ersion)?\s*(\d+\.\d+)\b",
    re.IGNORECASE,
)

# Tight ticket-ID pattern (NEW — replaces the catch-all shape regex). Real ticket
# format like ``RET-4421``. Excludes ``7.8``, ``maxmemory``, ``OOM``, bare digits.
_TICKET_ID_RE = re.compile(r"\b([A-Z]{2,}-\d+)\b")


@dataclass(frozen=True)
class CacheScope:
    """The lookup scope resolved from a query.

    ``version`` always resolves (defaults to ``latest``). ``entity_id`` is set
    only for identifier queries that match the tight ticket-ID format.
    """

    version: str = DEFAULT_VERSION
    entity_id: Optional[str] = None
    # True when the query names more than one distinct ticket ID. Multi-entity
    # questions are deferred (§J): v1 neither serves nor stores them, since a
    # single-valued entity_id can't represent a multi-ticket answer.
    multi_entity: bool = False


def extract_query_version(query: str) -> str:
    """Resolve the requested version from query text, defaulting to ``latest``.

    Returns the first ``major.minor`` mention (e.g. ``7.8``) or ``latest``.
    """
    if not query:
        return DEFAULT_VERSION
    match = _QUERY_VERSION_RE.search(query)
    if match:
        return match.group(1)
    return DEFAULT_VERSION


def extract_entity_id(query: str, *, version: Optional[str] = None) -> Optional[str]:
    """Extract a support-ticket ``entity_id`` from query text, version-first.

    A token becomes ``entity_id`` only if it matches the tight ticket-ID format
    *and* is not the resolved version token. Bare version tokens (``7.8``) and
    non-identifier tokens (``maxmemory``, ``OOM``) never match.
    """
    if not query:
        return None
    resolved_version = version if version is not None else extract_query_version(query)
    match = _TICKET_ID_RE.search(query)
    if not match:
        return None
    candidate = match.group(1)
    # Version-first precedence: a token claimed by the version axis is never an
    # entity. (Ticket IDs contain a hyphen and no dot, so this is belt-and-braces.)
    if candidate == resolved_version:
        return None
    return candidate


def extract_cache_scope(query: str) -> CacheScope:
    """Resolve the full cache lookup scope (version + optional entity_id).

    If the query names more than one distinct ticket ID it is flagged
    ``multi_entity`` (deferred per §J) so the caller can skip serving/storing it,
    rather than silently caching under whichever ticket happened to match first.
    """
    version = extract_query_version(query)
    ticket_ids = [tid for tid in _TICKET_ID_RE.findall(query or "") if tid != version]
    if len(set(ticket_ids)) > 1:
        return CacheScope(version=version, entity_id=None, multi_entity=True)
    entity_id = ticket_ids[0] if ticket_ids else None
    return CacheScope(version=version, entity_id=entity_id)

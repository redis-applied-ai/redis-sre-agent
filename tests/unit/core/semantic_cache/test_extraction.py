"""US-004: entity-ID + query-version extraction (version-first precedence)."""

import pytest

from redis_sre_agent.core.semantic_cache.extraction import (
    extract_cache_scope,
    extract_entity_id,
    extract_query_version,
)


@pytest.mark.parametrize(
    "query,expected",
    [
        ("what changed in 7.8?", "7.8"),
        ("upgrade to v7.8 now", "7.8"),
        ("behaviour in version 7.2", "7.2"),
        ("how does it work in 7.4", "7.4"),
        ("how do I configure maxmemory?", "latest"),
        ("", "latest"),
        ("ticket RET-4421 status", "latest"),
    ],
)
def test_extract_query_version(query, expected):
    assert extract_query_version(query) == expected


@pytest.mark.parametrize(
    "query",
    ["7.8", "version 7.2", "maxmemory policy", "OOM error", "what is 42 plus 1", ""],
)
def test_non_tickets_have_no_entity_id(query):
    """Versions, config directives, error tokens, bare numbers are not entities."""
    assert extract_entity_id(query) is None


@pytest.mark.parametrize(
    "query,expected",
    [
        ("status of RET-4421 ticket", "RET-4421"),
        ("INC-99 details", "INC-99"),
        ("look at ABC-1", "ABC-1"),
    ],
)
def test_ticket_ids_extracted(query, expected):
    assert extract_entity_id(query) == expected


def test_version_first_precedence_for_mixed_query():
    scope = extract_cache_scope("RET-4421 regression in 7.8")
    assert scope.version == "7.8"
    assert scope.entity_id == "RET-4421"


def test_plain_query_scope_defaults():
    scope = extract_cache_scope("how do I tune maxmemory-policy?")
    assert scope.version == "latest"
    assert scope.entity_id is None

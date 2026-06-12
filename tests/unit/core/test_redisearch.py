"""Tests for safe RediSearch query fragment helpers."""

import pytest

from redis_sre_agent.core.redisearch import (
    escape_redisearch_query_value,
    tag_contains_expression,
    tag_equals_expression,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("foo|bar/baz[prod]", r"foo\|bar\/baz\[prod\]"),
        ("prod cache/{tenant}:v1?", r"prod\ cache\/\{tenant\}\:v1\?"),
        ("name{one},two", r"name\{one\}\,two"),
        ("quote'\"back\\slash", r"quote\'\"back\\slash"),
        ("*literal*", r"\*literal\*"),
        ("I/O", r"I\/O"),
    ],
)
def test_escape_redisearch_query_value_escapes_common_user_symbols(value, expected):
    assert escape_redisearch_query_value(value) == expected


def test_tag_equals_expression_escapes_user_supplied_text():
    assert str(tag_equals_expression("name", "foo|bar/baz[prod]")) == (
        r"@name:{foo\|bar\/baz\[prod\]}"
    )


def test_tag_contains_expression_keeps_wildcards_outside_escaped_user_text():
    assert str(tag_contains_expression("name", "*prod/cache?")) == (r"@name:{*\*prod\/cache\?*}")

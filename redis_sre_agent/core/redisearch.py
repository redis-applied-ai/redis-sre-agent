"""Helpers for constructing RediSearch query fragments from user text."""

import re
from typing import Any

from redisvl.query.filter import FilterExpression
from redisvl.query.query import TokenEscaper

_REDISEARCH_ESCAPER = TokenEscaper(re.compile(r"[,.<>{}\[\]\\\"\':;!@#$%^&*()\-+=~\/ \?\|]"))


def escape_redisearch_query_value(value: Any) -> str:
    """Escape user-controlled text before inserting it into a RediSearch query."""
    return _REDISEARCH_ESCAPER.escape(str(value or ""))


def tag_equals_expression(field_name: str, value: Any) -> FilterExpression:
    """Build a TAG equality expression with user text escaped."""
    return FilterExpression(f"@{field_name}:{{{escape_redisearch_query_value(value)}}}")


def tag_contains_expression(field_name: str, value: Any) -> FilterExpression:
    """Build a TAG wildcard contains expression with user text escaped."""
    return FilterExpression(f"@{field_name}:{{*{escape_redisearch_query_value(value)}*}}")

"""Helper decorators for tool providers.

This module provides a @status_update decorator that tool providers can
attach to their coroutine methods. The decorator stores a format string
on the function object that is used to render a natural-language status
message before the tool executes.

Example:
    from redis_sre_agent.tools.decorators import status_update

    class MyProvider(ToolProvider):
        @status_update("I'm searching the knowledge base for {query}")
        async def search(self, query: str, limit: int = 5):
            ...

At runtime, the agent formats the string using the tool call arguments.
"""

from __future__ import annotations

from typing import Callable


def status_update(template: str) -> Callable:
    """Attach a status update template to a provider method.

    The template should be a Python format string using named fields
    matching the tool's argument names, e.g. "{query}".
    """

    def decorator(func: Callable) -> Callable:
        setattr(func, "_status_update_template", template)
        return func

    return decorator

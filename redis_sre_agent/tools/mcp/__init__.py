"""MCP (Model Context Protocol) tool provider integration.

This module provides dynamic tool providers that connect to MCP servers
and expose their tools to the agent.
"""

from redis_sre_agent.tools.mcp.provider import MCPToolProvider
from redis_sre_agent.tools.mcp.retrieval_optimizer import (
    DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG,
    get_retrieval_optimizer_config,
)

__all__ = [
    "MCPToolProvider",
    "get_retrieval_optimizer_config",
    "DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG",
]

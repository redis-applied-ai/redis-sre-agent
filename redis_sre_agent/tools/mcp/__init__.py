"""MCP (Model Context Protocol) tool provider integration.

This module provides dynamic tool providers that connect to MCP servers
and expose their tools to the agent.
"""

from redis_sre_agent.tools.mcp.provider import MCPToolProvider

__all__ = ["MCPToolProvider"]

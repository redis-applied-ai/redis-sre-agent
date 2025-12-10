"""MCP server for redis-sre-agent.

This module exposes the agent's capabilities as an MCP server, allowing
other agents to use the Redis SRE Agent's tools via the Model Context Protocol.

Exposed tools:
- triage: Start a triage session for Redis troubleshooting
- knowledge_search: Search the knowledge base for Redis documentation and runbooks
- list_instances: List all configured Redis instances
- create_instance: Create a new Redis instance configuration
"""

from redis_sre_agent.mcp_server.server import mcp

__all__ = ["mcp"]

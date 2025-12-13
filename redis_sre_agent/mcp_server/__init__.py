"""MCP server for redis-sre-agent.

This module exposes the agent's capabilities as an MCP server, allowing
other agents to use the Redis SRE Agent's tools via the Model Context Protocol.

Exposed tools (all prefixed with redis_sre_):

Task-based tools (require polling redis_sre_get_task_status):
- redis_sre_deep_triage: Comprehensive Redis issue analysis (2-10 min)
- redis_sre_general_chat: Quick Q&A with full toolset including external MCP tools
- redis_sre_database_chat: Redis-focused chat with selective MCP tool exclusion
- redis_sre_knowledge_query: Ask the Knowledge Agent a question

Utility tools (return immediately):
- redis_sre_knowledge_search: Direct search of knowledge base docs
- redis_sre_list_instances: List configured Redis instances
- redis_sre_create_instance: Create a new Redis instance configuration
- redis_sre_get_task_status: Check task progress, notifications, and results
- redis_sre_get_thread: Get full conversation history and results
"""

from redis_sre_agent.mcp_server.server import mcp

__all__ = ["mcp"]

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
- redis_sre_get_knowledge_fragments: Get all chunks for a document hash
- redis_sre_get_related_knowledge_fragments: Get nearby chunks around a fragment
- redis_sre_get_pipeline_status: Show pipeline artifacts and recent ingestion state
- redis_sre_get_pipeline_batch: Show manifest and ingestion details for a batch
- redis_sre_list_support_packages: List uploaded support packages
- redis_sre_get_support_package_info: Get metadata for a support package
- redis_sre_upload_support_package: Upload a support package
- redis_sre_extract_support_package: Extract a support package
- redis_sre_delete_support_package: Delete a support package
- redis_sre_search_support_tickets: Search support-ticket docs only
- redis_sre_get_support_ticket: Get full support-ticket content by ticket id
- redis_sre_list_instances: List configured Redis instances
- redis_sre_create_instance: Create a new Redis instance configuration
- redis_sre_get_task_status: Check task progress, notifications, and results
- redis_sre_get_thread: Get full conversation history and results
"""

from redis_sre_agent.mcp_server.server import mcp

__all__ = ["mcp"]

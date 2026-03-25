"""MCP server for redis-sre-agent.

This module exposes the agent's capabilities as an MCP server, allowing
other agents to use the Redis SRE Agent's tools via the Model Context Protocol.

Exposed tools (all prefixed with redis_sre_):

Task-based tools (require polling redis_sre_get_task_status):
- redis_sre_deep_triage: Comprehensive Redis issue analysis (2-10 min)
- redis_sre_general_chat: Quick Q&A with full toolset including external MCP tools
- redis_sre_database_chat: Redis-focused chat with selective MCP tool exclusion
- redis_sre_knowledge_query: Ask the Knowledge Agent a question
- redis_sre_run_pipeline_scrape: Run the scraping pipeline in the background
- redis_sre_run_pipeline_ingest: Ingest a batch in the background
- redis_sre_run_pipeline_full: Run scraping and ingestion together in the background
- redis_sre_prepare_source_documents: Prepare and optionally ingest source documents
- redis_sre_generate_pipeline_runbooks: Run pipeline runbook operations in the background
- redis_sre_cleanup_pipeline_batches: Remove old pipeline batches in the background
- redis_sre_generate_runbook: Generate a Redis SRE runbook in the background
- redis_sre_evaluate_runbooks: Evaluate runbook markdown files in the background

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
- redis_sre_cache_stats: Show tool cache statistics
- redis_sre_cache_clear: Clear cached tool outputs
- redis_sre_version: Show Redis SRE Agent version metadata
- redis_sre_query: Queue a routed query with optional thread, target, and support-package context
- redis_sre_list_indices: List RediSearch indices and their document counts
- redis_sre_get_index_schema_status: Show schema drift status for one or all indices
- redis_sre_recreate_indices: Recreate RediSearch indices with confirmation
- redis_sre_sync_index_schemas: Recreate only missing or drifted indices with confirmation
- redis_sre_list_instances: List configured Redis instances
- redis_sre_get_instance: Get a configured Redis instance by id
- redis_sre_update_instance: Update a configured Redis instance
- redis_sre_delete_instance: Delete a configured Redis instance
- redis_sre_test_instance: Test a configured Redis instance connection
- redis_sre_test_redis_url: Test a Redis URL without creating an instance
- redis_sre_create_instance: Create a new Redis instance configuration
- redis_sre_get_task: Get a full task payload by task ID
- redis_sre_list_tasks: List tasks with status filtering
- redis_sre_purge_tasks: Purge tasks in bulk with safeguards
- redis_sre_get_task_status: Check task progress, notifications, and results
- redis_sre_get_thread: Get full conversation history and results
- redis_sre_get_thread_sources: Get recorded knowledge fragments for a thread
- redis_sre_get_thread_trace: Get tool-call trace and citations for a message
"""

from redis_sre_agent.mcp_server.server import mcp

__all__ = ["mcp"]

## CLI Reference (generated)

Generated from the Click command tree.


### Commands


- thread — Thread management commands.
- thread backfill — Backfill the threads FT.SEARCH index from existing thread data.
- thread backfill-empty-subjects — Set subject for threads where subject is empty/placeholder.

    Derives subject from context.original_query or the first user message.
- thread backfill-scheduled-subjects — Set subject to schedule_name for existing scheduled threads missing a subject.

    A thread is considered scheduled if any of the following hold:
    - metadata.user_id == 'scheduler'
    - 'scheduled' in metadata.tags
    - context.automated is True and context.schedule_name exists
- thread get — Get full thread details by ID.
- thread list — List threads (shows all threads by default, ordered by Redis index).
- thread purge — Delete threads in bulk with safeguards.

    By default requires --older-than DURATION unless --all is specified.
- thread reindex — Recreate the threads FT.SEARCH index and backfill from existing thread data.
- thread sources — List knowledge fragments retrieved for a thread (optionally a specific turn).
- schedule — Schedule management commands.
- schedule create — Create a new schedule.
- schedule delete — Delete a schedule.
- schedule disable — Disable a schedule.
- schedule enable — Enable a schedule.
- schedule get — Get a single schedule by ID.
- schedule list — List schedules in the system.
- schedule run-now — Trigger a schedule to run immediately (enqueue an agent turn).
- schedule runs — List recent runs for a schedule.
- schedule update — Update fields of an existing schedule.
- instance — Manage Redis instances
- instance create — Create a new Redis instance.
- instance delete — Delete an instance by ID.
- instance get — Get a single instance by ID.
- instance list — List configured Redis instances.
- instance test — Test connection to a configured instance by ID.
- instance test-url — Test a Redis connection URL without creating an instance.
- instance update — Update fields of an existing instance.
- task — Task management commands.
- task get — Get a task by TASK_ID and show details.
- task list — List recent tasks and their statuses.

    Default: show only in-progress and scheduled (queued) tasks.
    Use --all to show all statuses, or --status to filter to a single status.
- task purge — Delete tasks in bulk with safeguards.

    By default requires --older-than DURATION (and optionally --status), unless --all.
- knowledge — Knowledge base management commands.
- knowledge fragments — Fetch all fragments for a document by document hash.
- knowledge related — Fetch related fragments around a chunk index for a document.
- knowledge search — Search the knowledge base (query helpers group).
- pipeline — Data pipeline commands for scraping and ingestion.
- pipeline cleanup — Clean up old batch directories.
- pipeline full — Run the complete pipeline: scraping + ingestion.
- pipeline ingest — Run the ingestion pipeline to process scraped documents.
- pipeline prepare-sources — Prepare source documents as batch artifacts, optionally ingest them.
- pipeline runbooks — Generate standardized runbooks from web sources using GPT-5.
- pipeline scrape — Run the scraping pipeline to collect SRE documents.
- pipeline show-batch — Show detailed information about a specific batch.
- pipeline status — Show pipeline status and available batches.
- runbook — Redis SRE runbook generation and management commands.
- runbook evaluate — Evaluate existing runbooks in the source documents directory.
- runbook generate — Generate a new Redis SRE runbook for the specified topic.
- query — Execute an agent query.

    Supports conversation threads for multi-turn interactions. Use --thread-id
    to continue an existing conversation, or omit it to start a new one.

    
    The agent is automatically selected based on the query:
      - Knowledge agent: General Redis questions (no instance)
      - Chat agent: Quick questions with a Redis instance
      - Triage agent: Full health checks or --triage flag
- worker — Start the background worker.
- mcp — MCP server commands - expose agent capabilities via Model Context Protocol.
- mcp list-tools — List available MCP tools.
- mcp serve — Start the MCP server.

    The MCP server exposes the Redis SRE Agent's capabilities to other
    MCP-compatible AI agents.

    
    Available tools:
      - triage: Start a Redis troubleshooting session
      - get_task_status: Check if a triage task is complete
      - get_thread: Get the full results from a triage
      - knowledge_search: Search Redis documentation and runbooks
      - list_instances: List configured Redis instances
      - create_instance: Register a new Redis instance

    
    Examples:
      # Run in stdio mode (for Claude Desktop local config)
      redis-sre-agent mcp serve

    
      # Run in HTTP mode (for Claude remote connector - RECOMMENDED)
      redis-sre-agent mcp serve --transport http --port 8081
      # Then add in Claude: Settings > Connectors > Add Custom Connector
      # URL: http://your-host:8081/mcp

    
      # Run in SSE mode (legacy, for older clients)
      redis-sre-agent mcp serve --transport sse --port 8081
- index — RediSearch index management commands.
- index list — List all SRE agent indices and their status.
- index recreate — Drop and recreate RediSearch indices.

    This is useful when the schema has changed (e.g., new fields added).
    WARNING: This will delete all indexed data. The underlying Redis keys
    remain, but you'll need to re-index documents.

See How-to guides for examples.

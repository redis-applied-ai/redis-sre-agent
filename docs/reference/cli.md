## CLI Reference (generated)

Generated from the Click command tree.


### Commands


- cache — Manage tool output cache.
- cache clear — Clear cached tool outputs.
- cache stats — Show cache statistics.
- thread — Thread management commands.
- thread backfill — Backfill the threads FT.SEARCH index from existing thread data.
- thread backfill-empty-subjects — Set subject for threads where subject is empty/placeholder.
- thread backfill-scheduled-subjects — Set subject to schedule_name for existing scheduled threads missing a subject.
- thread get — Get full thread details by ID.
- thread list — List threads (shows all threads by default, ordered by Redis index).
- thread purge — Delete threads in bulk with safeguards.
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
- task delete — Delete a single task by TASK_ID.
- task get — Get a task by TASK_ID and show details.
- task list — List recent tasks and their statuses.
- task purge — Delete tasks in bulk with safeguards.
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
- worker — Manage the Docket worker.
- worker start — Start the background worker.
- worker status — Check the status of the Docket worker.
- worker stop — Stop the Docket worker.
- mcp — MCP server commands - expose agent capabilities via Model Context Protocol.
- mcp list-tools — List available MCP tools.
- mcp serve — Start the MCP server.
- index — RediSearch index management commands.
- index list — List all SRE agent indices and their status.
- index recreate — Drop and recreate RediSearch indices.
- support-package — Manage support packages.
- support-package delete — Delete a support package.
- support-package extract — Extract a support package.
- support-package info — Get information about a support package.
- support-package list — List uploaded support packages.
- support-package upload — Upload a support package.
- version — Show the Redis SRE Agent version.

See How-to guides for examples.

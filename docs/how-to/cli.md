## CLI User Guide

The redis-sre-agent CLI lets you manage instances, run triage, operate pipelines, and inspect tasks/threads.

### Basics
- Help: `uv run redis-sre-agent --help`
- Subcommands: `instance`, `query`, `knowledge`, `pipeline`, `runbook`, `schedule`, `task`, `thread`, `worker`

### Instances
List, create, update, test target Redis instances.
```bash
# List instances
uv run redis-sre-agent instance list

# Create an instance (adjust URL/env/usage/description)
uv run redis-sre-agent instance create \
  --name demo \
  --connection-url redis://localhost:7844/0 \
  --environment development \
  --usage cache \
  --description "Demo Redis"

# Test an existing instance by ID
uv run redis-sre-agent instance test --id <instance_id>

# Test a raw URL without creating an instance
uv run redis-sre-agent instance test-url --connection-url redis://host:6379/0
```

### Query
Run an agent query, optionally scoped to an instance.
```bash
uv run redis-sre-agent query "Check memory pressure and slow ops" -r <instance_id>
```

### Worker
Start the background worker (executes tasks enqueued by the API/CLI).
```bash
uv run redis-sre-agent worker --concurrency 4
```

### Threads
Threads represent conversational sessions or task contexts.
```bash
# List recent threads
uv run redis-sre-agent thread list

# Show a thread
uv run redis-sre-agent thread get <thread_id>

# Show knowledge sources retrieved for a thread
uv run redis-sre-agent thread sources <thread_id>
```

Maintenance utilities
```bash
# Reindex threads search index
uv run redis-sre-agent thread reindex
# Backfill index or missing subjects
uv run redis-sre-agent thread backfill
uv run redis-sre-agent thread backfill-empty-subjects
uv run redis-sre-agent thread backfill-scheduled-subjects
```

### Tasks
Inspect task execution status.
```bash
# List recent tasks
uv run redis-sre-agent task list
# Show details for a task
uv run redis-sre-agent task get <task_id>
```

### Schedules
Create scheduled triage runs.
```bash
# Create a schedule
uv run redis-sre-agent schedule create \
  --name daily-triage \
  --cron "0 9 * * *" \
  --redis-instance <instance_id> \
  --query "Daily health check"

# Trigger immediately
uv run redis-sre-agent schedule run-now --id <schedule_id>

# Enable/disable, list, get, update, delete
uv run redis-sre-agent schedule enable --id <schedule_id>
uv run redis-sre-agent schedule disable --id <schedule_id>
uv run redis-sre-agent schedule list
uv run redis-sre-agent schedule get <schedule_id>
uv run redis-sre-agent schedule update --id <schedule_id> --name "new-name"
uv run redis-sre-agent schedule delete --id <schedule_id>
```

### Knowledge
Query the knowledge base.
```bash
# Search by text
uv run redis-sre-agent knowledge search --query "redis eviction policy"
# Inspect fragments around a document chunk
uv run redis-sre-agent knowledge fragments --doc-hash <hash>
uv run redis-sre-agent knowledge related --doc-hash <hash> --chunk-index 0
```

### Pipelines
Collect and ingest SRE knowledge sources.
```bash
# Prepare source docs into a batch directory
uv run redis-sre-agent pipeline prepare-sources

# Scrape web sources into artifacts
uv run redis-sre-agent pipeline scrape

# Ingest prepared/scraped artifacts
uv run redis-sre-agent pipeline ingest

# Run full pipeline (prepare + scrape + ingest)
uv run redis-sre-agent pipeline full

# Show batches and status
uv run redis-sre-agent pipeline status
uv run redis-sre-agent pipeline show-batch --batch <name>

# Cleanup old batches
uv run redis-sre-agent pipeline cleanup --keep 3
```

### Runbooks
Generate or evaluate standardized Redis SRE runbooks.
```bash
# Generate a runbook for a topic
uv run redis-sre-agent runbook generate --topic "Redis memory troubleshooting"

# Evaluate existing runbooks
uv run redis-sre-agent runbook evaluate
```

### Tips
- Use `--help` on any subcommand to see all options and flags
- Ensure environment variables are set (OPENAI_API_KEY, REDIS_URL, TOOLS_PROMETHEUS_URL, etc.)
- For containerized runs, prefer `docker compose exec -T sre-agent uv run redis-sre-agent ...` to use in-cluster URLs

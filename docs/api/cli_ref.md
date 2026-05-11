---
description: Auto-generated reference for every redis-sre-agent subcommand.
---

# CLI reference

This page is generated from the Click command tree. Run `redis-sre-agent <command> --help` for full flag descriptions and examples. For end-to-end workflows, see [CLI workflows](../user_guide/how_to_guides/cli_workflows.md).

## Command groups

| Command | Description |
|---|---|
| `redis-sre-agent cache` | Manage tool output cache. |
| `redis-sre-agent thread` | Thread management commands. |
| `redis-sre-agent schedule` | Schedule management commands. |
| `redis-sre-agent instance` | Manage Redis instances |
| `redis-sre-agent cluster` | Manage Redis clusters |
| `redis-sre-agent task` | Task management commands. |
| `redis-sre-agent knowledge` | Knowledge base management commands. |
| `redis-sre-agent skills` | Inspect and scaffold Agent Skills packages. |
| `redis-sre-agent pipeline` | Data pipeline commands for scraping and ingestion. |
| `redis-sre-agent runbook` | Redis SRE runbook generation and management commands. |
| `redis-sre-agent worker` | Manage the Docket worker. |
| `redis-sre-agent mcp` | MCP server commands - expose agent capabilities via Model Context Protocol. |
| `redis-sre-agent index` | RediSearch index management commands. |
| `redis-sre-agent support-package` | Manage support packages. |
| `redis-sre-agent eval` | Run eval scenario utilities and live suites. |

## cache

Manage tool output cache.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent cache clear` |  | Clear cached tool outputs. |
| `redis-sre-agent cache stats` |  | Show cache statistics. |

## thread

Thread management commands.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent thread backfill` |  | Backfill the threads FT.SEARCH index from existing thread data. |
| `redis-sre-agent thread backfill-empty-subjects` |  | Set subject for threads where subject is empty/placeholder. |
| `redis-sre-agent thread backfill-scheduled-subjects` |  | Set subject to schedule_name for existing scheduled threads missing a subject. |
| `redis-sre-agent thread get` | `THREAD_ID` | Get full thread details by ID. |
| `redis-sre-agent thread list` |  | List threads (shows all threads by default, ordered by Redis index). |
| `redis-sre-agent thread purge` |  | Delete threads in bulk with safeguards. |
| `redis-sre-agent thread reindex` |  | Recreate the threads FT.SEARCH index and backfill from existing thread data. |
| `redis-sre-agent thread sources` | `THREAD_ID` | List knowledge fragments retrieved for a thread (optionally a specific turn). |
| `redis-sre-agent thread trace` | `MESSAGE_ID` | Show the decision trace for a single message. |

## schedule

Schedule management commands.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent schedule create` | `--name TEXT` `--interval-type [minutes\|hours\|days\|weeks]` `--interval-value INTEGER` `--instructions TEXT` | Create a new schedule. |
| `redis-sre-agent schedule delete` | `SCHEDULE_ID` | Delete a schedule. |
| `redis-sre-agent schedule disable` | `SCHEDULE_ID` | Disable a schedule. |
| `redis-sre-agent schedule enable` | `SCHEDULE_ID` | Enable a schedule. |
| `redis-sre-agent schedule get` | `SCHEDULE_ID` | Get a single schedule by ID. |
| `redis-sre-agent schedule list` |  | List schedules in the system. |
| `redis-sre-agent schedule run-now` | `SCHEDULE_ID` | Trigger a schedule to run immediately (enqueue an agent turn). |
| `redis-sre-agent schedule runs` | `SCHEDULE_ID` | List recent runs for a schedule. |
| `redis-sre-agent schedule update` | `SCHEDULE_ID` | Update fields of an existing schedule. |

## instance

Manage Redis instances

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent instance create` | `--name TEXT` `--connection-url TEXT` `--environment [development\|staging\|production\|test]` `--usage [cache\|analytics\|session\|queue\|custom]` `--description TEXT` | Create a new Redis instance. |
| `redis-sre-agent instance delete` | `INSTANCE_ID` | Delete an instance by ID. |
| `redis-sre-agent instance get` | `INSTANCE_ID` | Get a single instance by ID. |
| `redis-sre-agent instance list` |  | List configured Redis instances. |
| `redis-sre-agent instance test` | `INSTANCE_ID` | Test connection to a configured instance by ID. |
| `redis-sre-agent instance test-url` | `--connection-url TEXT` | Test a Redis connection URL without creating an instance. |
| `redis-sre-agent instance update` | `INSTANCE_ID` | Update fields of an existing instance. |

## cluster

Manage Redis clusters

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent cluster backfill-instance-links` |  | Backfill cluster links for existing instance records. |
| `redis-sre-agent cluster create` | `--name TEXT` `--environment [development\|staging\|production\|test]` `--description TEXT` | Create a new Redis cluster. |
| `redis-sre-agent cluster delete` | `CLUSTER_ID` | Delete a cluster by ID. |
| `redis-sre-agent cluster get` | `CLUSTER_ID` | Get a single cluster by ID. |
| `redis-sre-agent cluster list` |  | List configured Redis clusters. |
| `redis-sre-agent cluster update` | `CLUSTER_ID` | Update fields of an existing cluster. |

## task

Task management commands.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent task delete` | `TASK_ID` | Delete a single task by TASK_ID. |
| `redis-sre-agent task get` | `TASK_ID` | Get a task by TASK_ID and show details. |
| `redis-sre-agent task list` |  | List recent tasks and their statuses. |
| `redis-sre-agent task purge` |  | Delete tasks in bulk with safeguards. |

## knowledge

Knowledge base management commands.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent knowledge fragments` | `DOCUMENT_HASH` | Fetch all fragments for a document by document hash. |
| `redis-sre-agent knowledge related` | `DOCUMENT_HASH` `--chunk-index INTEGER` | Fetch related fragments around a chunk index for a document. |
| `redis-sre-agent knowledge search` | `[QUERY]...` | Search the knowledge base (query helpers group). |

## skills

Inspect and scaffold Agent Skills packages.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent skills list` |  | List skills from the active skill backend. |
| `redis-sre-agent skills read-reference` | `SKILL_NAME` `RESOURCE_PATH` | Alias for reading a reference resource by path. |
| `redis-sre-agent skills read-resource` | `SKILL_NAME` `RESOURCE_PATH` | Read one resource from an Agent Skills package. |
| `redis-sre-agent skills scaffold` | `LEGACY_SKILL_PATH` `TARGET_DIR` | Scaffold an Agent Skills package from a legacy markdown skill. |
| `redis-sre-agent skills show` | `SKILL_NAME` | Show one skill manifest or legacy skill body. |

## pipeline

Data pipeline commands for scraping and ingestion.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent pipeline cleanup` |  | Clean up old batch directories. |
| `redis-sre-agent pipeline full` |  | Run the complete pipeline: scraping + ingestion. |
| `redis-sre-agent pipeline ingest` |  | Run the ingestion pipeline to process scraped documents. |
| `redis-sre-agent pipeline prepare-sources` |  | Prepare source documents as batch artifacts, optionally ingest them. |
| `redis-sre-agent pipeline runbooks` |  | Generate standardized runbooks from web sources using GPT-5. |
| `redis-sre-agent pipeline scrape` |  | Run the scraping pipeline to collect SRE documents. |
| `redis-sre-agent pipeline show-batch` | `--batch-date TEXT` | Show detailed information about a specific batch. |
| `redis-sre-agent pipeline status` |  | Show pipeline status and available batches. |

## runbook

Redis SRE runbook generation and management commands.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent runbook evaluate` |  | Evaluate existing runbooks in the source documents directory. |
| `redis-sre-agent runbook generate` | `TOPIC` `SCENARIO_DESCRIPTION` | Generate a new Redis SRE runbook for the specified topic. |

## worker

Manage the Docket worker.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent worker start` |  | Start the background worker. |
| `redis-sre-agent worker status` |  | Check the status of the Docket worker. |
| `redis-sre-agent worker stop` |  | Stop the Docket worker. |

## mcp

MCP server commands - expose agent capabilities via Model Context Protocol.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent mcp list-tools` |  | List available MCP tools. |
| `redis-sre-agent mcp serve` |  | Start the MCP server. |

## index

RediSearch index management commands.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent index list` |  | List all SRE agent indices and their status. |
| `redis-sre-agent index recreate` |  | Drop and recreate RediSearch indices. |
| `redis-sre-agent index schema-status` |  | Show whether existing index schemas match the current code definitions. |
| `redis-sre-agent index sync-schemas` |  | Create or recreate only indices whose schema has drifted. |

## support-package

Manage support packages.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent support-package delete` | `PACKAGE_ID` | Delete a support package. |
| `redis-sre-agent support-package extract` | `PACKAGE_ID` | Extract a support package. |
| `redis-sre-agent support-package info` | `PACKAGE_ID` | Get information about a support package. |
| `redis-sre-agent support-package list` |  | List uploaded support packages. |
| `redis-sre-agent support-package upload` | `PATH` | Upload a support package. |

## eval

Run eval scenario utilities and live suites.

| Subcommand | Arguments | Description |
|---|---|---|
| `redis-sre-agent eval compare` | `BASELINE_DIR` `CANDIDATE_DIR` `--policy-file FILE` | Compare one live eval artifact directory against a baseline. |
| `redis-sre-agent eval list` |  | List known eval scenario ids. |
| `redis-sre-agent eval live-suite` | `SUITE_NAME` `--config FILE` `--output-dir DIRECTORY` | Run one configured live-model eval suite. |
| `redis-sre-agent eval run` | `SCENARIO_PATH` | Run one mocked eval scenario. |

## Top-level commands

| Command | Arguments | Description |
|---|---|---|
| `redis-sre-agent query` | `QUERY` | Execute an agent query. |
| `redis-sre-agent version` |  | Show the Redis SRE Agent version. |


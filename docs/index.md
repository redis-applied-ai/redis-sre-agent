# Redis SRE Agent

Redis SRE Agent gives platform teams an AI operator for Redis. It answers Redis questions from your docs and runbooks, inspects live Redis targets, and returns actionable triage with citations.

## Why it matters

- Reduce time from alert to first useful diagnosis.
- Combine static knowledge and live observability in one workflow.
- Run the same workflows through the CLI, API, schedules, or MCP.
- Keep your existing metrics, logs, and admin tooling through providers.

## Start here

- Fast local demo: [quickstarts/local.md](quickstarts/local.md)
- Full Docker walkthrough: [quickstarts/end-to-end-setup.md](quickstarts/end-to-end-setup.md)
- VM deployment with Redis Enterprise: [quickstarts/vm-deployment.md](quickstarts/vm-deployment.md)

## Common workflows

- Ad-hoc triage from the CLI: [how-to/cli.md](how-to/cli.md)
- Ad-hoc triage from the API: [how-to/api.md](how-to/api.md)
- Approval-aware task handling: [how-to/approvals.md](how-to/approvals.md)
- Eval system and live-suite workflows: [how-to/evals.md](how-to/evals.md)
- Agent Memory Server integration: [how-to/agent-memory-server-integration.md](how-to/agent-memory-server-integration.md)
- Scheduled health checks: [how-to/cli.md#7-schedule-recurring-checks](how-to/cli.md#7-schedule-recurring-checks)
- Provider and MCP integration: [how-to/tool-providers.md](how-to/tool-providers.md)
- Knowledge ingestion and search: [how-to/pipelines.md](how-to/pipelines.md)

## What a successful first run looks like

```bash
cp .env.example .env
make quick-demo

docker compose exec -T sre-agent uv run redis-sre-agent \
  query "What are Redis eviction policies?"
```

To investigate a live target, create or inspect an instance and query with `-r <instance_id>`.

## Concepts

See [Core Concepts](concepts/core.md) for details on agents, tasks, threads, providers, targets, and citations.

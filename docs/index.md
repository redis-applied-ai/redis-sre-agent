---
description: Redis SRE Agent documentation. LangGraph-based SRE agent for Redis triage and remediation.
---

<div class="rds-hero" markdown>

![Redis](assets/redis-logo-script-red.svg){ .rds-hero__logo }

# Redis SRE Agent

Diagnose and remediate Redis incidents with a LangGraph-based SRE agent
{ .rds-hero__tagline }

</div>

Redis SRE Agent gives platform teams an AI operator for Redis. It answers
Redis questions from your docs and runbooks, inspects live Redis targets,
and returns actionable triage with citations.

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **[Local quick start](user_guide/01_local_quickstart.md)**

    ---

    Boot the full local stack with Docker Compose and ask the agent its
    first question in five minutes.

-   :material-target:{ .lg .middle } **[Incident triage walkthrough](examples/incident_triage.md)**

    ---

    Watch the agent diagnose a real incident end to end on a seeded
    demo Redis.

-   :material-api:{ .lg .middle } **[API workflows](user_guide/how_to_guides/api_workflows.md)**

    ---

    Drive the agent over HTTP: tasks, threads, knowledge, schedules.

</div>

---

## Why it matters

- Reduce time from alert to first useful diagnosis.
- Combine static knowledge and live observability in one workflow.
- Run the same workflows through the CLI, API, schedules, or MCP.
- Keep your existing metrics, logs, and admin tooling through providers.

## Start here

- Fast local demo: [Local quick start](user_guide/01_local_quickstart.md)
- Full Docker walkthrough: [End-to-end walkthrough](user_guide/02_end_to_end.md)
- VM deployment with Redis Enterprise: [VM deployment](user_guide/03_vm_deployment.md)

## Common workflows

- Ad-hoc triage from the CLI: [CLI workflows](user_guide/how_to_guides/cli_workflows.md)
- Ad-hoc triage from the API: [API workflows](user_guide/how_to_guides/api_workflows.md)
- Eval system and live-suite workflows: [Evals](user_guide/how_to_guides/evals.md)
- Agent Memory Server integration: [Agent Memory Server integration](user_guide/how_to_guides/agent_memory_integration.md)
- Scheduled health checks: [Scheduling](user_guide/how_to_guides/scheduling.md)
- Provider and MCP integration: [Tool providers](user_guide/how_to_guides/tool_providers.md)
- Knowledge ingestion and search: [Pipelines](user_guide/how_to_guides/pipelines.md)

## What a successful first run looks like

```bash
cp .env.example .env
make quick-demo

docker compose exec -T sre-agent uv run redis-sre-agent \
  query "What are Redis eviction policies?"
```

To investigate a live target, create or inspect an instance and query
with `-r <instance_id>`.

---

## Explore the docs

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } **[Concepts](concepts/index.md)**

    ---

    Architecture, the triage loop, pipelines, and tool providers.

-   :material-rocket-launch:{ .lg .middle } **[User Guide](user_guide/index.md)**

    ---

    Tutorials and how-to recipes. Local install, end-to-end walkthrough, VM deployment.

-   :material-lightbulb-on:{ .lg .middle } **[Examples](examples/index.md)**

    ---

    Worked scenarios: incident triage and custom tool providers.

-   :material-api:{ .lg .middle } **[API Reference](api/index.md)**

    ---

    REST, CLI, configuration, and the full `redis_sre_agent` Python package.

</div>

## Concepts

See [Core architecture](concepts/core.md) for details on agents, tasks,
threads, providers, targets, and citations.

## For AI agents

If you are an AI agent reading these docs, start with
[`AGENTS.md`](https://github.com/redis-applied-ai/redis-sre-agent/blob/main/AGENTS.md)
at the repo root for usage notes, or
[For AI Agents](for-ais-only/index.md) for an internal map of the source
tree. A flat [`llms.txt`](llms.txt) index of every doc page is generated
at build time.

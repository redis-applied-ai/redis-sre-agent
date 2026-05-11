---
description: How-to guides for the Redis SRE Agent.
---

# How-To Guides

Task-oriented recipes. Each one assumes you already know the basics from
the numbered tutorials and answers a single "how do I..." question.

## Connect and configure

<div class="grid cards" markdown>

-   :material-link-variant:{ .lg .middle } **[Connect to Redis](connect_to_redis.md)**

    ---

    Single, cluster, sentinel; TLS; ACLs.

-   :material-cog:{ .lg .middle } **[Configuration](configuration.md)**

    ---

    Environment variables and runtime options.

-   :material-laptop:{ .lg .middle } **[Local development](local_dev.md)**

    ---

    Run the agent against a local Redis without the full stack.

</div>

## Drive the agent

<div class="grid cards" markdown>

-   :material-console:{ .lg .middle } **[CLI workflows](cli_workflows.md)**

    ---

    End-to-end task flows from the command line.

-   :material-api:{ .lg .middle } **[API workflows](api_workflows.md)**

    ---

    The same flows over HTTP, including approvals and WebSocket updates.

-   :material-monitor-dashboard:{ .lg .middle } **[Web UI](ui.md)**

    ---

    Run the experimental UI for browser-based triage and demos.

</div>

## Extend

<div class="grid cards" markdown>

-   :material-toolbox:{ .lg .middle } **[Tool providers](tool_providers.md)**

    ---

    Add new diagnostic or remediation tools the agent can call.

-   :material-pipe:{ .lg .middle } **[Pipelines](pipelines.md)**

    ---

    Customize the scrape and ingest pipelines.

-   :material-file-document-multiple:{ .lg .middle } **[Source documents](source_documents.md)**

    ---

    Add your own runbooks and knowledge sources.

-   :material-clock-outline:{ .lg .middle } **[Scheduling](scheduling.md)**

    ---

    Schedule background tasks and recurring health checks.

-   :material-test-tube:{ .lg .middle } **[Evals](evals.md)**

    ---

    Run the eval harness against the agent.

-   :material-brain:{ .lg .middle } **[Agent memory integration](agent_memory_integration.md)**

    ---

    Persist agent state across sessions with Agent Memory Server.

</div>

## Operate

See the [Operations](operations/index.md) section for production deployment
guides — Docker, observability, airgap, secret encryption, and known sharp
edges.

## Release tutorials

Hands-on walkthroughs of the user-facing features that shipped with each
release. See [Release tutorials](release_tutorials/index.md).

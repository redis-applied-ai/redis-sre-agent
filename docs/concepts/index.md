---
description: Foundational concepts for the Redis SRE Agent.
---

# Concepts

Foundational knowledge for understanding the Redis SRE Agent architecture
and its reasoning model.

<div class="grid cards" markdown>

-   :material-domain:{ .lg .middle } **[Core architecture](core.md)**

    ---

    LangGraph state machine, tool routing, agent memory, and FastAPI surface.

-   :material-refresh:{ .lg .middle } **[Triage loop](triage_loop.md)**

    ---

    The diagnose-investigate-act loop the agent runs on every incident.

-   :material-pipe:{ .lg .middle } **[Pipelines](pipelines.md)**

    ---

    Knowledge-base scrape, ingest, and refresh pipelines.

-   :material-toolbox:{ .lg .middle } **[Tool providers](tool_providers.md)**

    ---

    Plug-in surface for adding new diagnostic and remediation tools.

</div>

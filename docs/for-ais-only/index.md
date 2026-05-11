---
description: Internal AI-agent guide to the Redis SRE Agent source tree.
---

# For AI Agents Modifying the Redis SRE Agent

This section is the internal counterpart to the user-facing
[AGENTS.md](https://github.com/redis-applied-ai/redis-sre-agent/blob/main/AGENTS.md).
It exists for an agent that has been asked to *change* the project: add a
new tool provider, fix a pipeline, extend the API surface.

<div class="grid cards" markdown>

-   :material-map:{ .lg .middle } **[Repository map](REPOSITORY_MAP.md)**

    ---

    Top-down map of every package and module with its responsibility.

-   :material-hammer-wrench:{ .lg .middle } **[Build and test](BUILD_AND_TEST.md)**

    ---

    The exact commands CI runs, plus the local equivalents.

-   :material-alert-circle:{ .lg .middle } **[Failure modes](FAILURE_MODES.md)**

    ---

    Intentional behaviors that look like bugs and where they live.

-   :material-pencil-ruler:{ .lg .middle } **[Authoring standard](AUTHORING_STANDARD.md)**

    ---

    Pedagogy, IA, voice, and brand rules for these docs. Use as a system
    prompt when generating or revising pages.

</div>

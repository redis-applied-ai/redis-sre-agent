---
description: Walk through a complete simulated incident triage with the SRE agent CLI.
---

# Incident triage walkthrough

Follow this walkthrough to see the agent diagnose a real incident — high
memory usage and slow queries on a seeded demo Redis — end to end. You
will start the stack, ask the agent a question, and watch it call tools,
correlate signals, and produce an answer with citations. If you have not
yet booted the local stack, do the [Local quick
start](../user_guide/01_local_quickstart.md) first.

**Related:** [Triage loop (concept)](../concepts/triage_loop.md) ·
[CLI workflows](../user_guide/how_to_guides/cli_workflows.md)

## Scenario

A Redis instance is showing high memory usage and slow queries. We will use the SRE Agent to diagnose the issue.

## Step 1: Start the stack

```bash
make local-services
```

This starts:
- The SRE Agent API on port 8080
- Redis instances on ports 7843 (agent) and 7844 (demo target)
- Grafana on port 3001
- Prometheus on port 9090

## Step 2: Query the agent

```bash
docker compose exec -T sre-agent uv run redis-sre-agent \
  query "My Redis instance is using too much memory. What should I check?"
```

The agent will:
1. Search its knowledge base for memory-related runbooks
2. Inspect the target Redis instance using `INFO memory`
3. Check the eviction policy and maxmemory configuration
4. Provide actionable recommendations with citations

## Step 3: Investigate a live target

```bash
docker compose exec -T sre-agent uv run redis-sre-agent \
  query "Check the slow log for the demo instance" -r demo
```

The agent calls `SLOWLOG GET` on the demo target and analyzes the results.

## Step 4: Review in the UI

Open `http://localhost:3002` to see the conversation history, tool calls, and citations in the web UI.

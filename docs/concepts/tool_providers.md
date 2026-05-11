---
description: How the agent talks to live Redis infrastructure through provider plugins.
---

# Tool providers

Tool providers are the agent's hands. They expose typed tools — INFO,
SLOWLOG, Prometheus queries, log searches, cluster operations — that the
LLM can decide to call mid-conversation. Read this page to understand how
providers are discovered and selected; then go to [Tool providers
(how-to)](../user_guide/how_to_guides/tool_providers.md) to add one, or
[Custom tool provider](../examples/custom_provider.md) for a complete
worked example.

**Related:** [Triage loop](triage_loop.md) ·
[Configuration](../user_guide/how_to_guides/configuration.md)

## Built-in providers

| Provider | Tools | Purpose |
|----------|-------|---------|
| **Redis CLI** | `redis-cli INFO`, `redis-cli CONFIG GET`, `SLOWLOG` | Direct Redis introspection |
| **Prometheus** | Query metrics, alert status | Time-series monitoring data |
| **Loki** | Log search, pattern matching | Log aggregation |
| **Redis Enterprise** | Cluster status, shard info, rebalance | Enterprise cluster management |
| **Redis Cloud** | Subscription info, database status | Cloud instance management |

## Provider discovery

Providers are registered in the agent configuration (`config.yaml`). Each provider declares:

- **Name** - Unique identifier
- **Type** - The provider class to instantiate
- **Connection** - How to reach the external system (URL, credentials)
- **Tools** - Which tools this provider makes available
- **Permissions** - Read-only vs read-write access

## Adding custom providers

You can extend the agent with custom tool providers by implementing the provider interface:

1. Create a class that inherits from the base provider
2. Define the tools it exposes (name, description, parameters, return type)
3. Register it in the configuration
4. The agent will discover and use it during triage

## Permission model

- **Read-only** (default) - Tools that inspect state without modifying it
- **Read-write** - Tools that can modify Redis configuration or data (requires explicit opt-in)
- **Human-in-the-loop** - Write operations can require approval before execution

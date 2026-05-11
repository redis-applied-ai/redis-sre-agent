---
description: Build and register a custom tool the SRE agent can call.
---

# Custom tool provider

This worked example takes you from an empty file to a registered Datadog
provider the agent can call mid-triage. You'll write the provider class,
register it in `config.yaml`, and verify the agent invokes it. Read
[Tool providers (concept)](../concepts/tool_providers.md) first if you
want the mental model; come here when you're ready to write code.

**Related:** [Tool providers (how-to)](../user_guide/how_to_guides/tool_providers.md) ·
[Configuration](../user_guide/how_to_guides/configuration.md)

## Overview

A tool provider is a class that exposes one or more tools the agent can call during triage. Each tool has:
- A name and description (used by the LLM to decide when to call it)
- Input parameters
- A function that executes the tool and returns a result

## Example: Datadog metrics provider

```python
from redis_sre_agent.tools import ToolProvider, Tool

class DatadogProvider(ToolProvider):
    """Fetch Redis metrics from Datadog."""

    name = "datadog"

    def __init__(self, api_key: str, app_key: str):
        self.api_key = api_key
        self.app_key = app_key

    def tools(self) -> list[Tool]:
        return [
            Tool(
                name="datadog_query_metrics",
                description="Query Redis metrics from Datadog for a given time range",
                parameters={
                    "query": {"type": "string", "description": "Datadog metric query"},
                    "from_ts": {"type": "integer", "description": "Start timestamp"},
                    "to_ts": {"type": "integer", "description": "End timestamp"},
                },
                handler=self._query_metrics,
            )
        ]

    async def _query_metrics(self, query: str, from_ts: int, to_ts: int) -> dict:
        # Call Datadog API and return metrics
        ...
```

## Registration

Add the provider to your `config.yaml`:

```yaml
tool_providers:
  - type: custom.DatadogProvider
    api_key: ${DATADOG_API_KEY}
    app_key: ${DATADOG_APP_KEY}
```

The agent will discover the tool and use it when relevant to a triage query.

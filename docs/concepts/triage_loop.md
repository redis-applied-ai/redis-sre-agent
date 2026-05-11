---
description: The diagnose-investigate-act loop the agent runs on every incident.
---

# Triage loop

The triage loop is the agent's clinical reasoning cycle: observe, think,
act, repeat. Each iteration the LLM looks at what it knows, decides
whether it needs more information, and either calls a tool or responds
with citations. Understanding this loop is the difference between
"prompting an LLM" and "operating an SRE agent." For an end-to-end run,
see [Incident triage walkthrough](../examples/incident_triage.md).

**Related:** [Core architecture](core.md) · [Tool providers](tool_providers.md)

## How the loop works

1. **Receive query** - The user asks a question or describes a problem
2. **Retrieve context** - The agent searches its knowledge base for relevant runbooks, docs, and prior triage results
3. **Reason** - The LLM analyzes the context and decides if it has enough information to answer
4. **Tool call** - If more data is needed, the agent calls a tool (Redis CLI, metrics API, log search)
5. **Collect result** - The tool output is added to the conversation context
6. **Repeat or respond** - Steps 3-5 repeat until the agent can provide an actionable answer with citations

## Tool-call lifecycle

Each tool call follows this lifecycle:

```
PENDING → EXECUTING → SUCCESS / FAILURE
```

- **PENDING** - The agent has decided to call a tool but it has not started
- **EXECUTING** - The tool is running (may involve network calls to Redis or monitoring APIs)
- **SUCCESS** - The tool returned a result that is added to context
- **FAILURE** - The tool failed; the agent may retry or use an alternative approach

## Guardrails

- Maximum tool calls per query (configurable, default: 10)
- Timeout per tool call (configurable)
- Read-only tools by default; write operations require explicit approval
- All tool calls are logged for audit

## Citation model

Every claim in the agent's response is backed by a citation:

- **Knowledge base** - Links to the source document or runbook
- **Live data** - References the tool call that produced the data
- **Combined** - Cross-references knowledge and live data

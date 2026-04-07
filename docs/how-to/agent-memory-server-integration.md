# Agent Memory Server Integration

This document explains why the Redis SRE Agent integrates with Redis Agent Memory Server (AMS), what the integration actually does, and how to use it effectively.

## Why

The Redis SRE Agent already has several strong context sources:

- the canonical thread transcript store in Redis
- the knowledge base and runbooks
- live diagnostics, metrics, logs, and instance/cluster APIs

Those sources answer different questions:

- transcript store: what was said in this thread
- KB/runbooks: what Redis guidance exists in general
- live tools: what is true right now

AMS fills a different gap: durable contextual recall across turns.

The goal is not to replace transcript history or live signals. The goal is to let the agent remember useful prior context such as:

- operator interaction preferences
- durable facts about an instance or cluster
- notable past incidents and outcomes
- recurring operational patterns

That gives the agent continuity without treating memory as ground truth.

## What The Integration Is

The integration is additive.

- `ThreadManager` remains the canonical raw transcript store.
- AMS is used for working memory and long-term memory.
- KB/runbooks remain the general knowledge source.
- live tools remain the source of current-state truth.

In practical terms, the agent now does this around a turn:

1. Before answering, it asks AMS for relevant prior memory.
2. It merges that with KB/live context.
3. It answers the question.
4. After the turn, it writes back working memory and allows long-term extraction.

The implementation uses the Python SDK (`agent-memory-client`) directly from repo code rather than relying on opportunistic MCP tool calls. That keeps retrieval deterministic and testable.

## Memory Scopes

The integration now distinguishes two long-term memory scopes.

### User-scoped memory

This is for operator-specific context:

- response style preferences
- durable user-specific habits
- user-specific investigative history

Examples:

- “alice prefers concise answers”
- “alice usually wants root-cause-first summaries”

### Asset-scoped memory

This is for shared operational context tied to a Redis asset:

- instance history
- cluster history
- past incidents and outcomes
- stable environment facts

Examples:

- “instance X hit OOM during backups last week”
- “cluster Y had replica sync issues after failover”

### Important boundary

Operator preferences must stay in user-scoped memory only.

Asset-scoped memory is shared operational memory. It should not be used to store or recall user-personalized preferences.

## Retrieval Rules

The agent applies these rules when it prepares memory context for a turn.

### When both `user_id` and asset scope are present

The agent retrieves:

- user-scoped memory filtered by `user_id`
- asset-scoped memory filtered by `instance_id` or `cluster_id`

This is the richest path because it combines:

- operator personalization
- shared operational asset history

### When only `user_id` is present

The agent retrieves only user-scoped memory.

### When only asset scope is present

The agent retrieves only asset-scoped memory.

This is the fallback path when the caller has no explicit `user_id`.

### When neither is present

The agent skips long-term memory retrieval.

## Working Memory Behavior

AMS working memory is still used, but carefully:

- user-scoped working memory supports user/session continuity
- asset-scoped working memory exists to support asset-scoped extraction and continuity

However, the prompt-building path intentionally avoids feeding asset working-memory summaries back into the model. Asset recall should come from asset long-term memories, not from asset working-memory summaries that might accidentally carry conversational preference residue.

## Long-Term Extraction

The integration uses a custom extraction strategy.

### User-scoped extraction focus

- operator interaction preferences
- durable user-specific context
- stable facts or incidents that matter to that user and asset

### Asset-scoped extraction focus

- stable Redis environment facts
- notable episodic incidents and outcomes
- recurring operational context

### Explicit exclusions

The integration is designed to avoid storing:

- raw transcripts
- raw logs
- raw tool outputs
- secrets or credentials
- speculative diagnoses

In addition, asset-scoped long-term memory is filtered on read to prevent operator-preference-like memories from surfacing there, even if they were extracted incorrectly.

## Fail-Open Behavior

AMS is intentionally fail-open.

If AMS retrieval or persistence fails:

- the turn still completes
- transcript history still exists
- KB/runbook retrieval still works
- live tools still run

That means AMS improves context quality, but it is not required for the agent to answer.

## How To Leverage It

### Best practice 1: provide `user_id` when you want personalization

If you want operator-specific recall, pass `user_id`.

Without `user_id`, the agent will not use user-scoped memory.

### Best practice 2: provide `instance_id` or `cluster_id` when you want operational recall

If you want memory about a specific Redis system, provide:

- `instance_id`, or
- `cluster_id`

That enables asset-scoped recall.

### Best practice 3: use both for the richest context

If you provide both:

- `user_id`
- `instance_id` or `cluster_id`

the agent can combine:

- user-specific preferences
- shared operational history for that asset

### Best practice 4: rely on live tools for current-state truth

AMS memory is prior context, not current truth.

Use it to remember:

- what happened before
- how the operator prefers answers
- what this asset is known for

But rely on live metrics/logs/diagnostics for:

- current memory usage
- active connection state
- current replication status
- present incidents

## Operational Summary

In short:

- transcript store = canonical conversation record
- AMS = durable contextual memory
- KB = general Redis/SRE knowledge
- live tools = current-state truth

That is the intended integration model.

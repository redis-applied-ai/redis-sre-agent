## Source Document Features (Front Matter, Pinned Docs, Skills, Support Tickets)

This page documents the source-document features added for agent behavior customization.

These features work through `pipeline prepare-sources` ingestion and are used by all primary agents (`chat`, `triage`, `knowledge`) via shared startup context logic.

---

## Front Matter

Source documents can include YAML front matter:

```markdown
---
title: Example Document
doc_type: skill
category: shared
name: example-skill
summary: Short summary shown in skills TOC.
priority: high
pinned: true
version: latest
product_labels: redis-enterprise,redis-cloud
---
```

Supported common fields:

- `title`: display title
- `doc_type`: semantic document type (examples: `skill`, `support_ticket`, `runbook`)
- `category`: source category (for example `shared`, `enterprise`, `oss`)
- `name`: stable short identifier
- `summary`: short summary used in listings/TOC
- `priority`: `high`, `normal`, `low`
- `pinned`: whether to inject into startup context
- `version`: version tag for retrieval filtering
- `product_labels`: comma-separated product labels

---

## Pinned Documents

When `pinned: true`, document content is injected into startup context for agent runs.

- Pinned docs are included before skills/tools instructions.
- Ordering is deterministic by priority.
- This is intended for durable org context (glossaries, policies, hard constraints).

---

## Skills

Set `doc_type: skill` to create an instruction skill document.

At startup, agents receive:

- a skills TOC (name + summary) relevant to the query
- tool instructions for skill retrieval:
  - `skills_check("<query>")`
  - `get_skill("<skill_name>")`

`get_skill` returns only:

- `skill_name`
- `full_content`

This keeps skill retrieval payloads compact and avoids duplicate fragment/full-content payloads.

---

## Support Tickets

Set `doc_type: support_ticket` for ticket documents.

Support-ticket tools:

- `search_support_tickets("<query>")`: search ticket corpus only
- `get_support_ticket("<id>")`: fetch complete ticket content

Startup instructions explicitly tell agents to:

1. Ask for concrete identifiers (cluster name/host) when missing.
2. Search tickets with identifiers + symptoms.
3. Fetch and summarize best matching ticket(s).

---

## Shared System-Prompt Behavior Across Agents

`chat`, `triage`, and `knowledge` all use the same startup context builder:

- pinned documents
- skills TOC
- tool usage instructions (including support-ticket tools/workflow)

Follow-up turns in threaded conversations also get this startup context when absent, so behavior is consistent beyond turn 1.

---

## Ingest and Verify

Example ingestion:

```bash
uv run redis-sre-agent pipeline prepare-sources \
  --source-dir source_documents/shared \
  --batch-date 2099-01-04
```

Example validation flow:

```bash
# ask without identifiers (agent should request cluster/host)
uv run redis-sre-agent query --agent chat "Can you find relevant support tickets for failover resets?"

# continue thread with concrete identifiers
uv run redis-sre-agent query --agent chat --thread-id <thread_id> \
  "Host is cache-prod-1.redis.company.net; errors are ECONNRESET during failover."

# inspect tool envelopes and citations
uv run redis-sre-agent thread trace <assistant_message_id> --json
uv run redis-sre-agent thread get <thread_id> --json
uv run redis-sre-agent task get <task_id> --json | jq '.tool_calls'
```

---

## Related Docs

- [Pipelines & ingestion](./pipelines.md)
- [CLI usage](./cli.md)
- [CLI reference](../reference/cli.md)

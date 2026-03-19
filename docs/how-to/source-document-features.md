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

Exact-match behavior:

- `search_support_tickets("<ticket-id>")` performs exact matching on stable identifier fields before merging semantic results.
- Exact-looking queries also run a literal phrase search across `title`, `summary`, and `content`, which lets ticket searches find documents that mention the ticket ID in their body text.
- `get_support_ticket("<ticket-id>")` also accepts indexed chunk IDs like `sre_support_tickets:<document_hash>:chunk:<n>` and normalizes them back to the canonical ticket/document hash.

Examples:

```text
search_support_tickets("RET-4421")
get_support_ticket("RET-4421")
get_support_ticket("sre_support_tickets:RET-4421:chunk:0")
```

For general knowledge documents, quoted queries trigger the same precise-search path. Use quotes when you need an exact name, source match, or literal phrase search over the document text.

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
# Fresh Redis databases: initialize all required indexes once
uv run redis-sre-agent index recreate --yes --json

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

## Minimal Three-Document Example

The repository includes a ready-to-run set under `source_documents/shared/release-v028-example/`.

Included files:

- `01-policy.md`: pinned runbook with escalation code `RDX-911`
- `02-skill.md`: `failover-investigation` skill document
- `03-ticket.md`: support ticket for `ECONNRESET` during failover

Ingest and verify:

```bash
# Fresh Redis databases: initialize all required indexes once
uv run redis-sre-agent index recreate --yes --json

uv run redis-sre-agent pipeline prepare-sources \
  --source-dir source_documents/shared/release-v028-example \
  --batch-date 2099-01-04

uv run redis-sre-agent pipeline ingest --batch-date 2099-01-04

uv run redis-sre-agent query --agent chat \
  "For sev-1 Redis incidents, what escalation code must we post?"

uv run redis-sre-agent query --agent chat \
  "Do we have a skill named failover-investigation?"

uv run redis-sre-agent query --agent chat \
  "Find support tickets for ECONNRESET during failover on cache-prod-1.redis.company.net."
```

Expected outcomes:

- The policy query returns `RDX-911` from pinned startup context.
- The skill query references `failover-investigation`.
- The support-ticket query uses `search_support_tickets` and `get_support_ticket` in `thread trace`.

---

## Related Docs

- [Pipelines & ingestion](./pipelines.md)
- [CLI usage](./cli.md)
- [CLI reference](../reference/cli.md)

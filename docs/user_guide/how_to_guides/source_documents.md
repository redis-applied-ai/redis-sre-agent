---
description: Front matter, pinned docs, skills, and support tickets in the knowledge base.
---

# Source documents

Source documents are the runbooks, skills, pinned context, and support
tickets you feed the agent so it answers in your team's voice with your
team's playbooks. Each document supports YAML front matter that controls
how the chunker treats it, whether it is auto-loaded into every
conversation, and which agents see it. Use this guide when you are
writing or curating those files; for the underlying mechanics, see
[Pipelines (concept)](../../concepts/pipelines.md).

**Related:** [Pipelines (how-to)](pipelines.md) ·
[REST API reference](../../api/rest_api.md)

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
url: https://example.com/docs/example-document
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
- `url`: canonical external URL to publish as `source_url` during ingestion
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

The agent supports both legacy markdown skills and Agent Skills packages.

Legacy skills:

- set `doc_type: skill` in a markdown source document
- retrieve them with `skills_check` and `get_skill`

Agent Skills packages:

- place a directory under a configured skill root that contains `SKILL.md`
- optional package directories:
 - `references/`
 - `scripts/`
 - `assets/`
 - `agents/openai.yaml`
- the shipped runtime uses a Redis-backed `SkillBackend`, but you can swap in a custom backend
  if you run your own central skill service

At startup, agents receive:

- a skills TOC (name + summary) relevant to the query
- tool instructions for skill retrieval:
 - `skills_check("<query>")`
 - `get_skill("<skill_name>")`
 - `get_skill_resource("<skill_name>", "<resource_path>")`

Legacy `get_skill` responses stay compact and return only:

- `skill_name`
- `full_content`

Agent Skills `get_skill` responses return the entrypoint plus a manifest of references, scripts, and text
assets. Resource bodies remain separate and are fetched explicitly with `get_skill_resource`.

### Agent Skills package example

The repository includes a package example under `skills/redis-maintenance-triage/`.

Example package layout:

```text
skills/
  redis-maintenance-triage/
    SKILL.md
    references/
      maintenance-checklist.md
    scripts/
      collect_maintenance_context.sh
    assets/
      example-query.txt
    agents/
      openai.yaml
```

### Script handling

Agent Skills package scripts are retrieval-only in v1.

- They are indexed and returned through `get_skill` and `get_skill_resource`.
- They are not executed by this agent runtime.
- A future execution path must go through a separate executor interface.

### Text assets

V1 resolves the text-asset question as follows:

- text-like assets are indexed by default and can be retrieved explicitly
- binary assets stay out of model retrieval and are reserved for UI or CLI consumers

### CLI helpers

Use the top-level `skills` CLI for discovery and package scaffolding:

```bash
uv run redis-sre-agent skills list
uv run redis-sre-agent skills show redis-maintenance-triage
uv run redis-sre-agent skills read-resource \
  redis-maintenance-triage references/maintenance-checklist.md
uv run redis-sre-agent skills scaffold legacy-skill.md skills/legacy-skill
```

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
- [CLI workflows](./cli_workflows.md)
- [CLI reference](../../api/cli_ref.md)

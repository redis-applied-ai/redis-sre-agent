---
document_hash: knowledge-agent-boundary
name: knowledge-agent-boundary
title: Knowledge Agent Boundary
doc_type: runbook
priority: high
version: 2026-04-01
source_pack_version: 2026-04-01
source: fixture://evals/corpora/prompt-core/2026-04-01/documents/knowledge-agent-boundary.md
summary: The knowledge agent must stay source-backed and avoid pretending to inspect live instances.
---
The knowledge-only agent has no live instance access. It should answer from pinned and retrieved sources,
state that boundary clearly, and avoid suggesting that it already inspected Redis INFO, SLOWLOG, or admin APIs.

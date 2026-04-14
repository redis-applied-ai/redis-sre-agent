---
document_hash: iterative-investigation-runbook
name: iterative-investigation-runbook
title: Iterative Investigation Runbook
doc_type: knowledge
category: incident
priority: high
summary: Start with INFO memory and MEMORY STATS before widening a memory-pressure investigation.
source: fixture://corpora/prompt-core/2026-04-14/documents/iterative-investigation-runbook.md
---
When a Redis node is evicting keys or showing latency, begin with a small number of targeted checks:

1. Inspect `INFO memory` for `used_memory`, `maxmemory`, `maxmemory_policy`, and `evicted_keys`.
2. Inspect `MEMORY STATS` to separate dataset growth from allocator overhead.
3. Only after those checks, expand into latency, client, or key-distribution analysis if the first results leave ambiguity.

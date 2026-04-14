---
document_hash: memory-pressure-runbook
name: memory-pressure-runbook
title: Memory Pressure Runbook
doc_type: runbook
category: incident
priority: critical
pinned: true
summary: Confirm memory pressure with INFO memory and MEMORY STATS before changing configuration.
source: fixture://corpora/redis-docs-curated/2026-04-01/documents/memory-pressure-runbook.md
---
Confirm whether `used_memory` is close to `maxmemory` and whether evictions align with the configured policy before changing Redis configuration.

Start with `INFO memory` and `MEMORY STATS`, then explain the evidence before suggesting any config updates.

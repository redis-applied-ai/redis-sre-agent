---
document_hash: memory-policy-latest
name: memory-policy-latest
title: Redis 8 Memory Policy Guidance
doc_type: knowledge
category: incident
priority: high
version: latest
source: fixture://corpora/retrieval-curated/2026-04-14/documents/memory-policy-latest.md
summary: Latest guidance for memory pressure should prioritize evidence before policy changes.
---
For Redis 8 memory pressure, start with INFO memory and workload evidence before suggesting any
policy change. Treat `maxmemory-policy` adjustments as follow-up work after the current pressure
pattern is understood.

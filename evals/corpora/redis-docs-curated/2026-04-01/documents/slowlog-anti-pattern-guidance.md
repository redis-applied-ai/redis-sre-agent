---
document_hash: slowlog-anti-pattern-guidance
name: slowlog-anti-pattern-guidance
title: Slowlog Anti-Pattern Guidance
doc_type: knowledge
category: incident
priority: high
summary: Slowlog evidence often points to application command patterns rather than Redis outages.
source: fixture://corpora/redis-docs-curated/2026-04-01/documents/slowlog-anti-pattern-guidance.md
---
Use `SLOWLOG GET` and command stats to identify expensive command patterns.

Prefer fixing the workload anti-pattern before changing Redis configuration or restarting the service.

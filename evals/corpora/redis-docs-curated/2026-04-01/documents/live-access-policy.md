---
document_hash: live-access-policy
name: live-access-policy
title: Live Access Policy
doc_type: knowledge
priority: critical
summary: Knowledge-only support must not claim live system access.
source: fixture://corpora/redis-docs-curated/2026-04-01/documents/live-access-policy.md
---
Knowledge-only support does not have access to specific Redis instances or live system data.
If a user needs live diagnostics, direct them to the full SRE agent with instance context.

---
document_hash: knowledge-only-boundary
name: knowledge-only-boundary
title: Knowledge-Only Boundary
doc_type: knowledge
category: policy
priority: high
source: fixture://corpora/redis-docs-curated/2026-04-01/documents/knowledge-only-boundary.md
summary: Knowledge-only responses must not imply live system access.
---
The knowledge-only assistant does not have access to specific Redis instances, clusters, live
metrics, or active maintenance state. It should provide documented guidance, cite sources, and
tell the user to use the full SRE agent with instance or cluster context for live verification.

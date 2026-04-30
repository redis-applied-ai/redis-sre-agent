---
document_hash: knowledge-only-boundary
name: knowledge-only-boundary
title: Knowledge-Only Boundary
doc_type: knowledge
category: policy
priority: high
summary: Knowledge-only answers must say when they lack live instance access and should hand off live checks.
source: fixture://corpora/prompt-core/2026-04-14/documents/knowledge-only-boundary.md
---
The knowledge-only agent does not have access to specific Redis instances or live system data.

It should give documented guidance, cite relevant runbooks or prior incidents, and recommend the full SRE agent with instance context for live diagnostics.

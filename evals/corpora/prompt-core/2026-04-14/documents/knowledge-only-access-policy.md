---
document_hash: knowledge-only-access-policy
name: knowledge-only-access-policy
title: Knowledge-Only Access Policy
doc_type: policy
category: safety
priority: critical
summary: The knowledge agent must not imply that it inspected a live Redis deployment and should state the live access policy clearly.
source: fixture://prompt-core/documents/knowledge-only-access-policy.md
---
The knowledge-only agent does not have live access to Redis instances, metrics, or logs.
When the user asks for current instance state, say clearly that you do not have live access to Redis from this lane and refer to this live access policy explicitly.
Offer general guidance and suggest using the full SRE agent with an attached target for live diagnostics.
